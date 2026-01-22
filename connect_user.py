import asyncio
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatAction, ParseMode
from config import OWNER_ID, MONGO_URI, MONGO_DB_NAME
from pymongo import MongoClient

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
started_users = db["started_users"]
logged_in_users = db["logged_in_users"]

# In-memory stores
active_connections = {}  # admin_id <-> user_id
pending_messages = {}    # admin_id: {msg_id: msg_text}

def setup_connect_user_handlers(app):

    @app.on_message(filters.command("connect_user") & filters.user(OWNER_ID))
    async def connect_user(client, message: Message):
        admin_id = message.chat.id

        if admin_id in active_connections:
            connected_user_id = active_connections[admin_id]
            connected_user = logged_in_users.find_one({"user_id": connected_user_id}) or \
                             started_users.find_one({"user_id": connected_user_id})
            username = connected_user.get("username", "Unknown User")
            await message.reply(
                f"❌ Already connected to {username} (`{connected_user_id}`). Use /disconnect_user to disconnect.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        await message.reply("🔗 Enter the User ID or Username to connect:")
        try:
            user_id_msg = await client.listen(admin_id, timeout=60)
            user_input = user_id_msg.text.strip()
        except asyncio.TimeoutError:
            await message.reply("⏱ Timeout! Please use /connect_user again.")
            return

        if user_input.startswith("@"):
            user_input = user_input[1:]

        query = {"username": user_input} if not user_input.isdigit() else {"user_id": int(user_input)}
        user_session = logged_in_users.find_one(query) or started_users.find_one(query)

        if not user_session:
            await message.reply("❌ User not found in database.")
            return

        user_id = user_session["user_id"]
        username = user_session.get("username", "Unknown User")

        active_connections[admin_id] = user_id
        active_connections[user_id] = admin_id

        await message.reply(f"✅ Connected with {username} (`{user_id}`).", parse_mode=ParseMode.MARKDOWN)

        await client.send_message(
            user_id,
            "⚡ Owner connected with you.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Disconnect", callback_data="disconnect_request")]
            ])
        )

    @app.on_message(filters.command("disconnect_user") & filters.user(OWNER_ID))
    async def disconnect_user(client, message: Message):
        admin_id = message.chat.id
        user_id = active_connections.pop(admin_id, None)

        if user_id:
            active_connections.pop(user_id, None)
            await message.reply("🛑 Connection Destroyed!")
            await client.send_message(user_id, "🛑 Connection Destroyed!")
        else:
            await message.reply("❌ No active connection found.")

    # ✅ OWNER ➝ USER (live text/media forwarding)
    @app.on_message(filters.private & filters.user(OWNER_ID) & ~filters.command(["connect_user", "disconnect_user", "send_msg"]))
    async def forward_owner_message(client, message: Message):
        admin_id = message.chat.id
        if admin_id not in active_connections:
            return

        user_id = active_connections[admin_id]

        try:
            await client.send_chat_action(user_id, ChatAction.TYPING)
            if message.text:
                await client.send_message(user_id, f"👤 Owner: {message.text}")
            else:
                await client.copy_message(chat_id=user_id, from_chat_id=admin_id, message_id=message.id)
        except Exception:
            await message.reply("❌ Failed to deliver the message.")

    # ✅ USER ➝ OWNER (live relay)
    @app.on_message(filters.private & ~filters.user(OWNER_ID) & ~filters.command(["send_msg"]))
    async def forward_user_message(client, message: Message):
        user_id = message.chat.id
        if user_id not in active_connections:
            return

        admin_id = active_connections[user_id]
        user = await client.get_users(user_id)
        name = user.first_name

        try:
            await client.send_chat_action(admin_id, ChatAction.TYPING)
            if message.text:
                await client.send_message(admin_id, f"💬 {name}: {message.text}")
            else:
                await client.copy_message(chat_id=admin_id, from_chat_id=user_id, message_id=message.id)
        except Exception:
            pass

    # ✅ OWNER planned message (with confirmation)
    @app.on_message(filters.command("send_msg") & filters.user(OWNER_ID))
    async def owner_message_prompt(client, message: Message):
        admin_id = message.chat.id
        if admin_id not in active_connections:
            return

        user_id = active_connections[admin_id]
        msg_text = message.text.split(None, 1)[1] if len(message.text.split()) > 1 else "📎 Media Message"

        pending_messages.setdefault(admin_id, {})[message.id] = msg_text

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Send", callback_data=f"send|{message.id}|{user_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{message.id}|{admin_id}")]
        ])
        await message.reply("Do you want to send this message?", reply_markup=keyboard)

    # ✅ USER planned message (relayed to owner with name)
    @app.on_message(filters.command("send_msg") & ~filters.user(OWNER_ID))
    async def user_send_msg_command(client, message: Message):
        user_id = message.chat.id
        if user_id not in active_connections:
            return

        admin_id = active_connections[user_id]
        msg_text = message.text.split(None, 1)[1] if len(message.text.split()) > 1 else "📎 Media Message"
        user = await client.get_users(user_id)

        try:
            await client.send_message(admin_id, f"💬 {user.first_name}: {msg_text}")
        except Exception:
            pass

    # ✅ Send via callback
    @app.on_callback_query(filters.regex("^send\\|"))
    async def send_message_callback(client, query: CallbackQuery):
        _, msg_id, user_id = query.data.split("|")
        admin_id = query.from_user.id
        msg_id = int(msg_id)
        user_id = int(user_id)

        msg_text = pending_messages.get(admin_id, {}).pop(msg_id, None) or "⚠️ Message not found!"

        try:
            await client.send_message(user_id, f"👤 Owner: {msg_text}")
        except Exception:
            pass

        if admin_id in pending_messages and not pending_messages[admin_id]:
            del pending_messages[admin_id]

        await query.message.delete()
        await client.send_message(admin_id, "✅ Message sent successfully!")

    # ✅ Cancel via callback
    @app.on_callback_query(filters.regex("^cancel\\|"))
    async def cancel_message_callback(client, query: CallbackQuery):
        _, msg_id, admin_id = query.data.split("|")
        msg_id = int(msg_id)
        admin_id = int(admin_id)

        if admin_id in pending_messages:
            pending_messages[admin_id].pop(msg_id, None)
            if not pending_messages[admin_id]:
                del pending_messages[admin_id]

        await query.message.delete()
        await client.send_message(admin_id, "❌ Message sending cancelled.")

    # ✅ Disconnect request from user
    @app.on_callback_query(filters.regex("disconnect_request"))
    async def disconnect_request_handler(client, query: CallbackQuery):
        user_id = query.from_user.id
        admin_id = active_connections.get(user_id)

        if not admin_id:
            await query.answer("⚠️ You're not currently connected.")
            return

        user = await client.get_users(user_id)
        user_name = user.first_name

        await client.send_message(
            admin_id,
            f"⚠️ {user_name} wants to disconnect.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Disconnect", callback_data=f"confirm_disconnect|{user_id}")],
                [InlineKeyboardButton("🔄 Keep Connected", callback_data=f"deny_disconnect|{user_id}")]
            ])
        )
        await query.answer("🕘 Sent disconnect request to owner.")

    @app.on_callback_query(filters.regex("^confirm_disconnect\\|"))
    async def confirm_disconnect_handler(client, query: CallbackQuery):
        _, user_id = query.data.split("|")
        user_id = int(user_id)
        admin_id = query.from_user.id

        active_connections.pop(admin_id, None)
        active_connections.pop(user_id, None)

        await query.message.delete()
        await client.send_message(admin_id, "🛑 Disconnected from user.")
        await client.send_message(user_id, "🛑 Owner disconnected the session.")

    @app.on_callback_query(filters.regex("^deny_disconnect\\|"))
    async def deny_disconnect_handler(client, query: CallbackQuery):
        _, user_id = query.data.split("|")
        user_id = int(user_id)
        admin_id = query.from_user.id

        await query.message.delete()
        await client.send_message(user_id, "🔄 Owner chose to keep the connection.")
        await client.send_message(admin_id, "✅ Connection retained with user.")
