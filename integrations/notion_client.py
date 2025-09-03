"""
Module d'intégration avec Notion pour le bot Telegram Comptables.

Gère les opérations CRUD sur la base de données Notion des comptables,
la déduplication et la vérification du schéma.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from notion_client import Client
from notion_client.errors import APIResponseError

from utils.validation import sanitize_text_field, NOTION_TEXT_MAX_LENGTH, NOTION_TITLE_MAX_LENGTH

logger = logging.getLogger(__name__)


class NotionComptablesClient:
    """Client pour interagir avec la base de données Notion des comptables."""
    
    # Schéma attendu de la base de données
    EXPECTED_SCHEMA = {
        "Nom": {"type": "title"},
        "Contact": {"type": "rich_text"},
        "Email": {"type": "email"},
        "Téléphone": {"type": "phone_number"},
        "Ville": {"type": "rich_text"},
        "Source": {"type": "select", "options": ["Client", "Prospect", "LinkedIn", "Appel", "Autre"]},
        "Ajouté par": {"type": "rich_text"},
        "Statut": {"type": "select", "options": ["À qualifier", "Cordial", "Ciblé", "Autre"]},
        "Notes": {"type": "rich_text"},
        "Date d'ajout": {"type": "date"}
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
        
        Args:
            comptable_data: Données du comptable
            
        Returns:
            Propriétés formatées pour Notion
        """
        properties = {}
        
        # Nom (Title) - obligatoire
        if "nom" in comptable_data and comptable_data["nom"]:
            properties["Nom"] = {
                "title": [{"text": {"content": sanitize_text_field(comptable_data["nom"], NOTION_TITLE_MAX_LENGTH) or "Sans nom"}}]
            }
        
        # Contact (Rich text)
        if "contact" in comptable_data and comptable_data["contact"]:
            properties["Contact"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["contact"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Email
        if "email" in comptable_data and comptable_data["email"]:
            properties["Email"] = {"email": comptable_data["email"]}
        
        # Téléphone
        if "telephone" in comptable_data and comptable_data["telephone"]:
            properties["Téléphone"] = {"phone_number": comptable_data["telephone"]}
        
        # Ville (Rich text)
        if "ville" in comptable_data and comptable_data["ville"]:
            properties["Ville"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["ville"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Source (Select)
        source = comptable_data.get("source", "Autre")
        if source in self.EXPECTED_SCHEMA["Source"]["options"]:
            properties["Source"] = {"select": {"name": source}}
        
        # Ajouté par (Rich text)
        if "ajoute_par" in comptable_data and comptable_data["ajoute_par"]:
            properties["Ajouté par"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["ajoute_par"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Statut (Select) - par défaut "À qualifier"
        statut = comptable_data.get("statut", "À qualifier")
        if statut in self.EXPECTED_SCHEMA["Statut"]["options"]:
            properties["Statut"] = {"select": {"name": statut}}
        
        # Notes (Rich text)
        if "notes" in comptable_data and comptable_data["notes"]:
            properties["Notes"] = {
                "rich_text": [{"text": {"content": sanitize_text_field(comptable_data["notes"], NOTION_TEXT_MAX_LENGTH)}}]
            }
        
        # Date d'ajout (Date) - automatique
        properties["Date d'ajout"] = {
            "date": {"start": datetime.now().isoformat()}
        }
        
        return properties
    
    async def find_existing_comptables(self, email: Optional[str] = None, 
                                     nom: Optional[str] = None, 
                                     ville: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recherche des comptables existants selon les critères de déduplication.
        
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
                    "property": "Email",
                    "email": {"equals": email}
                })
            
            # Filtre par nom ET ville si fournis
            if nom and ville:
                filters.extend([
                    {
                        "property": "Nom",
                        "title": {"equals": nom}
                    },
                    {
                        "property": "Ville",
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
                        "title": {"contains": query}
                    },
                    {
                        "property": "Ville",
                        "rich_text": {"contains": query}
                    },
                    {
                        "property": "Email",
                        "email": {"contains": query}
                    },
                    {
                        "property": "Contact",
                        "rich_text": {"contains": query}
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
                # Extrait le titre et l'URL
                title_prop = page.get("properties", {}).get("Nom", {})
                title_content = title_prop.get("title", [])
                title = title_content[0].get("text", {}).get("content", "Sans nom") if title_content else "Sans nom"
                
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
        
        Args:
            page: Page Notion
            
        Returns:
            Titre de la page
        """
        title_prop = page.get("properties", {}).get("Nom", {})
        title_content = title_prop.get("title", [])
        if title_content:
            return title_content[0].get("text", {}).get("content", "Sans nom")
        return "Sans nom"

