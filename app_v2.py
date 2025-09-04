"""
Bot Telegram v2 - Gestion complète des contacts professionnels
Avec validation et nouveaux champs
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

import aiohttp
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# États de conversation
TYPE, NOM_STRUCTURE, TELEPHONE, EMAIL, ADRESSE, AFFAIRE_SOURCE, COMMENTAIRE, VALIDATION = range(8)

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN") 
NOTION_DB_ID = os.getenv("NOTION_DB_ID")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "").split(",")

class NotionClientV2:
    """Client Notion v2 avec nouveaux champs"""
    
    def __init__(self):
        self.token = NOTION_TOKEN
        self.database_id = NOTION_DB_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    async def add_contact(self, data: Dict[str, Any], author: str) -> bool:
        """Ajoute un contact à Notion avec tous les nouveaux champs"""
        try:
            properties = {}
            
            # Type (Select)
            if data.get("type"):
                properties["Type"] = {
                    "select": {"name": data["type"]}
                }
            
            # Nom de structure OU Nom/Prénom
            if data.get("nom_structure"):
                # Si c'est une structure
                properties["Société"] = {
                    "rich_text": [{"text": {"content": data["nom_structure"]}}]
                }
                # Nom et Prénom vides pour une structure
                properties["Nom"] = {"rich_text": []}
                properties["Prénom"] = {"rich_text": []}
            else:
                # Si c'est une personne individuelle
                if data.get("nom"):
                    properties["Nom"] = {
                        "rich_text": [{"text": {"content": data["nom"]}}]
                    }
                if data.get("prenom"):
                    properties["Prénom"] = {
                        "rich_text": [{"text": {"content": data["prenom"]}}]
                    }
                # Société vide pour une personne
                properties["Société"] = {"rich_text": []}
            
            # Téléphone (optionnel)
            if data.get("telephone"):
                properties["Phone"] = {
                    "phone_number": data["telephone"]
                }
            
            # Email (optionnel)
            if data.get("email"):
                properties["Customer Email"] = {
                    "email": data["email"]
                }
            
            # Adresse & Code postal
            if data.get("adresse"):
                properties["Localisation"] = {
                    "rich_text": [{"text": {"content": data["adresse"]}}]
                }
            
            # Nom de l'affaire/Source
            if data.get("affaire_source"):
                properties["Nom de l'affaire/Source"] = {
                    "rich_text": [{"text": {"content": data["affaire_source"]}}]
                }
            
            # Commentaire
            if data.get("commentaire"):
                properties["Commentaire"] = {
                    "rich_text": [{"text": {"content": data["commentaire"]}}]
                }
            
            # Auteur
            properties["Auteur"] = {
                "rich_text": [{"text": {"content": author}}]
            }
            
            # Date
            properties["Date"] = {
                "date": {"start": datetime.now().isoformat()[:10]}
            }
            
            # Statut par défaut
            properties["Étape de la qualification"] = {
                "select": {"name": "A contacter"}
            }
            
            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties
            }
            
            async with aiohttp.ClientSession() as session:
                url = "https://api.notion.com/v1/pages"
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        logger.info("Contact ajouté avec succès")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Erreur Notion: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout: {e}")
            return False

# Instance du client Notion
notion_client = NotionClientV2()

def check_user_authorized(user_id: str) -> bool:
    """Vérifie si l'utilisateur est autorisé"""
    return str(user_id) in ALLOWED_USER_IDS

def get_user_name(update: Update) -> str:
    """Récupère le nom de l'utilisateur pour l'auteur"""
    user = update.effective_user
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"User {user.id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Commande /start"""
    user_id = str(update.effective_user.id)
    
    if not check_user_authorized(user_id):
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à utiliser ce bot.")
        return ConversationHandler.END
    
    # Réinitialise les données
    context.user_data.clear()
    
    # Clavier pour le type
    keyboard = [
        ["Expert Comptable", "Cabinet d'experts comptables"],
        ["Avocats", "Cabinet d'avocats"],
        ["Autres"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "👋 Bonjour ! Je vais vous aider à ajouter un contact professionnel.\n\n"
        "🏢 **Quel est le type de contact ?**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le type de contact"""
    type_contact = update.message.text.strip()
    
    types_valides = ["Expert Comptable", "Cabinet d'experts comptables", "Avocats", "Cabinet d'avocats", "Autres"]
    if type_contact not in types_valides:
        await update.message.reply_text("❌ Veuillez choisir un type valide parmi les options proposées.")
        return TYPE
    
    context.user_data['type'] = type_contact
    
    # Détermine si c'est une structure ou une personne
    is_structure = "Cabinet" in type_contact
    context.user_data['is_structure'] = is_structure
    
    if is_structure:
        await update.message.reply_text(
            "✅ Type enregistré.\n\n"
            "🏢 **Nom de la structure/cabinet :**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "✅ Type enregistré.\n\n"
            "👤 **Nom et prénom** (ex: Jean Dupont) :",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
    
    return NOM_STRUCTURE

async def get_nom_structure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le nom de structure ou nom/prénom"""
    nom_complet = update.message.text.strip()
    
    if context.user_data.get('is_structure'):
        context.user_data['nom_structure'] = nom_complet
    else:
        # Sépare nom et prénom
        parts = nom_complet.split(' ', 1)
        if len(parts) >= 2:
            context.user_data['prenom'] = parts[0]
            context.user_data['nom'] = parts[1]
        else:
            context.user_data['nom'] = parts[0]
    
    # Clavier pour téléphone optionnel
    keyboard = [["Passer"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ Nom enregistré.\n\n"
        "📞 **Numéro de téléphone** (optionnel) :",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return TELEPHONE

async def get_telephone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le téléphone"""
    telephone = update.message.text.strip()
    
    if telephone != "Passer":
        context.user_data['telephone'] = telephone
    
    # Clavier pour email optionnel
    keyboard = [["Passer"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ Téléphone enregistré.\n\n"
        "📧 **Adresse email** (optionnel) :",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère l'email"""
    email = update.message.text.strip()
    
    if email != "Passer":
        # Validation basique
        if "@" not in email or "." not in email:
            await update.message.reply_text("❌ Email invalide. Veuillez saisir un email valide ou 'Passer' :")
            return EMAIL
        context.user_data['email'] = email
    
    await update.message.reply_text(
        "✅ Email enregistré.\n\n"
        "📍 **Adresse complète & code postal :**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return ADRESSE

async def get_adresse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère l'adresse"""
    context.user_data['adresse'] = update.message.text.strip()
    
    await update.message.reply_text(
        "✅ Adresse enregistrée.\n\n"
        "🤝 **Nom de l'affaire en lien ou source de recommandation :**",
        parse_mode='Markdown'
    )
    return AFFAIRE_SOURCE

async def get_affaire_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère l'affaire/source"""
    context.user_data['affaire_source'] = update.message.text.strip()
    
    # Clavier pour commentaire optionnel
    keyboard = [["Aucun commentaire"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ Source enregistrée.\n\n"
        "💬 **Commentaire** (optionnel) :",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return COMMENTAIRE

async def get_commentaire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le commentaire et affiche le récapitulatif"""
    commentaire = update.message.text.strip()
    
    if commentaire != "Aucun commentaire":
        context.user_data['commentaire'] = commentaire
    
    # Génère le récapitulatif
    data = context.user_data
    
    recap = "📋 **RÉCAPITULATIF**\n\n"
    recap += f"🏢 **Type :** {data['type']}\n"
    
    if data.get('is_structure'):
        recap += f"🏢 **Structure :** {data['nom_structure']}\n"
    else:
        nom_complet = f"{data.get('prenom', '')} {data.get('nom', '')}".strip()
        recap += f"👤 **Nom :** {nom_complet}\n"
    
    if data.get('telephone'):
        recap += f"📞 **Téléphone :** {data['telephone']}\n"
    
    if data.get('email'):
        recap += f"📧 **Email :** {data['email']}\n"
    
    recap += f"📍 **Adresse :** {data['adresse']}\n"
    recap += f"🤝 **Affaire/Source :** {data['affaire_source']}\n"
    
    if data.get('commentaire'):
        recap += f"💬 **Commentaire :** {data['commentaire']}\n"
    
    recap += f"\n👤 **Ajouté par :** {get_user_name(update)}"
    
    # Boutons de validation
    keyboard = [
        [InlineKeyboardButton("✅ Confirmer et ajouter", callback_data="confirm")],
        [InlineKeyboardButton("✏️ Modifier", callback_data="modify")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        recap,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return VALIDATION

async def handle_validation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la validation du récapitulatif"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm":
        # Ajout à Notion
        author = get_user_name(update)
        success = await notion_client.add_contact(context.user_data, author)
        
        if success:
            await query.edit_message_text(
                "🎉 **Contact ajouté avec succès !**\n\n"
                "Le contact a été enregistré dans la base Notion.\n\n"
                "Utilisez /start pour ajouter un autre contact.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **Erreur lors de l'ajout.**\n\n"
                "Une erreur s'est produite. Veuillez réessayer avec /start",
                parse_mode='Markdown'
            )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    elif query.data == "modify":
        await query.edit_message_text(
            "✏️ **Modification**\n\n"
            "Utilisez /start pour recommencer la saisie.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END
        
    elif query.data == "cancel":
        await query.edit_message_text(
            "❌ **Ajout annulé.**\n\n"
            "Utilisez /start pour recommencer.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule la conversation"""
    await update.message.reply_text(
        "❌ Ajout annulé.\n\nUtilisez /start pour recommencer.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /help"""
    help_text = """
🤖 **Bot Contacts Professionnels - Aide**

**Commandes disponibles :**
• `/start` - Ajouter un nouveau contact
• `/help` - Afficher cette aide
• `/cancel` - Annuler l'ajout en cours

**Types de contacts :**
• Expert Comptable
• Cabinet d'experts comptables  
• Avocats
• Cabinet d'avocats
• Autres

**Informations collectées :**
• Type de contact
• Nom/Prénom ou nom de structure
• Téléphone (optionnel)
• Email (optionnel)
• Adresse complète
• Affaire/Source de recommandation
• Commentaire (optionnel)

**Utilisation :**
1. Tapez `/start`
2. Suivez les instructions étape par étape
3. Validez le récapitulatif avant ajout
4. Le contact sera ajouté à Notion

**Support :** Contactez l'administrateur en cas de problème.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    """Fonction principale"""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN manquant")
        return
    
    if not NOTION_TOKEN:
        logger.error("NOTION_TOKEN manquant")
        return
    
    if not NOTION_DB_ID:
        logger.error("NOTION_DB_ID manquant")
        return
    
    logger.info("Démarrage du bot v2...")
    
    # Création de l'application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Gestionnaire de conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type)],
            NOM_STRUCTURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nom_structure)],
            TELEPHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telephone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            ADRESSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_adresse)],
            AFFAIRE_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_affaire_source)],
            COMMENTAIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_commentaire)],
            VALIDATION: [CallbackQueryHandler(handle_validation)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Ajout des handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    
    # Démarrage
    logger.info("Bot v2 démarré avec succès !")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

