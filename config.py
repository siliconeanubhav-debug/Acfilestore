import os

class Config:
    API_ID = int(os.environ.get("API_ID", "1234567"))
    API_HASH = os.environ.get("API_HASH", "your_api_hash")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
    
    # Mongo Database
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://...")
    DB_NAME = os.environ.get("DB_NAME", "AC_FileStore_DB")
    
    # Telegram Channels
    DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1001234567890"))
    AUTH_CHANNEL = int(os.environ.get("AUTH_CHANNEL", "-1009876543210"))  # Force Sub Channel
    
    # Admin ID
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
    
    # Render Web Server Port
    PORT = int(os.environ.get("PORT", "8080"))
