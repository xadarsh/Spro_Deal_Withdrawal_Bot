import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))  # Your Telegram API ID
API_HASH = os.getenv("API_HASH", "")    # Your Telegram API Hash
BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # Telegram Bot Token
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Telegram User ID of the bot owner

MONGO_URI = os.getenv("MONGO_URI", "")       # MongoDB connection string
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "")  # Mongo database name

# Validate required environment variables
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID, MONGO_URI, MONGO_DB_NAME]):
    missing = []
    if not API_ID: missing.append('API_ID')
    if not API_HASH: missing.append('API_HASH')
    if not BOT_TOKEN: missing.append('BOT_TOKEN')
    if not OWNER_ID: missing.append('OWNER_ID')
    if not MONGO_URI: missing.append('MONGO_URI')
    if not MONGO_DB_NAME: missing.append('MONGO_DB_NAME')
    raise ValueError(f"❌ Missing required environment variables: {', '.join(missing)}\n\nPlease set these variables in Koyeb dashboard or .env file")