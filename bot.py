import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from handlers import BotHandlers
from database import DatabaseManager
from openrouter_client import OpenRouterClient
from admin_handlers import AdminHandlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class KarwaBannerBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.owner_id = int(os.getenv('OWNER_USER_ID', '6942195606'))
        self.owner_username = os.getenv('OWNER_USERNAME', 'Escobaar100x')
        
        self.db = DatabaseManager()
        self.openrouter = OpenRouterClient()
        
        # Initialize handlers
        self.handlers = BotHandlers(self)
        self.admin_handlers = AdminHandlers(self)
        
        # Session management
        self.user_sessions: Dict[int, Dict[str, Any]] = {}
        
        # Commands list for bot menu
        self.commands = [
            BotCommand("start", "Start the bot and check access"),
            BotCommand("ascii", "Convert text to ASCII art"),
            BotCommand("image", "Enhance/extend uploaded image"),
            BotCommand("generate", "Create banner/pfp from description"),
            BotCommand("commands", "Show all available commands"),
            BotCommand("help", "Detailed usage guide"),
            BotCommand("manage", "User management (Owner only)"),
        ]
    
    async def post_init(self, application: Application) -> None:
        """Set bot commands after initialization"""
        await application.bot.set_my_commands(self.commands)
    
    def get_user_session(self, user_id: int) -> Dict[str, Any]:
        """Get or create user session"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        else:
            # Check for session timeout (10 minutes)
            session = self.user_sessions[user_id]
            if session.get('last_activity'):
                time_diff = datetime.now() - session['last_activity']
                if time_diff.total_seconds() > 600:  # 10 minutes
                    # Clean up any temp files
                    if session.get('image_path') and os.path.exists(session['image_path']):
                        try:
                            os.remove(session['image_path'])
                        except:
                            pass
                    # Clear expired session
                    self.user_sessions[user_id] = {}
        
        return self.user_sessions[user_id]
    
    def clear_user_session(self, user_id: int):
        """Clear user session"""
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
    
    def is_owner(self, user_id: int) -> bool:
        """Check if user is bot owner"""
        return user_id == self.owner_id
    
    def get_user_address(self, update_or_query):
        """
        Get user's display name for personalized messages.
        Handles both Update objects and CallbackQuery objects.
        """
        # Determine if we got an Update or a CallbackQuery
        if hasattr(update_or_query, 'effective_user'):
            # It's an Update object
            user = update_or_query.effective_user
        elif hasattr(update_or_query, 'from_user'):
            # It's a CallbackQuery object
            user = update_or_query.from_user
        else:
            # Fallback
            return "Karwe"
        
        # Use first name if available, otherwise username, otherwise "Karwe"
        if user.first_name:
            return user.first_name
        elif user.username:
            return user.username
        else:
            return "Karwe"
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization
        if not self.db.is_user_allowed(user_id):
            await update.message.reply_text(
                f"🔒 Access Restricted\n\n"
                f"Hey {user_address}! This bot is currently private and requires owner approval.\n\n"
                f"To request access, contact: @{self.owner_username}\n\n"
                f"[ℹ️ Learn More]",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("ℹ️ Learn More", callback_data="info_access")
                ]])
            )
            return
        
        # Get user status
        status = self.db.can_user_generate(user_id)
        daily_count = self.db.get_user_daily_count(user_id)
        
        welcome_text = (
            f"🎨 Welcome to Karwa Banner Generator, {user_address}!\n\n"
            f"Your professional tool for creating Dexscreener banners (3:1) and profile pictures (1:1) using AI.\n\n"
        )
        
        if not status['is_owner']:
            welcome_text += f"Daily Limit: {daily_count}/1 generations\n"
        
        welcome_text += (
            f"Available Commands: /commands\n"
            f"Need Help?: /help\n\n"
            f"Let's create something amazing! 🚀"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📋 View Commands", callback_data="view_commands"),
                InlineKeyboardButton("📖 Help Guide", callback_data="help_main")
            ]
        ]
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    async def ascii_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ascii command"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization and rate limit
        if not await self._check_access_and_limit(update, user_id, user_address):
            return
        
        # CREATE SESSION immediately
        self.user_sessions[user_id] = {
            'command': 'ascii',
            'step': 'awaiting_aspect_ratio',
            'aspect_ratio': None,
            'text_input': None
        }
        
        # Show aspect ratio selection
        keyboard = [
            [
                InlineKeyboardButton("3:1 Banner", callback_data="ascii_banner"),
                InlineKeyboardButton("1:1 Profile Picture", callback_data="ascii_pfp")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        await update.message.reply_text(
            f"🎨 ASCII Art Generator\n\n"
            f"{user_address}, choose your output format:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def image_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /image command or image_start callback"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization and rate limit
        if not await self._check_access_and_limit(update, user_id, user_address):
            return
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("🖼️ 3:1 Banner", callback_data='image_banner'),
                InlineKeyboardButton("⭐ 1:1 Profile Pic", callback_data='image_pfp')
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🖼️ *Image Enhancement*\n\n"
            "Transform your image into a perfect Dexscreener banner or profile picture!\n\n"
            "Choose your desired format:"
        )
        
        # Determine if this is a callback or command
        if update.callback_query:
            # It's from a callback button
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # It's from /image command
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def generate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /generate command"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization and rate limit
        if not await self._check_access_and_limit(update, user_id, user_address):
            return
        
        # Show output type selection
        keyboard = [
            [
                InlineKeyboardButton("3:1 Banner", callback_data="generate_banner"),
                InlineKeyboardButton("1:1 Profile Picture", callback_data="generate_pfp")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        await update.message.reply_text(
            f"✨ AI Image Generation\n\n"
            f"{user_address}, choose your output format:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def commands_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /commands command"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization
        if not self.db.is_user_allowed(user_id):
            await self._send_access_denied(update, user_address)
            return
        
        daily_count = self.db.get_user_daily_count(user_id)
        status = self.db.can_user_generate(user_id)
        
        commands_text = (
            f"📋 Karwa Banner Generator - Commands\n\n"
            f"🎨 Generation Commands:\n"
            f"/ascii - Convert text to ASCII art (3:1 or 1:1)\n"
            f"/image - Enhance/extend uploaded image\n"
            f"/generate - Create banner/pfp from description\n\n"
            f"ℹ️ Information:\n"
            f"/help - Detailed usage guide\n"
            f"/commands - This list\n\n"
        )
        
        if self.is_owner(user_id):
            commands_text += "⚙️ Admin (Owner Only):\n/manage - User access management\n\n"
        
        commands_text += (
            f"📊 Your Status:\n"
            f"Generations Today: {daily_count}/1\n"
        )
        
        if not status['is_owner'] and not status['can_generate']:
            # Calculate time until reset
            last_reset = status.get('last_reset')
            if last_reset:
                reset_time = last_reset + timedelta(days=1)
                time_until = reset_time - datetime.now().date()
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60
                commands_text += f"Next Reset: {hours}h {minutes}m\n"
        
        commands_text += f"\nNeed help, {user_address}? Use /help for detailed guides! 🚀"
        
        await update.message.reply_text(commands_text, parse_mode=ParseMode.HTML)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        
        # Check authorization
        if not self.db.is_user_allowed(user_id):
            await self._send_access_denied(update, user_address)
            return
        
        # Show help page 1
        help_text = (
            f"📖 Karwa Banner Generator - Help Guide\n\n"
            f"Welcome, {user_address}! This bot creates professional banners and profile pictures for Dexscreener and crypto projects.\n\n"
            f"🎯 What You Can Do:\n"
            f"• ASCII Art: Text → Stylized ASCII images\n"
            f"• Image Enhancement: Extend/improve existing images\n"
            f"• AI Generation: Text description → Custom artwork\n\n"
            f"📏 Output Formats:\n"
            f"• 3:1 Banner (Dexscreener standard)\n"
            f"• 1:1 Profile Picture (Square)\n\n"
            f"⏰ Usage Limits:\n"
            f"• 1 generation per 24 hours\n"
            f"• Counter resets exactly 24h after last use\n"
            f"• Owner has unlimited access"
        )
        
        keyboard = [
            [InlineKeyboardButton("Next: ASCII Guide →", callback_data="help_ascii")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    async def manage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /manage command (owner only)"""
        user_id = update.effective_user.id
        
        if not self.is_owner(user_id):
            await update.message.reply_text("⛔ This command is restricted to the bot owner.")
            return
        
        await self.admin_handlers._show_management_menu(update)
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_address = self.get_user_address(update)
        callback_data = query.data
        
        # HANDLE THESE FIRST - BEFORE ANY SESSION CHECK
        if callback_data == 'image_banner':
            # CREATE SESSION for image command
            self.user_sessions[user_id] = {
                'command': 'image',
                'step': 'awaiting_aspect_ratio',
                'aspect_ratio': None,
                'image_path': None
            }
            
            # Show aspect ratio buttons
            keyboard = [
                [InlineKeyboardButton("🖼️ 3:1 Banner", callback_data="banner_3x1")],
                [InlineKeyboardButton("⬜ 1:1 Profile Picture", callback_data="pfp_1x1")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
            
            await query.message.edit_text(
                "📐 Choose aspect ratio for your image:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        if callback_data in ['banner_3x1', 'pfp_1x1']:
            session = self.user_sessions.get(user_id)
            if not session:
                await query.answer("⚠️ Session expired")
                return
            
            await query.answer()
            
            # Set aspect ratio in session
            aspect_ratio = '3:1' if callback_data == 'banner_3x1' else '1:1'
            session['aspect_ratio'] = aspect_ratio
            session['step'] = 'awaiting_image'
            session['output_type'] = 'banner_3_1' if aspect_ratio == '3:1' else 'pfp_1_1'
            
            # Ask for image
            await query.message.edit_text(
                f"✅ Selected: {aspect_ratio}\n\n"
                "📤 Now send me an image to convert."
            )
            return
        
        # Get current session state
        session = self.get_user_session(user_id)
        current_step = session.get('step')
        current_command = session.get('command')
        
        logger.info(f"User {user_id} - Callback received: {callback_data}, Current step: {current_step}, Command: {current_command}")
        
        # Safety check for buttons that don't need session
        if callback_data in ['cancel', 'main_menu', 'info_access', 'view_commands', 'help_main', 'done', 'back_to_menu', 'my_generations', 'ai_generate', 'ascii_again']:
            # These buttons work without session
            if callback_data == "cancel":
                await self.handlers._handle_cancel(query)
            elif callback_data == "main_menu":
                # Handle main_menu callback separately (don't call start_command)
                await query.answer()
                
                # Clean up session
                if user_id in self.user_sessions:
                    del self.user_sessions[user_id]
                
                # Delete current message
                try:
                    await query.message.delete()
                except:
                    pass
                
                # Send main menu directly
                keyboard = [
                    [InlineKeyboardButton("🖼️ Image to Banner/PFP", callback_data="image_banner")],
                    [InlineKeyboardButton("🎨 Text to ASCII Art", callback_data="ascii_art")],
                    [InlineKeyboardButton("✨ AI Image Generator", callback_data="ai_generate")],
                    [InlineKeyboardButton("📊 My Generations", callback_data="my_generations")],
                    [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
                ]
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="👋 Welcome back!\n\n🎨 Choose an option:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            elif callback_data == "info_access":
                await self.handlers._handle_info_access(query)
            elif callback_data == "view_commands":
                await self.commands_command(update, context)
            elif callback_data == "help_main":
                help_text = """
🎨 **Karwa Banner Generator Bot**

**Features:**
• Convert images to banners (3:1) or profile pictures (1:1)
• Generate ASCII art from text
• AI image generation (coming soon)

**How to use:**
1. Choose an option from the menu
2. Follow the prompts
3. Download your result!

**Commands:**
/start - Main menu
/image - Convert image to banner/PFP
/ascii - Generate ASCII art
/help - Show this help

**Support:** @Escobaar100x
"""
                
                keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
                
                await query.message.edit_text(
                    help_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                return
            elif callback_data == "my_generations":
                await query.answer()
                await query.message.edit_text(
                    "📊 My Generations\n\n"
                    "Coming soon! This feature will show your generation history.\n\n"
                    "For now, use the menu below:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")
                    ]])
                )
                return
            elif callback_data == "ai_generate":
                await query.answer()
                await query.message.edit_text(
                    "✨ AI Image Generator\n\n"
                    "Coming soon! This feature will generate images from text prompts.\n\n"
                    "For now, use the menu below:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")
                    ]])
                )
                return
            elif callback_data == "ascii_again":
                # Reset session
                self.user_sessions[user_id] = {
                    'command': 'ascii',
                    'step': 'awaiting_aspect_ratio',
                    'aspect_ratio': None,
                    'text_input': None
                }
                
                # DELETE photo message (don't edit it)
                try:
                    await query.message.delete()
                except:
                    pass
                
                # SEND NEW message with buttons
                keyboard = [
                    [InlineKeyboardButton("🖼️ 3:1 Banner", callback_data="ascii_banner")],
                    [InlineKeyboardButton("⬜ 1:1 Profile Picture", callback_data="ascii_pfp")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ]
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📐 Choose aspect ratio for ASCII art:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            elif callback_data in ['done', 'back_to_menu']:
                # Clean up session
                if user_id in self.user_sessions:
                    session = self.user_sessions[user_id]
                    # Clean up any temp files
                    if 'image_path' in session:
                        try:
                            os.remove(session['image_path'])
                        except:
                            pass
                    del self.user_sessions[user_id]
                
                # DELETE the current message (which is a photo)
                try:
                    await query.message.delete()
                except:
                    pass
                
                # SEND NEW message with main menu (don't edit)
                keyboard = [
                    [InlineKeyboardButton("🖼️ Image to Banner/PFP", callback_data="image_banner")],
                    [InlineKeyboardButton("🎨 Text to ASCII Art", callback_data="ascii_art")],
                    [InlineKeyboardButton("✨ AI Image Generator", callback_data="ai_generate")],
                    [InlineKeyboardButton("📊 My Generations", callback_data="my_generations")],
                    [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
                ]
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="✅ Done! What would you like to do next?\n\n🎨 Choose an option:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return
        
        # Safety check for retry buttons
        if callback_data in ["image_again", "generate_again"]:
            query = update.callback_query
            await query.answer()
            
            if callback_data == "image_again":
                await self.image_command(update, context)
            elif callback_data == "generate_again":
                await self.generate_command(update, context)
            return
        
        # For all other callbacks, check if session exists
        if not session:
            logger.warning(f"User {user_id} - No session for callback: {callback_data}")
            await query.edit_message_text(
                "⚠️ Session expired. Please start again with /start",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Start Over", callback_data="main_menu")
                ]])
            )
            return
        
        # Route callback based on BOTH button data AND current session state
        
        # Start image command
        elif callback_data == "image_start":
            await self.image_command(update, context)
        
        # Aspect ratio selection - only when starting image command
        elif callback_data.startswith("image_") and current_step in [None, 'select_ratio']:
            await self.handlers._handle_image_selection(query, callback_data)
        
        # Prompt type selection - only after image has been uploaded
        elif callback_data == "image_auto" and current_step == 'awaiting_prompt_type':
            await self.handlers._handle_image_prompt_selection(query, session)
        
        elif callback_data == "image_custom_prompt" and current_step == 'awaiting_prompt_type':
            await self.handlers._handle_image_prompt_selection(query, session)
        
        # ASCII command callbacks
        elif callback_data.startswith("ascii_"):
            # Get or create session
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = {
                    'command': 'ascii',
                    'step': 'awaiting_text',
                    'aspect_ratio': None,
                    'text_input': None
                }
            
            # Set aspect ratio
            aspect_ratio = '3:1' if callback_data == 'ascii_banner' else '1:1'
            self.user_sessions[user_id]['aspect_ratio'] = aspect_ratio
            self.user_sessions[user_id]['step'] = 'awaiting_text'
            
            await query.answer()
            await query.message.edit_text(
                f"✅ Selected: {aspect_ratio}\n\n"
                "💬 Now send me the text you want to convert to ASCII art.\n\n"
                "Examples: KARWA, BITCOIN, TRUMP"
            )
            return
        
        # Generate command callbacks
        elif callback_data.startswith("generate_"):
            await self.handlers._handle_generate_selection(query, callback_data)
        
        # Help callbacks
        elif callback_data.startswith("help_"):
            await self.handlers._handle_help_navigation(query, callback_data)
        
        # Admin callbacks
        elif callback_data.startswith("manage_"):
            await self.admin_handlers._handle_management_callbacks(query, callback_data)
        
        else:
            # Invalid state or unknown callback
            logger.warning(f"User {user_id} - Invalid callback: {callback_data} at step: {current_step}")
            await query.edit_message_text(
                "⚠️ Something went wrong. Please start again with /image",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Try Again", callback_data="image_start")
                ]])
            )
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text and image messages"""
        user_id = update.effective_user.id
        session = self.get_user_session(user_id)
        
        # Check if user is in an active session
        if 'command' not in session:
            return
        
        command = session['command']
        step = session.get('step')
        
        # Route based on command and step
        if command == 'ascii' and step == 'awaiting_text':
            await self.handlers._handle_ascii_text(update, session)
        elif command == 'image' and step == 'awaiting_custom_prompt':
            await self.handlers._handle_image_custom_prompt(update, session)
        elif command == 'generate' and step == 'awaiting_text':
            await self.handlers._handle_generate_text(update, session)
        elif command == 'manage_add_user':
            await self.admin_handlers._handle_manage_add_user(update, session)
        # Legacy support for old session format
        elif command == 'ascii':
            await self.handlers._handle_ascii_text(update, session)
        elif command == 'image_custom':
            await self.handlers._handle_image_custom_prompt(update, session)
        elif command == 'generate':
            await self.handlers._handle_generate_text(update, session)
    
    async def photo_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads"""
        user_id = update.effective_user.id
        session = self.get_user_session(user_id)
        
        # Check if user is in image command and awaiting image
        if session.get('command') == 'image' and session.get('step') == 'awaiting_image':
            await self.handlers._handle_image_upload(update, session)
        else:
            # User sent photo without being in the right context
            await update.message.reply_text(
                "📸 Please use the /image command first to enhance an image.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Start /image", callback_data="image_start")
                ]])
            )
    
    async def _check_access_and_limit(self, update: Update, user_id: int, user_address: str) -> bool:
        """Check if user is authorized and within rate limits"""
        # Check authorization
        if not self.db.is_user_allowed(user_id):
            await self._send_access_denied(update, user_address)
            return False
        
        # Check rate limit
        status = self.db.can_user_generate(user_id)
        if not status['can_generate']:
            await self._send_rate_limit_exceeded(update, user_address, status)
            return False
        
        return True
    
    async def _send_access_denied(self, update: Update, user_address: str):
        """Send access denied message"""
        await update.message.reply_text(
            f"🔒 Access Restricted\n\n"
            f"Hey {user_address}! This bot is currently private and requires owner approval.\n\n"
            f"To request access, contact: @{self.owner_username}\n\n"
            f"[ℹ️ Learn More]",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ℹ️ Learn More", callback_data="info_access")
            ]])
        )
    
    async def _send_rate_limit_exceeded(self, update: Update, user_address: str, status: Dict[str, Any]):
        """Send rate limit exceeded message"""
        last_reset = status.get('last_reset')
        time_text = "24 hours"
        
        if last_reset:
            reset_time = last_reset + timedelta(days=1)
            time_until = reset_time - datetime.now().date()
            if time_until.days > 0:
                time_text = f"{time_until.days} days"
            else:
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60
                time_text = f"{hours}h {minutes}m"
        
        await update.message.reply_text(
            f"⏰ Daily Limit Reached, {user_address}!\n\n"
            f"You've already generated 1 banner today. Your limit resets in {time_text}.\n\n"
            f"Come back then to create more amazing content! 🚀",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 View My Stats", callback_data="view_commands")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help_main")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
            ])
        )
    
    def run(self):
        """Start the bot"""
        from telegram.request import HTTPXRequest
        
        # Create custom request with longer timeouts
        request = HTTPXRequest(
            connection_pool_size=8,
            connect_timeout=30.0,    # 30 seconds to establish connection
            read_timeout=60.0,       # 60 seconds to read response
            write_timeout=30.0,      # 30 seconds to write request
            pool_timeout=10.0
        )
        
        application = Application.builder().token(self.bot_token).request(request).post_init(self.post_init).build()
        
        # Add error handler
        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Log errors and notify user"""
            logger.error("Exception while handling an update:", exc_info=context.error)
            
            # Try to send error message to user
            try:
                if update and hasattr(update, 'effective_user'):
                    error_message = (
                        "⚠️ *Oops! Something went wrong*\n\n"
                        "An unexpected error occurred. Please try again.\n\n"
                        "If this keeps happening, contact @Escobaar100x"
                    )
                    
                    if hasattr(update, 'callback_query') and update.callback_query:
                        await update.callback_query.answer()
                        await update.callback_query.message.reply_text(
                            error_message,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    elif hasattr(update, 'message') and update.message:
                        await update.message.reply_text(
                            error_message,
                            parse_mode=ParseMode.MARKDOWN
                        )
            except Exception as e:
                logger.error(f"Error sending error message to user: {e}")
        
        application.add_error_handler(error_handler)
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("ascii", self.ascii_command))
        application.add_handler(CommandHandler("image", self.image_command))
        application.add_handler(CommandHandler("generate", self.generate_command))
        application.add_handler(CommandHandler("commands", self.commands_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("manage", self.manage_command))
        
        application.add_handler(CallbackQueryHandler(self.callback_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        application.add_handler(MessageHandler(filters.PHOTO, self.photo_handler))
        
        # Start bot
        logger.info("Starting Karwa Banner Generator Bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    bot = KarwaBannerBot()
    bot.run()
