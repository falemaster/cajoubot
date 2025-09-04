"""
Bot Telegram ultra-simplifié pour ajouter des comptables à Notion
Version minimaliste qui fonctionne avec la structure existante
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

import aiohttp
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# États de conversation
NOM, PRENOM, SOCIETE, EMAIL, TELEPHONE, VILLE = range(6)

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN") 
NOTION_DB_ID = os.getenv("NOTION_DB_ID")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "").split(",")

class SimpleNotionClient:
    """Client Notion ultra-simple"""
    
    def __init__(self):
        self.token = NOTION_TOKEN
        self.database_id = NOTION_DB_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    async def add_comptable(self, data: Dict[str, Any]) -> bool:
        """Ajoute un comptable à Notion"""
        try:
            properties = {}
            
            # Nom (rich_text)
            if data.get("nom"):
                properties["Nom"] = {
                    "rich_text": [{"text": {"content": data["nom"]}}]
                }
            
            # Prénom (rich_text)
            if data.get("prenom"):
                properties["Prénom"] = {
                    "rich_text": [{"text": {"content": data["prenom"]}}]
                }
            
            # Société (rich_text)
            if data.get("societe"):
                properties["Société"] = {
                    "rich_text": [{"text": {"content": data["societe"]}}]
                }
            
            # Customer Email (email)
            if data.get("email"):
                properties["Customer Email"] = {
                    "email": data["email"]
                }
            
            # Phone (phone_number)
            if data.get("telephone"):
                properties["Phone"] = {
                    "phone_number": data["telephone"]
                }
            
            # Localisation (rich_text)
            if data.get("ville"):
                properties["Localisation"] = {
                    "rich_text": [{"text": {"content": data["ville"]}}]
                }
            
            # Date (date)
            properties["Date"] = {
                "date": {"start": datetime.now().isoformat()[:10]}
            }
            
            # Étape de la qualification (select)
            properties["Étape de la qualification"] = {
                "select": {"name": "Nouveau"}
            }
            
            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties
            }
            
            async with aiohttp.ClientSession() as session:
                url = "https://api.notion.com/v1/pages"
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        logger.info("Comptable ajouté avec succès")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"Erreur Notion: {response.status} - {error}")
                        return False
                        
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout: {e}")
            return False

# Instance du client Notion
notion_client = SimpleNotionClient()

def check_user_authorized(user_id: str) -> bool:
    """Vérifie si l'utilisateur est autorisé"""
    return str(user_id) in ALLOWED_USER_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Commande /start"""
    user_id = str(update.effective_user.id)
    
    if not check_user_authorized(user_id):
        await update.message.reply_text("❌ Vous n'êtes pas autorisé à utiliser ce bot.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "👋 Bonjour ! Je vais vous aider à ajouter un comptable à la base Notion.\n\n"
        "📝 Commençons par le nom de famille :"
    )
    return NOM

async def get_nom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le nom"""
    context.user_data['nom'] = update.message.text.strip()
    await update.message.reply_text("✅ Nom enregistré.\n\n📝 Maintenant, le prénom :")
    return PRENOM

async def get_prenom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le prénom"""
    context.user_data['prenom'] = update.message.text.strip()
    await update.message.reply_text("✅ Prénom enregistré.\n\n🏢 Maintenant, le nom de la société :")
    return SOCIETE

async def get_societe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère la société"""
    context.user_data['societe'] = update.message.text.strip()
    await update.message.reply_text("✅ Société enregistrée.\n\n📧 Maintenant, l'adresse email :")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère l'email"""
    email = update.message.text.strip()
    
    # Validation basique de l'email
    if "@" not in email or "." not in email:
        await update.message.reply_text("❌ Email invalide. Veuillez saisir un email valide :")
        return EMAIL
    
    context.user_data['email'] = email
    await update.message.reply_text("✅ Email enregistré.\n\n📞 Maintenant, le numéro de téléphone :")
    return TELEPHONE

async def get_telephone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère le téléphone"""
    context.user_data['telephone'] = update.message.text.strip()
    await update.message.reply_text("✅ Téléphone enregistré.\n\n🏙️ Enfin, la ville :")
    return VILLE

async def get_ville(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Récupère la ville et finalise l'ajout"""
    context.user_data['ville'] = update.message.text.strip()
    
    # Récapitulatif
    data = context.user_data
    recap = f"""
✅ **Récapitulatif :**

👤 **Nom :** {data['nom']}
👤 **Prénom :** {data['prenom']}
🏢 **Société :** {data['societe']}
📧 **Email :** {data['email']}
📞 **Téléphone :** {data['telephone']}
🏙️ **Ville :** {data['ville']}

⏳ Ajout en cours à la base Notion...
"""
    
    await update.message.reply_text(recap, parse_mode='Markdown')
    
    # Ajout à Notion
    success = await notion_client.add_comptable(data)
    
    if success:
        await update.message.reply_text(
            "🎉 **Comptable ajouté avec succès !**\n\n"
            "Utilisez /start pour ajouter un autre comptable.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **Erreur lors de l'ajout.**\n\n"
            "Veuillez réessayer avec /start"
        )
    
    # Nettoyage
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule la conversation"""
    await update.message.reply_text(
        "❌ Ajout annulé.\n\nUtilisez /start pour recommencer."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /help"""
    help_text = """
🤖 **Bot Comptables - Aide**

**Commandes disponibles :**
• `/start` - Ajouter un nouveau comptable
• `/help` - Afficher cette aide
• `/cancel` - Annuler l'ajout en cours

**Utilisation :**
1. Tapez `/start`
2. Suivez les instructions
3. Remplissez les informations demandées
4. Le comptable sera ajouté automatiquement à Notion

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
    
    logger.info("Démarrage du bot...")
    
    # Création de l'application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Gestionnaire de conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nom)],
            PRENOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prenom)],
            SOCIETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_societe)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            TELEPHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_telephone)],
            VILLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ville)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Ajout des handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    
    # Démarrage
    logger.info("Bot démarré avec succès !")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

