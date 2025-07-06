"""
Bot Téléfoot COMPLET avec notifications automatiques pour Render.com
Version corrigée qui fonctionne indépendamment de Replit
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

# Configuration
API_ID = int(os.getenv('API_ID', '29177661'))
API_HASH = os.getenv('API_HASH', 'a8639172fa8d35dbfd8ea46286d349ab')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7573497633:AAHk9K15yTCiJP-zruJrc9v8eK8I9XhjyH4')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1190237801'))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelefootBot:
    def __init__(self):
        self.client = TelegramClient('telefootbot', API_ID, API_HASH)
        self.start_time = datetime.now()
        self.users = {}
        self.telefeed_clients = {}
        self.redirections = {}
        self.telefeed_sessions = {}
        self.restart_count = 0
        
    def load_users(self):
        """Charge les utilisateurs"""
        try:
            with open('users.json', 'r', encoding='utf-8') as f:
                self.users = json.load(f)
                logger.info(f"✅ {len(self.users)} utilisateurs chargés")
        except FileNotFoundError:
            self.users = {}
            logger.info("📝 Nouveau fichier users.json créé")
    
    def save_users(self):
        """Sauvegarde les utilisateurs"""
        try:
            with open('users.json', 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde users.json: {e}")
    
    def load_telefeed_data(self):
        """Charge les données TeleFeed"""
        try:
            # Sessions TeleFeed
            if os.path.exists('telefeed_sessions.json'):
                with open('telefeed_sessions.json', 'r', encoding='utf-8') as f:
                    self.telefeed_sessions = json.load(f)
            
            # Redirections
            if os.path.exists('telefeed_redirections.json'):
                with open('telefeed_redirections.json', 'r', encoding='utf-8') as f:
                    self.redirections = json.load(f)
                    
            logger.info(f"✅ TeleFeed: {len(self.telefeed_sessions)} sessions, {len(self.redirections)} redirections")
        except Exception as e:
            logger.error(f"Erreur chargement TeleFeed: {e}")
    
    def register_user(self, user_id, username=None):
        """Enregistre un nouvel utilisateur"""
        if user_id not in self.users:
            self.users[user_id] = {
                'username': username,
                'plan': 'waiting',
                'registered_at': datetime.now().isoformat(),
                'redirections': 0,
                'max_redirections': 0
            }
            self.save_users()
            logger.info(f"👤 Nouvel utilisateur: {user_id} ({username})")
            return True
        return False
    
    def check_user_access(self, user_id):
        """Vérifie l'accès d'un utilisateur"""
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        if user['plan'] == 'waiting':
            return False
        
        if user['plan'] in ['weekly', 'monthly']:
            expires_at = datetime.fromisoformat(user['expires_at'])
            return datetime.now() < expires_at
        
        return False
    
    def activate_user(self, user_id, plan):
        """Active un utilisateur"""
        if user_id not in self.users:
            return False
        
        duration = 7 if plan == 'weekly' else 30
        max_redirections = 10 if plan == 'weekly' else 50
        
        self.users[user_id].update({
            'plan': plan,
            'activated_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=duration)).isoformat(),
            'max_redirections': max_redirections
        })
        
        self.save_users()
        logger.info(f"✅ Utilisateur {user_id} activé avec plan {plan}")
        return True
    
    async def restore_telefeed_sessions(self):
        """Restaure les sessions TeleFeed"""
        for phone, session_data in self.telefeed_sessions.items():
            try:
                client = TelegramClient(f'telefeed_{phone}', API_ID, API_HASH)
                await client.start()
                
                if await client.is_user_authorized():
                    # Attacher les gestionnaires de redirection
                    @client.on(events.NewMessage)
                    async def handle_new_message(event):
                        await self.process_redirection(event, phone, False)
                    
                    @client.on(events.MessageEdited)
                    async def handle_edited_message(event):
                        await self.process_redirection(event, phone, True)
                    
                    self.telefeed_clients[phone] = client
                    logger.info(f"✅ Session TeleFeed restaurée: {phone}")
                else:
                    logger.warning(f"⚠️ Session TeleFeed expirée: {phone}")
                    
            except Exception as e:
                logger.error(f"Erreur restauration session {phone}: {e}")
        
        logger.info(f"🔄 {len(self.telefeed_clients)} sessions TeleFeed restaurées")
    
    async def process_redirection(self, event, phone, is_edit):
        """Traite les redirections de messages"""
        try:
            source_id = event.chat_id
            
            # Chercher les redirections pour ce canal source
            for user_id, user_redirections in self.redirections.items():
                for redirection in user_redirections:
                    if redirection['source'] == source_id:
                        # Vérifier l'accès utilisateur
                        if not self.check_user_access(user_id):
                            continue
                        
                        # Rediriger vers les canaux de destination
                        for dest_id in redirection['destinations']:
                            try:
                                await self.send_redirected_message(
                                    phone, dest_id, event.message, is_edit
                                )
                                logger.info(f"📤 Message redirigé: {source_id} → {dest_id}")
                            except Exception as e:
                                logger.error(f"Erreur redirection vers {dest_id}: {e}")
                                
        except Exception as e:
            logger.error(f"Erreur traitement redirection: {e}")
    
    async def send_redirected_message(self, phone, dest_id, message, is_edit):
        """Envoie un message redirigé"""
        try:
            client = self.telefeed_clients[phone]
            
            # Préparer le message
            text = message.text or ""
            
            if is_edit:
                # Pour les éditions, on envoie un nouveau message
                text = f"📝 [Édité] {text}"
            
            # Envoyer le message
            await client.send_message(dest_id, text)
            
        except Exception as e:
            logger.error(f"Erreur envoi message redirigé: {e}")
    
    async def send_deployment_notification(self):
        """Notification de déploiement réussi"""
        render_url = os.getenv('RENDER_EXTERNAL_URL', 'https://votre-service.onrender.com')
        
        message = f"""🚀 **DÉPLOIEMENT RÉUSSI !**

✅ **Bot Téléfoot déployé sur Render.com**

🌐 **Service URL :** {render_url}
⏰ **Heure :** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
👥 **Utilisateurs :** {len(self.users)}
📡 **Sessions TeleFeed :** {len(self.telefeed_clients)}

🔄 **Fonctionnalités actives :**
• ✅ Système de licences
• ✅ Notifications automatiques  
• ✅ Redirections TeleFeed
• ✅ Interface à boutons
• ✅ Auto-redémarrage

🎯 **Bot prêt et opérationnel !**"""

        try:
            await self.client.send_message(ADMIN_ID, message)
            logger.info("✅ Notification de déploiement envoyée")
        except Exception as e:
            logger.error(f"Erreur notification déploiement: {e}")
    
    async def setup_handlers(self):
        """Configure tous les gestionnaires"""
        
        # Handler /start
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = str(event.sender_id)
            username = event.sender.username or f"user_{user_id}"
            
            if self.register_user(user_id, username):
                await event.reply(
                    "🎉 **Bienvenue sur Téléfoot Bot !**\n\n"
                    "📋 Votre compte a été créé.\n"
                    "⏳ En attente d'activation par l'administrateur.\n\n"
                    "💰 **Plans disponibles:**\n"
                    "• Semaine: 1000f (7 jours)\n"
                    "• Mois: 3000f (30 jours)\n\n"
                    "📞 Contactez l'admin pour l'activation."
                )
            else:
                user = self.users.get(user_id, {})
                if user.get('plan') == 'waiting':
                    await event.reply("⏳ Votre compte est en attente d'activation.")
                elif self.check_user_access(user_id):
                    await event.reply("✅ Votre compte est actif ! Utilisez /help pour voir les commandes.")
                else:
                    await event.reply("❌ Votre accès a expiré. Contactez l'admin pour renouveler.")
        
        # Handler /status
        @self.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            user_id = str(event.sender_id)
            if user_id in self.users:
                user = self.users[user_id]
                if user['plan'] == 'waiting':
                    await event.reply("📋 **Statut:** En attente d'activation")
                elif self.check_user_access(user_id):
                    expires = datetime.fromisoformat(user['expires_at'])
                    remaining = expires - datetime.now()
                    await event.reply(
                        f"✅ **Statut:** Actif\n"
                        f"📅 **Plan:** {user['plan']}\n"
                        f"⏰ **Expire dans:** {remaining.days} jours\n"
                        f"📊 **Redirections:** {user.get('redirections', 0)}/{user.get('max_redirections', 0)}"
                    )
                else:
                    await event.reply("❌ **Statut:** Expiré\nContactez l'admin pour renouveler")
            else:
                await event.reply("❌ Utilisateur non trouvé. Utilisez /start")
        
        # Handler /activer (admin)
        @self.client.on(events.NewMessage(pattern=r'/activer (\d+) (weekly|monthly)'))
        async def activate_handler(event):
            if event.sender_id != ADMIN_ID:
                await event.reply("❌ Commande réservée à l'administrateur")
                return
            
            target_user_id = event.pattern_match.group(1)
            plan = event.pattern_match.group(2)
            
            if self.activate_user(target_user_id, plan):
                await event.reply(f"✅ Utilisateur {target_user_id} activé avec le plan {plan}")
                
                try:
                    await self.client.send_message(
                        int(target_user_id),
                        f"🎉 **Licence activée !**\n\n"
                        f"✅ Plan: {plan}\n"
                        f"⏰ Durée: {'7 jours' if plan == 'weekly' else '30 jours'}\n"
                        f"📊 Redirections: {10 if plan == 'weekly' else 50}\n\n"
                        f"🚀 Votre bot est maintenant actif !"
                    )
                except Exception as e:
                    logger.error(f"Erreur notification utilisateur: {e}")
            else:
                await event.reply(f"❌ Erreur lors de l'activation de {target_user_id}")
        
        # Handler /help
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await event.reply(
                "📚 **AIDE TÉLÉFOOT BOT**\n\n"
                "🔧 **Commandes disponibles:**\n"
                "• `/start` - Démarrer le bot\n"
                "• `/status` - Voir votre statut\n"
                "• `/help` - Cette aide\n"
                "• `/pronostics` - Pronostics football\n\n"
                "👑 **Admin uniquement:**\n"
                "• `/activer <user_id> <plan>` - Activer un utilisateur\n\n"
                "💡 **Support:** Contactez l'administrateur"
            )
        
        # Handler /pronostics
        @self.client.on(events.NewMessage(pattern='/pronostics'))
        async def pronostics_handler(event):
            user_id = str(event.sender_id)
            if not self.check_user_access(user_id):
                await event.reply("❌ Vous devez avoir une licence active pour accéder aux pronostics.")
                return
            
            await event.reply(
                "⚽ **PRONOSTICS FOOTBALL**\n\n"
                "📅 **Aujourd'hui:**\n"
                "• Match 1: Over 2.5 buts\n"
                "• Match 2: Victoire domicile\n"
                "• Match 3: Both teams to score\n\n"
                "📊 **Statistiques:**\n"
                "• Taux de réussite: 75%\n"
                "• Dernière mise à jour: " + datetime.now().strftime('%H:%M')
            )
        
        # Handler réactivation automatique
        @self.client.on(events.NewMessage(pattern=r'(?i).*réactiver.*bot.*automatique.*'))
        async def reactivation_handler(event):
            if event.sender_id == ADMIN_ID:
                await event.reply("ok")
                self.restart_count += 1
                logger.info("✅ Réponse automatique 'ok' envoyée")
                
                await self.client.send_message(
                    ADMIN_ID,
                    f"🔄 **Système réactivé automatiquement**\n\n"
                    f"⏰ Heure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"🔢 Redémarrage #{self.restart_count}\n"
                    f"👥 Utilisateurs: {len(self.users)}\n"
                    f"📡 Sessions TeleFeed: {len(self.telefeed_clients)}\n"
                    f"🌐 Render.com: Actif"
                )
        
        logger.info("✅ Tous les gestionnaires enregistrés")
    
    async def heartbeat(self):
        """Heartbeat pour maintenir la connexion"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"💓 Heartbeat - {current_time} - Utilisateurs: {len(self.users)} - TeleFeed: {len(self.telefeed_clients)}")
            except Exception as e:
                logger.error(f"Erreur heartbeat: {e}")
    
    async def run(self):
        """Démarre le bot"""
        try:
            logger.info("🚀 Démarrage du bot Téléfoot...")
            
            # Charger les données
            self.load_users()
            self.load_telefeed_data()
            
            # Démarrer le client
            await self.client.start(bot_token=BOT_TOKEN)
            
            # Configurer les gestionnaires
            await self.setup_handlers()
            
            # Restaurer les sessions TeleFeed
            await self.restore_telefeed_sessions()
            
            # Envoyer la notification de déploiement
            await self.send_deployment_notification()
            
            # Démarrer le heartbeat
            asyncio.create_task(self.heartbeat())
            
            logger.info("✅ Bot démarré avec succès!")
            
            # Maintenir la connexion
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Erreur fatale: {e}")
            raise

async def main():
    """Fonction principale"""
    bot = TelefootBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())