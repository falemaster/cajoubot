"""
Module de configuration pour le bot Telegram Comptables.

Gère le chargement et la validation des variables d'environnement.
"""

import os
from typing import List, Optional

from dotenv import load_dotenv

# Charge le fichier .env si présent
load_dotenv()


class Config:
    """Configuration centralisée de l'application."""
    
    # Configuration Telegram
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    
    # Configuration Notion
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")
    NOTION_DB_ID: str = os.getenv("NOTION_DB_ID", "")
    
    # Configuration webhook
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")
    
    # Sécurité
    ALLOWED_USER_IDS: List[int] = []
    
    # Configuration téléphone
    DEFAULT_PHONE_REGION: str = os.getenv("DEFAULT_PHONE_REGION", "FR")
    
    # Configuration serveur
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    @classmethod
    def load_allowed_users(cls) -> None:
        """Charge la liste des utilisateurs autorisés depuis les variables d'environnement."""
        allowed_users_str = os.getenv("ALLOWED_USER_IDS", "")
        if allowed_users_str:
            try:
                cls.ALLOWED_USER_IDS = [
                    int(user_id.strip()) 
                    for user_id in allowed_users_str.split(",") 
                    if user_id.strip()
                ]
            except ValueError as e:
                raise ValueError(f"Format invalide pour ALLOWED_USER_IDS: {e}")
    
    @classmethod
    def validate(cls) -> None:
        """Valide que toutes les variables d'environnement requises sont présentes."""
        missing_vars = []
        
        if not cls.TELEGRAM_TOKEN:
            missing_vars.append("TELEGRAM_TOKEN")
        
        if not cls.NOTION_TOKEN:
            missing_vars.append("NOTION_TOKEN")
        
        if not cls.NOTION_DB_ID:
            missing_vars.append("NOTION_DB_ID")
        
        if missing_vars:
            raise ValueError(
                f"Variables d'environnement manquantes: {', '.join(missing_vars)}"
            )
        
        # Charge les utilisateurs autorisés
        cls.load_allowed_users()
        
        if not cls.ALLOWED_USER_IDS:
            raise ValueError("Aucun utilisateur autorisé configuré (ALLOWED_USER_IDS)")


# Instance globale de configuration
config = Config()


def is_user_allowed(user_id: int) -> bool:
    """
    Vérifie si un utilisateur est autorisé à utiliser le bot.
    
    Args:
        user_id: L'ID Telegram de l'utilisateur
        
    Returns:
        True si l'utilisateur est autorisé
    """
    return user_id in config.ALLOWED_USER_IDS


def get_webhook_mode() -> bool:
    """
    Détermine si le bot doit fonctionner en mode webhook ou polling.
    
    Returns:
        True pour le mode webhook, False pour le mode polling
    """
    return config.WEBHOOK_URL is not None and config.WEBHOOK_URL.strip() != ""

