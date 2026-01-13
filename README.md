# Karwa Banner Generator

A professional Telegram bot for creating high-quality Dexscreener banners and profile pictures using Google's Gemini 2.5 Flash Image model.

## Features

- **ASCII Art Generation**: Convert text to stylized ASCII art images
- **Image Enhancement**: Extend and enhance existing images to perfect banner dimensions
- **AI Generation**: Create original artwork from text descriptions
- **Strict Aspect Ratios**: Enforced 3:1 (banner) and 1:1 (profile picture) formats
- **User Management**: Private bot with owner-controlled access
- **Rate Limiting**: 1 generation per 24 hours for regular users
- **Professional UI**: Clean, intuitive interface with inline keyboards

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Up Environment**:
   Copy `.env` file and configure your API keys:
   ```bash
   # Telegram Bot Token (get from @BotFather)
   TELEGRAM_BOT_TOKEN=your_bot_token
   
   # Gemini API Key (get from Google AI Studio)
   GEMINI_API_KEY=your_gemini_api_key
   
   # Owner Configuration
   OWNER_USER_ID=6942195606
   OWNER_USERNAME=Escobaar100x
   ```

3. **Run the Bot**:
   ```bash
   python bot.py
   ```

## Commands

### User Commands
- `/start` - Welcome message and access check
- `/ascii` - Convert text to ASCII art
- `/image` - Enhance/extend uploaded image
- `/generate` - Create banner/pfp from description
- `/commands` - Show all available commands
- `/help` - Detailed usage guide

### Admin Commands (Owner Only)
- `/manage` - User access management interface

## Bot Architecture

### Core Components

- **`bot.py`**: Main bot class and command routing
- **`database.py`**: SQLite database management for users and usage tracking
- **`gemini_client.py`**: Google Gemini API integration for image generation
- **`handlers.py`**: User interaction handlers
- **`admin_handlers.py`**: Administrative functions for bot owner

### Database Schema

- **`users_allowed`**: Authorized users list
- **`generation_logs`**: All generation history
- **`daily_usage`**: Rate limiting and usage counters

### API Integration

The bot uses Google's Gemini 2.5 Flash Image model for:
- Text-to-image generation
- Image enhancement and extension
- ASCII art creation

All images are post-processed to ensure exact aspect ratios (3:1 for banners, 1:1 for profile pictures).

## User Access System

### Access Levels

1. **Owner**: Unlimited access, full admin privileges
2. **Authorized Users**: 1 generation per 24 hours
3. **Unauthorized Users**: Blocked with contact information

### Rate Limiting

- Regular users: 1 generation per 24 hours
- Counter resets exactly 24 hours after last generation
- Owner has unlimited access
- All usage is logged for statistics

## Image Generation Features

### ASCII Art
- Converts text to stylized ASCII art
- Maintains exact aspect ratios
- High contrast, professional appearance
- Suitable for crypto project branding

### Image Enhancement
- Smart background matching for logos
- Natural photo extension
- Custom prompt support
- Maintains original style and quality

### AI Generation
- Text-to-image creation
- Professional cryptocurrency themes
- Custom styling and composition
- No unwanted text or watermarks

## Deployment

### Requirements
- Python 3.8+
- Telegram Bot Token
- Google Gemini API Key
- SQLite (built-in)

### Environment Variables
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_api_key
OWNER_USER_ID=your_telegram_user_id
OWNER_USERNAME=your_telegram_username
DATABASE_URL=sqlite:///karwa_bot.db
LOG_LEVEL=INFO
```

### Running the Bot
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_token"
export GEMINI_API_KEY="your_key"

# Run the bot
python bot.py
```

## Security Considerations

- API keys stored in environment variables
- User input validation and sanitization
- Rate limiting to prevent abuse
- Owner-only admin functions
- Parameterized database queries

## Logging and Monitoring

The bot logs:
- All command usage
- Generation attempts and results
- API errors and quota issues
- Unauthorized access attempts
- User management actions

## Support

For support or questions:
- Contact the bot owner: @Escobaar100x
- Check the bot's `/help` command for detailed guides
- Review error messages for specific issues

## License

This project is proprietary software for private use.
