"""
Module d'intégration avec Notion pour le bot Telegram Comptables.
Adapté à la structure existante de la base de données.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from notion_client import Client
from notion_client.errors import APIResponseError

from utils.validation import sanitize_text_field, NOTION_TEXT_MAX_LENGTH, NOTION_TITLE_MAX_LENGTH

logger = logging.getLogger(__name__)


class NotionComptablesClient:
    """Client pour interagir avec la base de données Notion des comptables - Structure adaptée."""
    
    # Schéma adapté à la structure existante
    EXPECTED_SCHEMA = {
        "Nom": {"type": "rich_text"},                    # Nom (Rich Text)
        "Prénom": {"type": "rich_text"},                 # Prénom (Rich Text)  
        "Société": {"type": "rich_text"},                # Société (Rich Text)
        "Phone": {"type": "phone_number"},               # Phone (Phone Number)
        "Localisation": {"type": "rich_text"},           # Localisation (Rich Text)
        "Customer Email": {"type": "email"},             # Customer Email (Email)
        "Date": {"type": "date"},                        # Date (Date)
        "Étape de la qualification": {"type": "select"}  # Étape de la qualification (Select)
    }
    
    def __init__(self, notion_token: str, database_id: str):
        """
        Initialise le client Notion.
        
        Args:
            notion_token: Token d'authentification Notion
            database_id: ID de la base de données Notion
        """
        self.client = Client(auth=notion_token)
        self.database_id = database_id
        self._retry_count = 3
        self._retry_delay = 1.0
    
    async def verify_database_schema(self) -> Tuple[bool, List[str]]:
        """
        Vérifie que le schéma de la base de données correspond aux attentes.
        
        Returns:
            Tuple contenant:
            - bool: True si le schéma est correct
            - List[str]: Liste des erreurs ou propriétés manquantes
        """
        try:
            database = self.client.databases.retrieve(database_id=self.database_id)
            properties = database.get("properties", {})
            
            errors = []
            
            for prop_name, expected_config in self.EXPECTED_SCHEMA.items():
                if prop_name not in properties:
                    errors.append(f"Propriété manquante: {prop_name}")
                    continue
                
                prop_config = properties[prop_name]
                expected_type = expected_config["type"]
                actual_type = prop_config.get("type")
                
                if actual_type != expected_type:
                    errors.append(
                        f"Type incorrect pour {prop_name}: attendu {expected_type}, "
                        f"trouvé {actual_type}"
                    )
                
                # Vérifie les options pour les propriétés select
                if expected_type == "select" and "options" in expected_config:
                    select_config = prop_config.get("select", {})
                    existing_options = {opt["name"] for opt in select_config.get("options", [])}
                    expected_options = set(expected_config["options"])
                    
                    missing_options = expected_options - existing_options
                    if missing_options:
                        errors.append(
                            f"Options manquantes pour {prop_name}: {', '.join(missing_options)}"
                        )
            
            if errors:
                logger.error(f"Erreurs de schéma détectées: {errors}")
                return False, errors
            
            logger.info("Schéma de la base de données vérifié avec succès")
            return True, []
            
        except APIResponseError as e:
            error_msg = f"Erreur lors de la vérification du schéma: {e}"
            logger.error(error_msg)
            return False, [error_msg]
    
    def _build_page_properties(self, comptable_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construit les propriétés d'une page Notion à partir des données du comptable.
        Adapté à la structure existante.
        
        Args:
            comptable_data: Données du comptable
            
        Returns:
            Propriétés formatées pour Notion
        """
        properties = {}
        
        # Nom (Rich Text) - obligatoire
        if "nom" in comptable_data and comptable_data["nom"]:
            properties["Nom"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["nom"], NOTION_TEXT_MAX_LENGTH) or "Sans nom"}}]
            }
        
        # Prénom (Rich Text)
        if "prenom" in comptable_data and comptable_data["prenom"]:
            properties["Prénom"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["prenom"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Société (Rich Text)
        if "societe" in comptable_data and comptable_data["societe"]:
            properties["Société"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["societe"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Phone (Phone Number)
        if "telephone" in comptable_data and comptable_data["telephone"]:
            properties["Phone"] = {"phone_number": comptable_data["telephone"]}
        
        # Localisation (Rich Text)
        if "ville" in comptable_data and comptable_data["ville"]:
            properties["Localisation"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["ville"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Customer Email (Email)
        if "email" in comptable_data and comptable_data["email"]:
            properties["Customer Email"] = {"email": comptable_data["email"]}
        
        # Date (Date) - automatique
        properties["Date"] = {
            "date": {"start": datetime.now().isoformat()[:10]}
        }
        
        # Étape de la qualification (Select) - par défaut "Nouveau"
        properties["Étape de la qualification"] = {
            "select": {"name": "Nouveau"}
        }
        
        return properties
    
    async def find_existing_comptables(self, email: Optional[str] = None, 
                                     nom: Optional[str] = None, 
                                     ville: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recherche des comptables existants selon les critères de déduplication.
        Adapté à la structure existante.
        
        Args:
            email: Email à rechercher
            nom: Nom exact à rechercher
            ville: Ville exacte à rechercher
            
        Returns:
            Liste des comptables trouvés
        """
        try:
            filters = []
            
            # Filtre par email si fourni
            if email:
                filters.append({
                    "property": "Customer Email",
                    "email": {"equals": email}
                })
            
            # Filtre par nom ET ville si fournis
            if nom and ville:
                filters.extend([
                    {
                        "property": "Nom",
                        "rich_text": {"equals": nom}
                    },
                    {
                        "property": "Localisation",
                        "rich_text": {"equals": ville}
                    }
                ])
            
            if not filters:
                return []
            
            # Construit la requête avec OR entre les groupes de critères
            query_filter = {"or": filters} if len(filters) > 1 else filters[0]
            
            logger.info(f"Recherche de doublons avec filtre: {query_filter}")
            
            response = self.client.databases.query(
                database_id=self.database_id,
                filter=query_filter
            )
            
            results = response.get("results", [])
            logger.info(f"Trouvé {len(results)} résultat(s) potentiel(s)")
            
            return results
            
        except APIResponseError as e:
            logger.error(f"Erreur lors de la recherche de doublons: {e}")
            return []
    
    async def create_comptable(self, comptable_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Crée un nouveau comptable dans Notion.
        
        Args:
            comptable_data: Données du comptable
            
        Returns:
            Tuple contenant:
            - bool: True si la création a réussi
            - str|None: URL de la page créée si succès
            - str|None: Message d'erreur si échec
        """
        try:
            properties = self._build_page_properties(comptable_data)
            
            logger.info(f"Création d'un nouveau comptable: {comptable_data.get('nom', 'Sans nom')}")
            
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            
            page_url = response.get("url")
            logger.info(f"Comptable créé avec succès: {page_url}")
            
            return True, page_url, None
            
        except APIResponseError as e:
            error_msg = f"Erreur lors de la création: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    async def update_comptable(self, page_id: str, comptable_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Met à jour un comptable existant dans Notion.
        
        Args:
            page_id: ID de la page Notion à mettre à jour
            comptable_data: Nouvelles données du comptable
            
        Returns:
            Tuple contenant:
            - bool: True si la mise à jour a réussi
            - str|None: URL de la page mise à jour si succès
            - str|None: Message d'erreur si échec
        """
        try:
            # Récupère la page existante pour merger les données
            existing_page = self.client.pages.retrieve(page_id=page_id)
            existing_properties = existing_page.get("properties", {})
            
            # Construit les nouvelles propriétés en ne remplaçant que les valeurs non-None
            new_properties = self._build_page_properties(comptable_data)
            
            # Merge intelligent : ne remplace que si la nouvelle valeur n'est pas None/vide
            merged_properties = {}
            for prop_name, new_value in new_properties.items():
                if new_value and self._has_content(new_value):
                    merged_properties[prop_name] = new_value
            
            logger.info(f"Mise à jour du comptable {page_id} avec {len(merged_properties)} propriétés")
            
            response = self.client.pages.update(
                page_id=page_id,
                properties=merged_properties
            )
            
            page_url = response.get("url")
            logger.info(f"Comptable mis à jour avec succès: {page_url}")
            
            return True, page_url, None
            
        except APIResponseError as e:
            error_msg = f"Erreur lors de la mise à jour: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def _has_content(self, property_value: Dict[str, Any]) -> bool:
        """
        Vérifie si une propriété Notion a du contenu.
        
        Args:
            property_value: Valeur de la propriété Notion
            
        Returns:
            True si la propriété a du contenu
        """
        if "title" in property_value:
            return bool(property_value["title"])
        elif "rich_text" in property_value:
            return bool(property_value["rich_text"])
        elif "email" in property_value:
            return bool(property_value["email"])
        elif "phone_number" in property_value:
            return bool(property_value["phone_number"])
        elif "select" in property_value:
            return bool(property_value["select"])
        elif "date" in property_value:
            return bool(property_value["date"])
        
        return False
    
    async def search_comptables(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recherche des comptables par texte libre.
        Adapté à la structure existante.
        
        Args:
            query: Terme de recherche
            limit: Nombre maximum de résultats
            
        Returns:
            Liste des comptables trouvés avec titre et URL
        """
        try:
            # Recherche dans plusieurs champs
            filters = {
                "or": [
                    {
                        "property": "Nom",
                        "rich_text": {"contains": query}
                    },
                    {
                        "property": "Prénom",
                        "rich_text": {"contains": query}
                    },
                    {
                        "property": "Société",
                        "rich_text": {"contains": query}
                    },
                    {
                        "property": "Localisation",
                        "rich_text": {"contains": query}
                    },
                    {
                        "property": "Customer Email",
                        "email": {"contains": query}
                    }
                ]
            }
            
            logger.info(f"Recherche de comptables avec le terme: '{query}'")
            
            response = self.client.databases.query(
                database_id=self.database_id,
                filter=filters,
                page_size=limit
            )
            
            results = []
            for page in response.get("results", []):
                # Extrait le nom et prénom pour le titre
                properties = page.get("properties", {})
                nom_prop = properties.get("Nom", {}).get("rich_text", [])
                prenom_prop = properties.get("Prénom", {}).get("rich_text", [])
                
                nom = nom_prop[0].get("text", {}).get("content", "") if nom_prop else ""
                prenom = prenom_prop[0].get("text", {}).get("content", "") if prenom_prop else ""
                
                title = f"{prenom} {nom}".strip() or "Sans nom"
                
                results.append({
                    "id": page["id"],
                    "title": title,
                    "url": page["url"]
                })
            
            logger.info(f"Trouvé {len(results)} résultat(s) pour la recherche '{query}'")
            return results
            
        except APIResponseError as e:
            logger.error(f"Erreur lors de la recherche: {e}")
            return []
    
    def extract_page_title(self, page: Dict[str, Any]) -> str:
        """
        Extrait le titre d'une page Notion.
        Adapté à la structure existante (Nom + Prénom).
        
        Args:
            page: Page Notion
            
        Returns:
            Titre de la page
        """
        properties = page.get("properties", {})
        nom_prop = properties.get("Nom", {}).get("rich_text", [])
        prenom_prop = properties.get("Prénom", {}).get("rich_text", [])
        
        nom = nom_prop[0].get("text", {}).get("content", "") if nom_prop else ""
        prenom = prenom_prop[0].get("text", {}).get("content", "") if prenom_prop else ""
        
        title = f"{prenom} {nom}".strip() or "Sans nom"
        return title

