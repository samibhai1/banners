import logging
from typing import Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

class AdminHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.db = bot_instance.db
    
    async def _show_management_menu(self, update):
        """Show management menu to owner"""
        stats = self.db.get_usage_stats()
        users = self.db.get_all_users()
        
        menu_text = (
            f"⚙️ Karwa Banner Generator - User Management\n\n"
            f"Current Statistics:\n"
            f"👥 Authorized Users: {len(users)}\n"
            f"📊 Total Generations Today: {stats['today']['total_generations']}\n"
            f"🔥 Active Users (24h): {stats['today']['active_users']}\n\n"
            f"Management Options:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("➕ Add User", callback_data="manage_add_user_start"),
                InlineKeyboardButton("➖ Remove User", callback_data="manage_remove_user")
            ],
            [
                InlineKeyboardButton("👥 View All Users", callback_data="manage_view_users"),
                InlineKeyboardButton("📊 Usage Stats", callback_data="manage_stats")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        
        if update.message:
            await update.message.reply_text(
                menu_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        else:
            await update.callback_query.edit_message_text(
                menu_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
    
    async def _handle_management_callbacks(self, query, callback_data):
        """Handle management-related callbacks"""
        user_id = query.from_user.id
        
        if callback_data == "manage_add_user_start":
            await self._start_add_user_flow(query)
        elif callback_data == "manage_remove_user":
            await self._show_remove_user_list(query)
        elif callback_data == "manage_view_users":
            await self._show_all_users(query, page=1)
        elif callback_data == "manage_stats":
            await self._show_usage_stats(query)
        elif callback_data.startswith("manage_remove_confirm_"):
            await self._confirm_remove_user(query, callback_data)
        elif callback_data.startswith("manage_remove_execute_"):
            await self._execute_remove_user(query, callback_data)
        elif callback_data.startswith("manage_users_page_"):
            page = int(callback_data.split("_")[-1])
            await self._show_all_users(query, page)
    
    async def _start_add_user_flow(self, query):
        """Start the add user flow"""
        session = self.bot.get_user_session(query.from_user.id)
        session['command'] = 'manage_add_user'
        
        await query.edit_message_text(
            "➕ Add User\n\n"
            "Send the User ID or forward a message from the user you want to add:\n\n"
            "Options:\n"
            "• Send numeric User ID (e.g., 123456789)\n"
            "• Forward any message from the user\n\n"
            "The bot will automatically extract the User ID from forwarded messages.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]])
        )
    
    async def _handle_manage_add_user(self, update, session):
        """Handle add user input"""
        user_id = update.effective_user.id
        
        # Try to extract user ID from forwarded message or direct input
        target_user_id = None
        target_username = None
        
        if update.message.forward_from:
            # Forwarded message
            target_user_id = update.message.forward_from.id
            target_username = update.message.forward_from.username or update.message.forward_from.first_name
        else:
            # Direct input - try to parse as number
            try:
                target_user_id = int(update.message.text.strip())
                target_username = f"ID_{target_user_id}"
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid User ID format.\n\n"
                    "Please send a numeric User ID (e.g., 123456789) or forward a message from the user.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                    ]])
                )
                return
        
        # Check if user already exists
        if self.db.is_user_allowed(target_user_id):
            await update.message.reply_text(
                f"⚠️ User {target_username} ({target_user_id}) is already in the allowed list.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
            self.bot.clear_user_session(user_id)
            return
        
        # Confirm addition
        session['target_user_id'] = target_user_id
        session['target_username'] = target_username
        
        await update.message.reply_text(
            f"Add user {target_username} ({target_user_id})?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"manage_add_confirm_{target_user_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ])
        )
    
    async def _confirm_add_user(self, query, callback_data):
        """Confirm adding a user"""
        user_id = query.from_user.id
        session = self.bot.get_user_session(user_id)
        
        target_user_id = session.get('target_user_id')
        target_username = session.get('target_username')
        
        if not target_user_id:
            await query.edit_message_text("❌ Session expired. Please try again.")
            return
        
        # Add user to database
        success = self.db.add_user(target_user_id, target_username, user_id)
        
        if success:
            await query.edit_message_text(
                f"✅ User {target_username} ({target_user_id}) added successfully!\n\n"
                f"They can now use the bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                f"❌ Failed to add user. They may already be in the system.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
        
        self.bot.clear_user_session(user_id)
    
    async def _show_remove_user_list(self, query):
        """Show list of users for removal"""
        users = self.db.get_all_users()
        
        if not users:
            await query.edit_message_text(
                "👥 No users found in the system.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
            return
        
        # Filter out owner
        removable_users = [u for u in users if not u['is_owner']]
        
        if not removable_users:
            await query.edit_message_text(
                "👥 No removable users found (only owner exists).",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
            return
        
        # Show first 10 users
        page_users = removable_users[:10]
        
        text = "➖ Remove User\n\n"
        keyboard = []
        
        for user in page_users:
            username_display = user['username'] or f"ID_{user['user_id']}"
            button_text = f"{username_display} - {user['user_id']}"
            
            if user['is_owner']:
                button_text += " (Owner - Cannot remove)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data="noop")])
            else:
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"manage_remove_confirm_{user['user_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _confirm_remove_user(self, query, callback_data):
        """Confirm user removal"""
        target_user_id = int(callback_data.split("_")[-1])
        
        # Get user info
        users = self.db.get_all_users()
        target_user = next((u for u in users if u['user_id'] == target_user_id), None)
        
        if not target_user:
            await query.edit_message_text("❌ User not found.")
            return
        
        if target_user['is_owner']:
            await query.edit_message_text("⛔ Cannot remove the bot owner.")
            return
        
        username_display = target_user['username'] or f"ID_{target_user_id}"
        
        await query.edit_message_text(
            f"Remove access for {username_display} ({target_user_id})?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"manage_remove_execute_{target_user_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="manage_remove_user")
                ]
            ])
        )
    
    async def _execute_remove_user(self, query, callback_data):
        """Execute user removal"""
        target_user_id = int(callback_data.split("_")[-1])
        
        # Get user info for confirmation message
        users = self.db.get_all_users()
        target_user = next((u for u in users if u['user_id'] == target_user_id), None)
        
        if not target_user:
            await query.edit_message_text("❌ User not found.")
            return
        
        username_display = target_user['username'] or f"ID_{target_user_id}"
        
        # Remove user
        success = self.db.remove_user(target_user_id)
        
        if success:
            await query.edit_message_text(
                f"❌ User {username_display} removed.\n\n"
                f"They no longer have access to the bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                f"❌ Failed to remove user {username_display}.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
    
    async def _show_all_users(self, query, page=1):
        """Show all users with pagination"""
        users = self.db.get_all_users()
        users_per_page = 10
        
        if not users:
            await query.edit_message_text(
                "👥 No users found in the system.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
                ]])
            )
            return
        
        total_pages = (len(users) + users_per_page - 1) // users_per_page
        start_idx = (page - 1) * users_per_page
        end_idx = start_idx + users_per_page
        page_users = users[start_idx:end_idx]
        
        text = f"👥 Authorized Users ({len(users)} total)\n\n"
        
        for user in page_users:
            username_display = user['username'] or "No username"
            daily_count = self.db.get_user_daily_count(user['user_id'])
            
            text += (
                f"{username_display}\n"
                f"├─ User ID: {user['user_id']}\n"
                f"├─ Added: {user['added_date'][:10]}\n"
                f"└─ Generations Today: {daily_count}/1\n\n"
            )
        
        # Navigation keyboard
        keyboard = []
        nav_row = []
        
        if page > 1:
            nav_row.append(InlineKeyboardButton("← Previous", callback_data=f"manage_users_page_{page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="noop"))
        
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next →", callback_data=f"manage_users_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    async def _show_usage_stats(self, query):
        """Show detailed usage statistics"""
        stats = self.db.get_usage_stats()
        
        text = (
            f"📊 Usage Statistics\n\n"
            f"📅 Today:\n"
            f"• Total Generations: {stats['today']['total_generations']}\n"
            f"• Active Users: {stats['today']['active_users']}\n"
        )
        
        if stats['today']['most_active']['username']:
            text += f"• Most Active: @{stats['today']['most_active']['username']} ({stats['today']['most_active']['count']} uses)\n"
        else:
            text += "• Most Active: None\n"
        
        text += (
            f"\n📈 All Time:\n"
            f"• Total Generations: {stats['all_time']['total_generations']}\n"
            f"• Total Users: {stats['all_time']['total_users']}\n"
        )
        
        if stats['all_time']['top_user']['username']:
            text += f"• Top User: @{stats['all_time']['top_user']['username']} ({stats['all_time']['top_user']['count']} generations)\n"
        else:
            text += "• Top User: None\n"
        
        text += f"\n⏰ Peak Hours: Data not available yet"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Management", callback_data="manage_menu")
            ]]),
            parse_mode=ParseMode.HTML
        )
