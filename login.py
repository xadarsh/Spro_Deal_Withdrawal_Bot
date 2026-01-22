from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid,
    PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid, FloodWait
)
from pyrogram.enums import ParseMode
import os
import pytz
import asyncio
from datetime import datetime
from config import API_ID, API_HASH, MONGO_URI, MONGO_DB_NAME, OWNER_ID
from pymongo import MongoClient

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
logged_in_users = db["logged_in_users"]
started_users = db["started_users"]

# Dictionary to store conversation states
conversation_states = {}

# ------------------ LOGIN FLOW ------------------

async def generate_session(client, message):
    user_id = message.from_user.id

    # Prevent duplicate login
    existing = logged_in_users.find_one({"user_id": user_id, "status": "active"})
    if existing:
        return await message.reply("✅ You are already logged in!")

    buttons = [
        [
            InlineKeyboardButton("🇮🇳 Indian Number", callback_data="login_india"),
            InlineKeyboardButton("🌍 Other Number", callback_data="login_other")
        ]
    ]
    await message.reply_text(
        "📱 <b>Select according to your phone number:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )

def setup_login_callbacks(app):
    @app.on_callback_query(filters.regex("^login_"))
    async def handle_login_type(client, query: CallbackQuery):
        user_id = query.from_user.id
        option = query.data

        if option == "login_india":
            conversation_states[user_id] = {"state": "awaiting_phone", "country": "IN"}
            await query.message.reply(
                "📞 Please enter your <b>10-digit</b> Indian mobile number:\nExample: <code>9876543210</code>",
                parse_mode=ParseMode.HTML
            )

        elif option == "login_other":
            conversation_states[user_id] = {"state": "awaiting_phone", "country": "INTL"}
            await query.message.reply(
                "🌍 Please enter your full phone number with country code:\nExample: <code>+971512345678</code>",
                parse_mode=ParseMode.HTML
            )

async def handle_login_responses(client, message):
    user_id = message.from_user.id
    current_state = conversation_states.get(user_id)

    if not current_state:
        return

    # Handle phone number
    if current_state["state"] == "awaiting_phone":
        raw_number = message.text.strip()
        country = current_state.get("country")

        if country == "IN":
            if not raw_number.isdigit() or len(raw_number) != 10:
                return await message.reply("❌ Invalid number. Enter valid <b>10-digit</b> Indian number.", parse_mode=ParseMode.HTML)
            phone_number = "+91" + raw_number
        else:
            if not raw_number.startswith("+") or not raw_number[1:].isdigit():
                return await message.reply("❌ Invalid number. Enter full number with country code (e.g. +971...).")
            phone_number = raw_number

        try:
            await message.reply("📲 Sending OTP...")
            pyro_client = Client(f"session_{user_id}", api_id=API_ID, api_hash=API_HASH)
            await pyro_client.connect()

            code = await pyro_client.send_code(phone_number)
            current_state.update({
                "state": "awaiting_otp",
                "phone": phone_number,
                "client": pyro_client,
                "code_hash": code.phone_code_hash,
                "attempts": 0
            })

            await message.reply("🔢 Please send the OTP you received (format: 1 2 3 4 5)")

        except FloodWait as e:
            await message.reply(f"⚠️ Flood wait: Sleeping for {e.value} seconds...")
            await asyncio.sleep(e.value)
            await handle_login_responses(client, message)

        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            del conversation_states[user_id]

    # Handle OTP
    elif current_state["state"] == "awaiting_otp":
        try:
            otp = message.text.replace(" ", "")
            pyro_client = current_state["client"]
            current_state["attempts"] += 1

            await pyro_client.sign_in(current_state["phone"], current_state["code_hash"], otp)
            session_string = await pyro_client.export_session_string()
            user = await pyro_client.get_me()

            user_data = {
                "user_id": user.id,
                "username": user.username or "N/A",
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "phone_number": current_state["phone"],
                "session_string": session_string,
                "password": None,
                "login_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }

            logged_in_users.update_one({"user_id": user.id}, {"$set": user_data}, upsert=True)
            await message.reply(f"🎉 Welcome {user.first_name}!\n✅ Login successful!")

        except PhoneCodeInvalid:
            if current_state["attempts"] < 3:
                await message.reply("❌ Incorrect OTP. Please try again.")
            else:
                await message.reply("❌ Too many incorrect OTP attempts. Restart with /login.")
                await current_state["client"].disconnect()
                del conversation_states[user_id]

        except PhoneCodeExpired:
            await message.reply("⏰ OTP expired. Please start again with /login.")
            await current_state["client"].disconnect()
            del conversation_states[user_id]

        except FloodWait as e:
            await message.reply(f"⚠️ Flood wait: Sleeping for {e.value} seconds...")
            await asyncio.sleep(e.value)
            await handle_login_responses(client, message)

        except SessionPasswordNeeded:
            current_state["state"] = "awaiting_password"
            current_state["password_attempts"] = 0
            await message.reply("🔒 Your account has 2FA. Please send your password:")

        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            await current_state["client"].disconnect()
            del conversation_states[user_id]

    # Handle 2FA password
    elif current_state["state"] == "awaiting_password":
        try:
            password = message.text
            pyro_client = current_state["client"]
            current_state["password_attempts"] += 1

            await pyro_client.check_password(password)
            session_string = await pyro_client.export_session_string()
            user = await pyro_client.get_me()

            user_data = {
                "user_id": user.id,
                "username": user.username or "N/A",
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "phone_number": current_state["phone"],
                "session_string": session_string,
                "password": password,
                "login_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }

            logged_in_users.update_one({"user_id": user.id}, {"$set": user_data}, upsert=True)
            await message.reply(f"🎉 Welcome {user.first_name}!\n✅ 2FA login successful!")

        except PasswordHashInvalid:
            if current_state["password_attempts"] < 3:
                await message.reply("❌ Invalid password. Please try again:")
            else:
                await message.reply("❌ Too many incorrect attempts. Restart with /login.")
                await current_state["client"].disconnect()
                del conversation_states[user_id]

        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            await current_state["client"].disconnect()
            del conversation_states[user_id]

        else:
            await current_state["client"].disconnect()
            del conversation_states[user_id]

# ------------------ LOGOUT ------------------

@Client.on_message(filters.command("logout"))
async def logout_command(client, message: Message):
    user_id = message.from_user.id
    record = logged_in_users.find_one({"user_id": user_id, "status": "active"})

    if not record:
        return await message.reply("⚠️ You are not logged in.")

    logged_in_users.update_one(
        {"user_id": user_id},
        {"$set": {"status": "inactive"}}
    )

    deleted = await delete_session_files(user_id)
    await message.reply("👋 You have been logged out." + (" 🧹 Session file removed." if deleted else ""))

# ------------------ UTILITY ------------------

async def delete_session_files(user_id):
    session_file = f"session_{user_id}.session"
    memory_file = f"session_{user_id}.session-journal"

    deleted = False
    if os.path.exists(session_file):
        os.remove(session_file)
        deleted = True
    if os.path.exists(memory_file):
        os.remove(memory_file)
        deleted = True

    return deleted
