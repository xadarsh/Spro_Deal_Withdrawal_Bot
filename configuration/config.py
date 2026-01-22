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