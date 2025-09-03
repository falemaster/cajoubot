"""
Configuration du système de logging pour le bot Telegram Comptables.

Fournit une journalisation structurée avec différents niveaux de log.
"""

import logging
import sys
from typing import Dict, Any


class StructuredFormatter(logging.Formatter):
    """Formateur de logs structuré pour une meilleure lisibilité."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Informations de base
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Ajoute des informations contextuelles si disponibles
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        if hasattr(record, "action"):
            log_data["action"] = record.action
        
        if hasattr(record, "step"):
            log_data["step"] = record.step
        
        # Formate le log
        formatted_parts = []
        formatted_parts.append(f"[{log_data['timestamp']}]")
        formatted_parts.append(f"{log_data['level']}")
        formatted_parts.append(f"{log_data['logger']}")
        
        # Ajoute le contexte si présent
        context_parts = []
        if "user_id" in log_data:
            context_parts.append(f"user:{log_data['user_id']}")
        if "action" in log_data:
            context_parts.append(f"action:{log_data['action']}")
        if "step" in log_data:
            context_parts.append(f"step:{log_data['step']}")
        
        if context_parts:
            formatted_parts.append(f"[{','.join(context_parts)}]")
        
        formatted_parts.append(f"- {log_data['message']}")
        
        # Ajoute la stack trace si c'est une exception
        formatted_log = " ".join(formatted_parts)
        if record.exc_info:
            formatted_log += "\n" + self.formatException(record.exc_info)
        
        return formatted_log


def setup_logging(level: str = "INFO") -> None:
    """
    Configure le système de logging de l'application.
    
    Args:
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configuration du logger racine
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Supprime les handlers existants
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Handler pour la console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(StructuredFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Configure les loggers spécifiques
    # Réduit le niveau de log pour les bibliothèques externes
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("notion_client").setLevel(logging.INFO)


def get_logger_with_context(name: str, user_id: int = None, action: str = None) -> logging.Logger:
    """
    Crée un logger avec du contexte prédéfini.
    
    Args:
        name: Nom du logger
        user_id: ID de l'utilisateur (optionnel)
        action: Action en cours (optionnel)
        
    Returns:
        Logger configuré avec le contexte
    """
    logger = logging.getLogger(name)
    
    # Ajoute le contexte par défaut
    if user_id is not None:
        logger = logging.LoggerAdapter(logger, {"user_id": user_id})
    
    if action is not None:
        extra = getattr(logger, "extra", {})
        extra["action"] = action
        logger = logging.LoggerAdapter(logger, extra)
    
    return logger


class BotLoggerAdapter(logging.LoggerAdapter):
    """Adaptateur de logger spécialisé pour le bot Telegram."""
    
    def __init__(self, logger: logging.Logger, user_id: int = None, action: str = None):
        self.user_id = user_id
        self.action = action
        super().__init__(logger, {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        extra = kwargs.get("extra", {})
        
        if self.user_id is not None:
            extra["user_id"] = self.user_id
        
        if self.action is not None:
            extra["action"] = self.action
        
        kwargs["extra"] = extra
        return msg, kwargs
    
    def log_step(self, step: str, message: str, level: int = logging.INFO) -> None:
        """
        Log une étape spécifique avec le contexte.
        
        Args:
            step: Nom de l'étape
            message: Message à logger
            level: Niveau de log
        """
        extra = {"step": step}
        if self.user_id is not None:
            extra["user_id"] = self.user_id
        if self.action is not None:
            extra["action"] = self.action
        
        self.log(level, message, extra=extra)


# Statistiques simples en mémoire
class BotStats:
    """Collecteur de statistiques simples pour le bot."""
    
    def __init__(self):
        self.stats = {
            "creations": 0,
            "updates": 0,
            "duplicates_detected": 0,
            "searches": 0,
            "errors": 0,
        }
    
    def increment(self, stat_name: str) -> None:
        """Incrémente un compteur de statistique."""
        if stat_name in self.stats:
            self.stats[stat_name] += 1
    
    def get_stats(self) -> Dict[str, int]:
        """Retourne les statistiques actuelles."""
        return self.stats.copy()
    
    def reset(self) -> None:
        """Remet à zéro toutes les statistiques."""
        for key in self.stats:
            self.stats[key] = 0


# Instance globale des statistiques
bot_stats = BotStats()

