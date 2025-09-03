#!/usr/bin/env python3
"""
Script pour exécuter le bot Telegram en mode polling (développement).

Ce mode ne nécessite pas de webhook et est idéal pour le développement local.
"""

import asyncio
import logging
import signal
import sys

from telegram.ext import Application

from utils.config import config
from utils.logging_config import setup_logging, bot_stats
from integrations.notion_client import NotionComptablesClient

# Import des handlers depuis app.py
from app import setup_handlers, notion_client

# Configuration du logging
setup_logging("INFO")
logger = logging.getLogger(__name__)

# Application Telegram globale
telegram_app: Application = None
running = True


async def setup_application():
    """Configure l'application Telegram pour le mode polling."""
    global telegram_app, notion_client
    
    logger.info("Configuration de l'application en mode polling...")
    
    try:
        # Valide la configuration
        config.validate()
        logger.info("Configuration validée")
        
        # Initialise le client Notion
        notion_client = NotionComptablesClient(config.NOTION_TOKEN, config.NOTION_DB_ID)
        
        # Vérifie le schéma Notion
        is_valid, errors = await notion_client.verify_database_schema()
        if not is_valid:
            logger.error(f"Schéma Notion invalide: {errors}")
            logger.info("Exécutez 'python scripts/verify_notion_schema.py' pour corriger le schéma")
            return False
        
        # Crée l'application Telegram
        telegram_app = Application.builder().token(config.TELEGRAM_TOKEN).build()
        
        # Configure les handlers (réutilise la fonction d'app.py)
        setup_handlers_for_polling()
        
        logger.info("Application configurée avec succès")
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de la configuration: {e}")
        return False


def setup_handlers_for_polling():
    """Configure les handlers pour le mode polling."""
    # Import des handlers depuis app.py
    from app import (
        start_command, help_command, find_command, cancel_command,
        start_add_command, handle_nom, handle_contact, handle_email,
        handle_telephone, handle_ville, handle_source_selection,
        handle_notes, handle_duplicate_choice,
        ASKING_NOM, ASKING_CONTACT, ASKING_EMAIL, ASKING_TELEPHONE,
        ASKING_VILLE, ASKING_SOURCE, ASKING_NOTES, HANDLING_DUPLICATE
    )
    
    from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, filters
    
    # Handler de conversation pour /add
    add_conversation = ConversationHandler(
        entry_points=[CommandHandler("add", start_add_command)],
        states={
            ASKING_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nom)],
            ASKING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact)],
            ASKING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            ASKING_TELEPHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_telephone)],
            ASKING_VILLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ville)],
            ASKING_SOURCE: [CallbackQueryHandler(handle_source_selection)],
            ASKING_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notes)],
            HANDLING_DUPLICATE: [CallbackQueryHandler(handle_duplicate_choice)]
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    )
    
    # Ajoute tous les handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(add_conversation)
    telegram_app.add_handler(CommandHandler("find", find_command))
    telegram_app.add_handler(CommandHandler("cancel", cancel_command))
    
    logger.info("Handlers configurés pour le mode polling")


async def run_polling():
    """Exécute le bot en mode polling."""
    global telegram_app, running
    
    logger.info("Démarrage du bot en mode polling...")
    
    try:
        # Initialise l'application
        await telegram_app.initialize()
        await telegram_app.start()
        
        logger.info("🤖 Bot démarré en mode polling!")
        logger.info("Appuyez sur Ctrl+C pour arrêter")
        
        # Démarre le polling
        await telegram_app.updater.start_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=-1,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
        
        # Boucle principale
        while running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution: {e}")
    finally:
        logger.info("Arrêt du bot...")
        
        if telegram_app:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
        
        logger.info("Bot arrêté")


def signal_handler(signum, frame):
    """Gestionnaire de signaux pour un arrêt propre."""
    global running
    
    logger.info(f"Signal {signum} reçu, arrêt en cours...")
    running = False


async def main():
    """Fonction principale."""
    logger.info("=== Bot Telegram Comptables - Mode Polling ===")
    
    # Configure les gestionnaires de signaux
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Configure l'application
        success = await setup_application()
        if not success:
            logger.error("Échec de la configuration")
            sys.exit(1)
        
        # Affiche les statistiques de démarrage
        logger.info(f"Utilisateurs autorisés: {len(config.ALLOWED_USER_IDS)}")
        logger.info(f"Région téléphone par défaut: {config.DEFAULT_PHONE_REGION}")
        
        # Exécute le bot
        await run_polling()
        
    except KeyboardInterrupt:
        logger.info("Interruption clavier détectée")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        sys.exit(1)
    
    # Affiche les statistiques finales
    final_stats = bot_stats.get_stats()
    logger.info(f"Statistiques finales: {final_stats}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")
        sys.exit(0)

