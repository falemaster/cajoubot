"""
Application principale du bot Telegram Comptables.

Intègre FastAPI pour le webhook et python-telegram-bot pour la gestion des messages.
"""

import asyncio
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    ConversationHandler,
    CallbackQueryHandler,
    filters
)

from utils.config import config, is_user_allowed
from utils.logging_config import setup_logging, BotLoggerAdapter, bot_stats
from utils.validation import (
    validate_and_normalize_email, 
    validate_and_normalize_phone,
    validate_required_field,
    sanitize_text_field
)
from integrations.notion_client import NotionComptablesClient

# Configuration du logging
setup_logging("INFO")
logger = logging.getLogger(__name__)

# États de la conversation pour /add
(
    ASKING_NOM,
    ASKING_CONTACT, 
    ASKING_EMAIL,
    ASKING_TELEPHONE,
    ASKING_VILLE,
    ASKING_SOURCE,
    ASKING_NOTES,
    HANDLING_DUPLICATE
) = range(8)

# Données temporaires des conversations
conversation_data: Dict[int, Dict[str, Any]] = {}

# Client Notion global
notion_client: NotionComptablesClient = None

# Application FastAPI
app = FastAPI(title="Bot Telegram Comptables", version="1.0.0")

# Application Telegram
telegram_app: Application = None


@app.on_event("startup")
async def startup_event():
    """Initialise l'application au démarrage."""
    global telegram_app, notion_client
    
    logger.info("Démarrage de l'application...")
    
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
            raise RuntimeError("Schéma Notion invalide")
        
        # Initialise l'application Telegram
        telegram_app = Application.builder().token(config.TELEGRAM_TOKEN).build()
        
        # Ajoute les handlers
        setup_handlers()
        
        # Initialise l'application
        await telegram_app.initialize()
        
        logger.info("Application initialisée avec succès")
        
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Nettoie les ressources au shutdown."""
    global telegram_app
    
    logger.info("Arrêt de l'application...")
    
    if telegram_app:
        await telegram_app.shutdown()
    
    logger.info("Application arrêtée")


@app.get("/healthz")
async def health_check():
    """Endpoint de health check."""
    return {
        "status": "healthy",
        "stats": bot_stats.get_stats()
    }


@app.get("/metrics")
async def get_metrics():
    """Endpoint pour les métriques simples."""
    return bot_stats.get_stats()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Endpoint pour recevoir les webhooks Telegram."""
    try:
        # Parse le JSON
        body = await request.body()
        update_data = json.loads(body.decode('utf-8'))
        
        # Crée l'objet Update
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Traite l'update
        await telegram_app.process_update(update)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Erreur lors du traitement du webhook: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


def setup_handlers():
    """Configure tous les handlers du bot Telegram."""
    global telegram_app
    
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
    
    logger.info("Handlers Telegram configurés")


async def start_command(update: Update, context) -> None:
    """Handler pour la commande /start."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="start")
    
    if not is_user_allowed(user_id):
        bot_logger.warning("Tentative d'accès non autorisée")
        await update.message.reply_text("❌ Accès refusé.")
        return
    
    bot_logger.info("Commande /start reçue")
    
    welcome_message = """
🤖 **Bot Telegram Comptables**

Bienvenue ! Ce bot vous permet de gérer facilement votre base de données d'experts-comptables dans Notion.

**Commandes disponibles :**
• `/add` - Ajouter un nouveau comptable
• `/find <terme>` - Rechercher des comptables
• `/help` - Afficher cette aide
• `/cancel` - Annuler l'opération en cours

Tapez `/add` pour commencer à ajouter un comptable !
"""
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context) -> None:
    """Handler pour la commande /help."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="help")
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Accès refusé.")
        return
    
    bot_logger.info("Commande /help reçue")
    
    help_message = """
📖 **Aide - Bot Telegram Comptables**

**Commandes principales :**

🆕 `/add` - Ajouter un comptable
Lance une conversation guidée pour ajouter un nouveau comptable à votre base Notion.

🔍 `/find <terme>` - Rechercher
Exemple: `/find Paris` ou `/find martin@email.com`
Recherche dans les noms, villes, emails et contacts.

❌ `/cancel` - Annuler
Annule la conversation en cours.

**Fonctionnalités :**
• Validation automatique des emails et téléphones
• Détection des doublons
• Normalisation des numéros français au format international
• Lien direct vers les fiches Notion créées

Pour commencer, tapez `/add` !
"""
    
    await update.message.reply_text(help_message, parse_mode="Markdown")


async def start_add_command(update: Update, context) -> int:
    """Démarre la conversation pour ajouter un comptable."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Accès refusé.")
        return ConversationHandler.END
    
    bot_logger.log_step("start", "Début de l'ajout d'un comptable")
    
    # Initialise les données de conversation
    conversation_data[user_id] = {
        "ajoute_par": update.effective_user.username or str(user_id)
    }
    
    await update.message.reply_text(
        "🏢 **Ajout d'un nouveau comptable**\n\n"
        "Étape 1/7: Quel est le **nom du cabinet** ?",
        parse_mode="Markdown"
    )
    
    return ASKING_NOM


async def handle_nom(update: Update, context) -> int:
    """Gère la saisie du nom."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    nom = update.message.text.strip()
    
    # Valide le champ obligatoire
    is_valid, error_msg = validate_required_field(nom, "nom du cabinet")
    if not is_valid:
        await update.message.reply_text(f"❌ {error_msg}\n\nVeuillez saisir le nom du cabinet :")
        return ASKING_NOM
    
    conversation_data[user_id]["nom"] = sanitize_text_field(nom)
    bot_logger.log_step("nom", f"Nom saisi: {nom}")
    
    await update.message.reply_text(
        "👤 Étape 2/7: Qui est le **contact principal** ?\n"
        "(Nom de la personne de contact)",
        parse_mode="Markdown"
    )
    
    return ASKING_CONTACT


async def handle_contact(update: Update, context) -> int:
    """Gère la saisie du contact."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    contact = update.message.text.strip()
    
    # Valide le champ obligatoire
    is_valid, error_msg = validate_required_field(contact, "contact principal")
    if not is_valid:
        await update.message.reply_text(f"❌ {error_msg}\n\nVeuillez saisir le nom du contact principal :")
        return ASKING_CONTACT
    
    conversation_data[user_id]["contact"] = sanitize_text_field(contact)
    bot_logger.log_step("contact", f"Contact saisi: {contact}")
    
    await update.message.reply_text(
        "📧 Étape 3/7: Quelle est l'**adresse email** ?\n"
        "(Tapez `-` si inconnue)",
        parse_mode="Markdown"
    )
    
    return ASKING_EMAIL


async def handle_email(update: Update, context) -> int:
    """Gère la saisie de l'email."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    email_input = update.message.text.strip()
    
    # Valide et normalise l'email
    is_valid, normalized_email, error_msg = validate_and_normalize_email(email_input)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ {error_msg}\n\n"
            "Veuillez saisir une adresse email valide ou tapez `-` si inconnue :"
        )
        return ASKING_EMAIL
    
    conversation_data[user_id]["email"] = normalized_email
    bot_logger.log_step("email", f"Email saisi: {email_input} -> {normalized_email}")
    
    await update.message.reply_text(
        "📱 Étape 4/7: Quel est le **numéro de téléphone** ?\n"
        "(Tapez `-` si inconnu)",
        parse_mode="Markdown"
    )
    
    return ASKING_TELEPHONE


async def handle_telephone(update: Update, context) -> int:
    """Gère la saisie du téléphone."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    phone_input = update.message.text.strip()
    
    # Valide et normalise le téléphone
    is_valid, normalized_phone, warning_msg = validate_and_normalize_phone(
        phone_input, config.DEFAULT_PHONE_REGION
    )
    
    conversation_data[user_id]["telephone"] = normalized_phone
    bot_logger.log_step("telephone", f"Téléphone saisi: {phone_input} -> {normalized_phone}")
    
    if warning_msg:
        bot_logger.log_step("telephone_warning", warning_msg)
    
    await update.message.reply_text(
        "🏙️ Étape 5/7: Dans quelle **ville** se trouve le cabinet ?",
        parse_mode="Markdown"
    )
    
    return ASKING_VILLE


async def handle_ville(update: Update, context) -> int:
    """Gère la saisie de la ville."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    ville = update.message.text.strip()
    
    # Valide le champ obligatoire
    is_valid, error_msg = validate_required_field(ville, "ville")
    if not is_valid:
        await update.message.reply_text(f"❌ {error_msg}\n\nVeuillez saisir la ville :")
        return ASKING_VILLE
    
    conversation_data[user_id]["ville"] = sanitize_text_field(ville)
    bot_logger.log_step("ville", f"Ville saisie: {ville}")
    
    # Crée le clavier inline pour la source
    keyboard = [
        [InlineKeyboardButton("👥 Client", callback_data="source_Client")],
        [InlineKeyboardButton("🎯 Prospect", callback_data="source_Prospect")],
        [InlineKeyboardButton("💼 LinkedIn", callback_data="source_LinkedIn")],
        [InlineKeyboardButton("📞 Appel", callback_data="source_Appel")],
        [InlineKeyboardButton("📋 Autre", callback_data="source_Autre")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📊 Étape 6/7: Quelle est la **source** de ce contact ?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    return ASKING_SOURCE


async def handle_source_selection(update: Update, context) -> int:
    """Gère la sélection de la source."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    query = update.callback_query
    await query.answer()
    
    source = query.data.replace("source_", "")
    conversation_data[user_id]["source"] = source
    
    bot_logger.log_step("source", f"Source sélectionnée: {source}")
    
    await query.edit_message_text(
        f"📊 Source sélectionnée: **{source}**\n\n"
        "📝 Étape 7/7: Avez-vous des **notes** à ajouter ?\n"
        "(Tapez `-` si aucune note)",
        parse_mode="Markdown"
    )
    
    return ASKING_NOTES


async def handle_notes(update: Update, context) -> int:
    """Gère la saisie des notes et finalise l'ajout."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    notes_input = update.message.text.strip()
    notes = sanitize_text_field(notes_input)
    
    conversation_data[user_id]["notes"] = notes
    bot_logger.log_step("notes", f"Notes saisies: {notes_input}")
    
    # Vérifie les doublons
    bot_logger.log_step("duplicate_check", "Vérification des doublons")
    
    email = conversation_data[user_id].get("email")
    nom = conversation_data[user_id].get("nom")
    ville = conversation_data[user_id].get("ville")
    
    existing_comptables = await notion_client.find_existing_comptables(
        email=email, nom=nom, ville=ville
    )
    
    if existing_comptables:
        bot_logger.log_step("duplicate_found", f"Doublon détecté: {len(existing_comptables)} résultat(s)")
        bot_stats.increment("duplicates_detected")
        
        # Affiche le premier match et propose les options
        first_match = existing_comptables[0]
        match_title = notion_client.extract_page_title(first_match)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Mettre à jour", callback_data="duplicate_update")],
            [InlineKeyboardButton("➕ Créer quand même", callback_data="duplicate_create")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ **Doublon détecté !**\n\n"
            f"Un comptable similaire existe déjà :\n"
            f"📋 **{match_title}**\n\n"
            f"Que souhaitez-vous faire ?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # Stocke l'ID de la page à mettre à jour
        conversation_data[user_id]["duplicate_page_id"] = first_match["id"]
        
        return HANDLING_DUPLICATE
    
    # Aucun doublon, crée directement
    return await create_comptable(update, context, user_id, bot_logger)


async def handle_duplicate_choice(update: Update, context) -> int:
    """Gère le choix de l'utilisateur en cas de doublon."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="add")
    
    query = update.callback_query
    await query.answer()
    
    choice = query.data.replace("duplicate_", "")
    
    if choice == "update":
        bot_logger.log_step("duplicate_choice", "Choix: mise à jour")
        return await update_existing_comptable(query, context, user_id, bot_logger)
    else:
        bot_logger.log_step("duplicate_choice", "Choix: création")
        return await create_comptable(query, context, user_id, bot_logger)


async def create_comptable(update_or_query, context, user_id: int, bot_logger: BotLoggerAdapter) -> int:
    """Crée un nouveau comptable dans Notion."""
    bot_logger.log_step("create", "Création du comptable dans Notion")
    
    comptable_data = conversation_data[user_id]
    
    success, page_url, error_msg = await notion_client.create_comptable(comptable_data)
    
    if success:
        bot_logger.log_step("create_success", f"Comptable créé: {page_url}")
        bot_stats.increment("creations")
        
        message = (
            f"✅ **Comptable créé avec succès !**\n\n"
            f"📋 **{comptable_data['nom']}**\n"
            f"👤 Contact: {comptable_data['contact']}\n"
            f"🏙️ Ville: {comptable_data['ville']}\n\n"
            f"🔗 [Voir dans Notion]({page_url})"
        )
    else:
        bot_logger.log_step("create_error", f"Erreur création: {error_msg}")
        bot_stats.increment("errors")
        
        message = f"❌ **Erreur lors de la création**\n\n{error_msg}"
    
    # Envoie le message
    if hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(message, parse_mode="Markdown")
    else:
        await update_or_query.message.reply_text(message, parse_mode="Markdown")
    
    # Nettoie les données de conversation
    if user_id in conversation_data:
        del conversation_data[user_id]
    
    return ConversationHandler.END


async def update_existing_comptable(query, context, user_id: int, bot_logger: BotLoggerAdapter) -> int:
    """Met à jour un comptable existant dans Notion."""
    bot_logger.log_step("update", "Mise à jour du comptable dans Notion")
    
    comptable_data = conversation_data[user_id]
    page_id = comptable_data["duplicate_page_id"]
    
    success, page_url, error_msg = await notion_client.update_comptable(page_id, comptable_data)
    
    if success:
        bot_logger.log_step("update_success", f"Comptable mis à jour: {page_url}")
        bot_stats.increment("updates")
        
        message = (
            f"🔄 **Comptable mis à jour avec succès !**\n\n"
            f"📋 **{comptable_data['nom']}**\n"
            f"👤 Contact: {comptable_data['contact']}\n"
            f"🏙️ Ville: {comptable_data['ville']}\n\n"
            f"🔗 [Voir dans Notion]({page_url})"
        )
    else:
        bot_logger.log_step("update_error", f"Erreur mise à jour: {error_msg}")
        bot_stats.increment("errors")
        
        message = f"❌ **Erreur lors de la mise à jour**\n\n{error_msg}"
    
    await query.edit_message_text(message, parse_mode="Markdown")
    
    # Nettoie les données de conversation
    if user_id in conversation_data:
        del conversation_data[user_id]
    
    return ConversationHandler.END


async def find_command(update: Update, context) -> None:
    """Handler pour la commande /find."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="find")
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Accès refusé.")
        return
    
    # Récupère le terme de recherche
    query_text = " ".join(context.args) if context.args else ""
    
    if not query_text.strip():
        await update.message.reply_text(
            "🔍 **Recherche de comptables**\n\n"
            "Usage: `/find <terme de recherche>`\n\n"
            "Exemples:\n"
            "• `/find Paris`\n"
            "• `/find martin@email.com`\n"
            "• `/find Dupont`",
            parse_mode="Markdown"
        )
        return
    
    bot_logger.log_step("search", f"Recherche: '{query_text}'")
    bot_stats.increment("searches")
    
    # Effectue la recherche
    results = await notion_client.search_comptables(query_text, limit=5)
    
    if not results:
        bot_logger.log_step("search_no_results", f"Aucun résultat pour: '{query_text}'")
        await update.message.reply_text(
            f"🔍 **Recherche: '{query_text}'**\n\n"
            "❌ Aucun résultat trouvé.\n\n"
            "Essayez avec d'autres termes (nom, ville, email, contact).",
            parse_mode="Markdown"
        )
        return
    
    bot_logger.log_step("search_results", f"{len(results)} résultat(s) trouvé(s)")
    
    # Formate les résultats
    message_parts = [f"🔍 **Recherche: '{query_text}'**\n"]
    message_parts.append(f"📋 **{len(results)} résultat(s) trouvé(s):**\n")
    
    for i, result in enumerate(results, 1):
        message_parts.append(f"{i}. [{result['title']}]({result['url']})")
    
    message = "\n".join(message_parts)
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def cancel_command(update: Update, context) -> int:
    """Handler pour la commande /cancel."""
    user_id = update.effective_user.id
    bot_logger = BotLoggerAdapter(logger, user_id=user_id, action="cancel")
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ Accès refusé.")
        return ConversationHandler.END
    
    bot_logger.log_step("cancel", "Conversation annulée")
    
    # Nettoie les données de conversation
    if user_id in conversation_data:
        del conversation_data[user_id]
    
    await update.message.reply_text(
        "❌ **Opération annulée**\n\n"
        "Tapez `/add` pour recommencer ou `/help` pour voir les commandes disponibles.",
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Démarrage du serveur sur {config.HOST}:{config.PORT}")
    uvicorn.run(app, host=config.HOST, port=config.PORT)

