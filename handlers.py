import asyncio
import logging
import os
import tempfile
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, CallbackQuery
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut
from io import BytesIO

logger = logging.getLogger(__name__)

class BotHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.db = bot_instance.db
        self.openrouter = bot_instance.openrouter
    
    async def _handle_cancel(self, query):
        """Handle cancel callback"""
        user_id = query.from_user.id
        session = self.bot.get_user_session(user_id)
        
        # Clean up any temporary files
        if session and session.get('image_path') and os.path.exists(session['image_path']):
            try:
                os.remove(session['image_path'])
                logger.info(f"Cleaned up temp file: {session['image_path']}")
            except Exception as e:
                logger.error(f"Failed to clean up temp file: {e}")
        
        # Clear session
        self.bot.clear_user_session(user_id)
        
        # Delete the current message (works for both text and photo messages)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Send new message instead of editing
        await query.message.get_bot().send_message(
            chat_id=query.message.chat_id,
            text="✅ Done! What would you like to do next?\n\n🎨 Choose an option:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")
            ]])
        )
    
    async def _handle_ascii_selection(self, query, callback_data):
        """Handle ASCII format selection"""
        user_id = query.from_user.id
        session = self.bot.get_user_session(user_id)
        
        aspect_ratio = "3:1" if callback_data == "ascii_banner" else "1:1"
        session.update({
            'command': 'ascii',
            'step': 'awaiting_text',
            'aspect_ratio': aspect_ratio,
            'output_type': 'banner_3_1' if aspect_ratio == "3:1" else 'pfp_1_1',
            'last_activity': datetime.now()
        })
        
        await query.edit_message_text(
            f"🎨 ASCII Art Generator\n\n"
            f"Format selected: {aspect_ratio}\n\n"
            f"Now send me the text you want to convert to ASCII art:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]])
        )
    
    async def _handle_ascii_text(self, update, session):
        """Handle ASCII text input using OpenRouter"""
        user_id = update.effective_user.id
        user_address = self.bot.get_user_address(update)
        text = update.message.text
        
        # Update session with text input
        session['text_input'] = text
        session['step'] = 'processing'
        session['output_type'] = 'banner_3_1' if session['aspect_ratio'] == '3:1' else 'pfp_1_1'
        
        # Send processing message
        processing_msg = await update.message.reply_text("🎨 Creating your ASCII masterpiece, Karwe...")
        
        try:
            # Generate ASCII art with OpenRouter
            image_data = self.bot.openrouter.generate_ascii_art(text, session['aspect_ratio'])
            
            if image_data:
                # Delete processing message
                await processing_msg.delete()
                
                # Send generated image
                await update.message.reply_photo(
                    photo=BytesIO(image_data),
                    caption=f"✅ ASCII art generated successfully!\n\nText: {text}\nFormat: {session['aspect_ratio']}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Generate Another", callback_data="ascii_again"),
                            InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")
                        ],
                        [InlineKeyboardButton("Done", callback_data="cancel")]
                    ])
                )
                
                # Record generation
                self.db.record_generation(
                    user_id, 'ascii', session['output_type'], text
                )
                
                # Clear session
                self.bot.clear_user_session(user_id)
                
            else:
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ Failed to generate ASCII art. Please try again.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Try Again", callback_data="ascii_again"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                    ]])
                )
        
        except Exception as e:
            logger.error(f"Error in ASCII generation: {e}")
            try:
                await processing_msg.delete()
            except:
                pass
            await update.message.reply_text(
                "⚠️ Generation failed due to a technical error. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Try Again", callback_data="ascii_again"),
                    InlineKeyboardButton("📞 Contact Owner", callback_data="contact_owner")
                ]])
            )
        
        finally:
            # Delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
    
    async def _handle_image_selection(self, query, callback_data):
        """Handle image format selection"""
        user_id = query.from_user.id
        session = self.bot.get_user_session(user_id)
        
        aspect_ratio = "3:1" if callback_data == "image_banner" else "1:1"
        session.update({
            'command': 'image',
            'step': 'awaiting_image',
            'aspect_ratio': aspect_ratio,
            'output_type': 'banner_3_1' if aspect_ratio == "3:1" else 'pfp_1_1',
            'last_activity': datetime.now()
        })
        
        logger.info(f"User {user_id} - Image command started, step: awaiting_image, ratio: {aspect_ratio}")
        
        await query.edit_message_text(
            f"🖼️ Image Enhancement\n\n"
            f"Format selected: {aspect_ratio}\n\n"
            f"Now send me the image you want to transform:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]])
        )
    
    async def _handle_image_upload(self, update, session):
        """Handle image upload with retry logic"""
        user_id = update.effective_user.id
        
        # Send confirmation
        await update.message.reply_text("📥 Image received, Karwe! Processing...")
        
        # Get the largest photo
        photo = update.message.photo[-1]
        
        # Download with retry logic
        max_retries = 3
        temp_path = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"User {user_id} - Attempting image download (attempt {attempt + 1}/{max_retries})")
                
                photo_file = await photo.get_file()
                
                # Create temp filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                temp_path = os.path.join(tempfile.gettempdir(), f'user_{user_id}_{timestamp}.jpg')
                
                # Download the file
                await photo_file.download_to_drive(temp_path)
                
                # Success!
                logger.info(f"User {user_id} - Image downloaded successfully to: {temp_path}")
                break
                
            except Exception as e:
                logger.error(f"User {user_id} - Download attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Wait before retrying
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
                else:
                    # All retries failed
                    await update.message.reply_text(
                        "⚠️ *Download Failed*\n\n"
                        "Sorry Karwe, I couldn't download your image after multiple attempts.\n\n"
                        "This might be due to:\n"
                        "• Slow network connection\n"
                        "• Image size too large\n"
                        "• Temporary Telegram API issue\n\n"
                        "Please try again with a smaller image or check your connection.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
        
        # Store in session
        session.update({
            'command': 'image',
            'step': 'awaiting_prompt_type',
            'image_path': temp_path,
            'image_file_id': photo.file_id,
            'last_activity': datetime.now()
        })
        
        logger.info(f"User {user_id} - Step updated to: awaiting_prompt_type")
        
        # Show prompt type selection
        keyboard = [
            [InlineKeyboardButton("✨ Use Smart Auto Prompt", callback_data='image_auto')],
            [InlineKeyboardButton("✏️ Write Custom Prompt", callback_data='image_custom_prompt')],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ *Image Saved!*\n\n"
            "How would you like me to transform it?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_image_prompt_selection(self, query, session):
        """Handle prompt type selection (auto or custom)"""
        user_id = query.from_user.id
        
        # Verify session has image
        if not session.get('image_path'):
            await query.answer()
            await query.edit_message_text(
                "❌ *Error*\n\n"
                "Image not found in session. Please start again with /image",
                parse_mode=ParseMode.MARKDOWN
            )
            self.bot.clear_user_session(user_id)
            return
        
        # Determine prompt type from callback data
        if query.data == 'image_auto':
            prompt_type = 'auto'
        elif query.data == 'image_custom_prompt':
            prompt_type = 'custom'
        else:
            await query.answer("❌ Invalid selection")
            return
        
        session['prompt_type'] = prompt_type
        
        if prompt_type == 'auto':
            # Use auto prompt - generate immediately
            session.update({
                'step': 'processing',
                'custom_prompt': None,
                'last_activity': datetime.now()
            })
            
            await query.answer()
            await query.edit_message_text(
                "🎨 *Generating Your Banner*\n\n"
                "Using Smart Auto Prompt, Karwe...\n\n"
                "This may take 20-30 seconds. Please wait! ⏳",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Get session data
            image_path = session['image_path']
            aspect_ratio = session['aspect_ratio']
            
            logger.info(f"User {user_id} - Starting auto generation")
            
            try:
                # Process the image with Gemini
                await self._process_image_enhancement(query, session)
                
                logger.info(f"User {user_id} - Generation successful")
                
            except Exception as e:
                logger.error(f"User {user_id} - Generation failed: {e}")
                await query.message.reply_text(
                    "⚠️ *Generation Failed*\n\n"
                    f"Sorry Karwe, an error occurred:\n\n`{str(e)}`\n\n"
                    "Please try again.",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        elif prompt_type == 'custom':
            # Ask for custom prompt
            session.update({
                'step': 'awaiting_custom_prompt',
                'last_activity': datetime.now()
            })
            
            await query.answer()
            await query.edit_message_text(
                "✏️ *Custom Prompt*\n\n"
                "Karwe, describe how you want your image transformed.\n\n"
                "Be specific about style, colors, composition, etc.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _handle_image_custom_prompt(self, update, session):
        """Handle custom image prompt"""
        user_id = update.effective_user.id
        user_address = self.bot.get_user_address(update)
        custom_prompt = update.message.text
        
        session.update({
            'step': 'processing',
            'custom_prompt': custom_prompt,
            'last_activity': datetime.now()
        })
        
        logger.info(f"User {user_id} - Custom prompt received: '{custom_prompt}', step: processing")
        
        processing_msg = await update.message.reply_text("🎨 Applying your custom vision, Karwe...")
        
        try:
            await self._process_image_enhancement(update, session, processing_msg)
        except Exception as e:
            logger.error(f"Error in custom image processing: {e}")
            await update.message.reply_text(
                "⚠️ Processing failed. Please try again.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Try Again", callback_data="image_again"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]])
            )
    
    async def _process_image_enhancement(self, query, session, processing_msg=None):
        """Process image enhancement using OpenRouter"""
        user_id = query.from_user.id
        
        logger.info(f"User {user_id} - Starting OpenRouter GPT-5 Image Mini generation")
        
        try:
            # Get image path and dimensions
            image_path = session.get('image_path')
            aspect_ratio = session.get('aspect_ratio')
            
            if not image_path or not os.path.exists(image_path):
                raise Exception("Image file not found")
            
            # Get target dimensions
            if aspect_ratio in ['3:1', 'banner_3_1']:
                width, height = 1500, 500
            else:
                width, height = 1000, 1000
            
            logger.info(f"User {user_id} - Target dimensions: {width}x{height}")
            
            logger.info(f"User {user_id} - Calling OpenRouter API")
            
            # Process with OpenRouter
            enhanced_data = self.bot.openrouter.enhance_image(
                image_path=image_path,
                aspect_ratio=aspect_ratio,
                custom_prompt=session.get('custom_prompt')
            )
            
            if enhanced_data:
                logger.info(f"User {user_id} - Received response, processing image")
                
                # Send enhanced image with retry logic
                await self._send_with_retry(query, enhanced_data, session)
                
                # Record generation
                self.db.record_generation(
                    user_id, 'image', session['output_type'], 
                    session.get('custom_prompt') or "Auto prompt"
                )
                
                logger.info(f"User {user_id} - Generation successful")
                
            else:
                raise Exception("OpenRouter API returned no image data")
                
        except Exception as e:
            logger.error(f"Error in image enhancement: {e}")
            await self._handle_enhancement_error(query, session, str(e))
        
        finally:
            # Clean up temporary file
            if session.get('image_path') and os.path.exists(session['image_path']):
                try:
                    os.remove(session['image_path'])
                    logger.info(f"Cleaned up temp file: {session['image_path']}")
                except Exception as e:
                    logger.error(f"Failed to clean up temp file: {e}")
            
            # Clear session
            self.bot.clear_user_session(user_id)
    
    async def _send_with_retry(self, query_or_update, image_data, session, max_retries=3):
        """Send image with retry logic for network errors"""
        
        # Determine if we got a CallbackQuery or Update
        if hasattr(query_or_update, 'message'):
            # It's a CallbackQuery
            query = query_or_update
            user_id = query.from_user.id
            message_obj = query.message
        else:
            # It's an Update object
            user_id = query_or_update.effective_user.id
            message_obj = query_or_update.message
        
        for attempt in range(max_retries):
            try:
                # Send the image as a new message
                await message_obj.reply_photo(
                    photo=BytesIO(image_data),
                    caption=f"✅ *Image Generated Successfully!*\n\n"
                            f"Format: {session.get('aspect_ratio', 'Unknown')}\n"
                            f"Prompt: {session.get('custom_prompt') or 'Auto Smart Prompt'}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Try Different Prompt", callback_data="image_custom_prompt"),
                            InlineKeyboardButton("Generate New", callback_data="image_again")
                        ],
                        [InlineKeyboardButton("Done", callback_data="cancel")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                return  # Success, exit retry loop
                
            except (NetworkError, TimedOut) as e:
                logger.warning(f"User {user_id} - Network error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    raise  # Re-raise after final attempt
            except Exception as e:
                logger.error(f"User {user_id} - Unexpected error sending image: {e}")
                raise
    
    async def _handle_enhancement_error(self, query, session, error_msg):
        """Handle enhancement errors with user-friendly messages"""
        user_id = query.from_user.id
        
        # Check for specific error types
        if "Insufficient credits" in error_msg or "402" in error_msg:
            error_text = (
                "🚫 *AI Credits Exhausted*\n\n"
                "Sorry Karwe, the AI service has run out of credits.\n\n"
                "Remaining balance: $0.00\n\n"
                "Contact @Escobaar100x to add more credits.\n\n"
                "Current cost: ~$0.01-0.02 per image"
            )
        elif "Rate limit" in error_msg or "429" in error_msg:
            error_text = (
                "⏰ *Too Many Requests*\n\n"
                "Please wait a moment before trying again, Karwe.\n\n"
                "The AI service is rate-limited to prevent abuse."
            )
        elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            error_text = (
                "⏰ *Generation Timed Out*\n\n"
                "The AI took too long to process, Karwe.\n\n"
                "Please try again with:\n"
                "• A smaller image file\n"
                "• A simpler request"
            )
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            error_text = "⚠️ Network error occurred. Please check your connection and try again."
        elif "api" in error_msg.lower() or "openrouter" in error_msg.lower():
            error_text = "⚠️ AI service temporarily unavailable. Please try again in a few minutes."
        else:
            # Generic error with details
            error_text = (
                f"⚠️ *Generation Failed*\n\n"
                f"Sorry Karwe, something went wrong:\n\n"
                f"`{error_msg}`\n\n"
                f"Please try again or contact @Escobaar100x"
            )
        
        # Delete the current message (works for both text and photo messages)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message: {e}")
        
        # Send new message instead of editing
        await query.message.get_bot().send_message(
            chat_id=query.message.chat_id,
            text=error_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Try Again", callback_data="image_again"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_generate_selection(self, query, callback_data):
        """Handle generate format selection"""
        user_id = query.from_user.id
        session = self.bot.get_user_session(user_id)
        
        aspect_ratio = "3:1" if callback_data == "generate_banner" else "1:1"
        session.update({
            'command': 'generate',
            'step': 'awaiting_text',
            'aspect_ratio': aspect_ratio,
            'output_type': 'banner_3_1' if aspect_ratio == "3:1" else 'pfp_1_1',
            'last_activity': datetime.now()
        })
        
        await query.edit_message_text(
            f"✨ AI Image Generation\n\n"
            f"Format selected: {aspect_ratio}\n\n"
            f"Describe the banner/pfp you want to create:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]])
        )
    
    async def _handle_generate_text(self, update, session):
        """Handle generate text input"""
        user_id = update.effective_user.id
        user_address = self.bot.get_user_address(update)
        prompt = update.message.text
        
        processing_msg = await update.message.reply_text("🎨 Bringing your vision to life, Karwe...")
        
        try:
            image_data = self.gemini.generate_from_text(prompt, session['aspect_ratio'])
            
            if image_data:
                await update.message.reply_photo(
                    photo=BytesIO(image_data),
                    caption=f"✅ Image generated successfully!\n\nPrompt: {prompt}\nFormat: {session['aspect_ratio']}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Refine This", callback_data="generate_refine"),
                            InlineKeyboardButton("Generate New", callback_data="generate_again")
                        ],
                        [InlineKeyboardButton("Done", callback_data="cancel")]
                    ])
                )
                
                # Record generation
                self.db.record_generation(
                    user_id, 'generate', session['output_type'], prompt
                )
                
                # Clear session
                self.bot.clear_user_session(user_id)
                
            else:
                await update.message.reply_text(
                    "❌ Failed to generate image. Please try again.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Try Again", callback_data="generate_again"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                    ]])
                )
        
        except Exception as e:
            logger.error(f"Error in image generation: {e}")
            await update.message.reply_text(
                "⚠️ Generation failed due to a technical error. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Try Again", callback_data="generate_again"),
                    InlineKeyboardButton("📞 Contact Owner", callback_data="contact_owner")
                ]])
            )
        
        finally:
            try:
                await processing_msg.delete()
            except:
                pass
    
    async def _handle_help_navigation(self, query, callback_data):
        """Handle help navigation"""
        user_address = self.bot.get_user_address(query)
        
        if callback_data == "help_ascii":
            help_text = (
                f"🎨 /ascii - ASCII Art Generator\n\n"
                f"Perfect for text-based logos and meme text banners.\n\n"
                f"How to Use:\n"
                f"1. Type /ascii\n"
                f"2. Choose aspect ratio (3:1 or 1:1)\n"
                f"3. Send your text\n"
                f"4. Receive ASCII art version\n\n"
                f"💡 Tips:\n"
                f"• Short text works best (1-8 characters)\n"
                f"• ALL CAPS for bold effect\n"
                f"• Try symbols: $ ₿ Ξ 🚀 💎\n"
                f"• Experiment with aspect ratios"
            )
            
            keyboard = [
                [InlineKeyboardButton("← Previous", callback_data="help_main")],
                [InlineKeyboardButton("Next: Image Guide →", callback_data="help_image")]
            ]
            
        elif callback_data == "help_image":
            help_text = (
                f"🖼️ /image - Image Enhancement\n\n"
                f"Extend logos or photos to perfect banner size.\n\n"
                f"How to Use:\n"
                f"1. Type /image\n"
                f"2. Choose output format\n"
                f"3. Upload your image\n"
                f"4. Select Auto or Custom prompt\n"
                f"5. Receive enhanced version\n\n"
                f"Auto Prompt Features:\n"
                f"✓ Smart background matching for logos\n"
                f"✓ Natural photo extension\n"
                f"✓ Professional quality\n"
                f"✓ No text/watermarks\n\n"
                f"Custom Prompt:\n"
                f"✏️ Describe specific changes you want"
            )
            
            keyboard = [
                [InlineKeyboardButton("← Previous", callback_data="help_ascii")],
                [InlineKeyboardButton("Next: Generate Guide →", callback_data="help_generate")]
            ]
            
        elif callback_data == "help_generate":
            help_text = (
                f"✨ /generate - AI Image Creation\n\n"
                f"Create original artwork from your imagination.\n\n"
                f"How to Use:\n"
                f"1. Type /generate\n"
                f"2. Choose aspect ratio\n"
                f"3. Describe what you want\n"
                f"4. Receive AI-generated image\n\n"
                f"💡 Prompt Tips:\n"
                f"• Be specific about style/mood\n"
                f"• Mention colors and themes\n"
                f"• Describe composition\n"
                f"• Add \"cryptocurrency\" or \"professional\" for context\n\n"
                f"Example Prompts:\n"
                f"\"Futuristic cyberpunk city with neon blue and purple colors\"\n"
                f"\"Abstract golden bull charging through digital particles\"\n"
                f"\"Dark space background with glowing green meteors\""
            )
            
            keyboard = [
                [InlineKeyboardButton("← Previous", callback_data="help_image")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
            ]
        
        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    
    async def _handle_info_access(self, query):
        """Handle info access callback"""
        info_text = (
            "🔒 About Bot Access\n\n"
            "Karwa Banner Generator is a private bot that requires owner approval for access.\n\n"
            "📋 Features:\n"
            "• Professional Dexscreener banners (3:1)\n"
            "• Square profile pictures (1:1)\n"
            "• ASCII art generation\n"
            "• Image enhancement\n"
            "• AI-powered creation\n\n"
            "⏰ Usage:\n"
            "• 1 generation per 24 hours\n"
            "• Unlimited access for owner\n\n"
            "📞 To Request Access:\n"
            "Contact @Escobaar100x\n\n"
            "The owner will review your request and add you to the allowed users list if approved."
        )
        
        await query.edit_message_text(
            info_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="main_menu")
            ]])
        )
