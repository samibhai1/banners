#!/usr/bin/env python3
"""
Karwa Banner Generator - Professional Telegram Bot
Main entry point for the bot application
"""
import os
import sys
import logging
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# Load environment variables
load_dotenv()

# Import bot after loading environment
from bot import KarwaBannerBot

def main():
    """Main function to start the bot"""
    # Check required environment variables
    required_vars = ['TELEGRAM_BOT_TOKEN', 'OPENROUTER_API_KEY', 'OWNER_USER_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these variables in your .env file or environment.")
        sys.exit(1)
    
    # Configure logging
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('karwa_bot.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Karwa Banner Generator Bot...")
    
    # Start health check server for Render
    PORT = int(os.environ.get('PORT', 10000))
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running!')
        
        def log_message(self, format, *args):
            pass  # Suppress logs
    
    def run_health_server():
        server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
        server.serve_forever()
    
    # Start health server in background thread
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info(f"Health check server running on port {PORT}")
    
    try:
        # Create and run bot
        bot = KarwaBannerBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
