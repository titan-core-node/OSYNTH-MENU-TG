import os
import sqlite3
import asyncio
from aiohttp import web
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =======================
# ENV
# =======================
TOKEN = os.getenv("TG_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", "8000"))

# =======================
# DATABASE
# =======================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    status TEXT DEFAULT 'active'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_id TEXT,
    file_type TEXT
)
""")

db.commit()

# =======================
# SECURITY
# =======================
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# =======================
# START / PROFILE
# =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user.id, user.username, user.first_name),
    )
    db.commit()

    keyboard = [
        [InlineKeyboardButton("👤 Профіль", callback_data="profile")],
        [InlineKeyboardButton("🕵️ OSINT", callback_data="osint")],
    ]

    await update.message.reply_text(
        "🔐 Бот активний.\nВибери дію:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cur.execute("SELECT status FROM users WHERE user_id=?", (query.from_user.id,))
    status = cur.fetchone()[0]

    await query.edit_message_text(
        f"👤 Профіль\n\n"
        f"ID: {query.from_user.id}\n"
        f"Username: @{query.from_user.username}\n"
        f"Статус: {status}"
    )

# =======================
# OSINT (BASE)
# =======================
async def osint_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🔎 Username", callback_data="osint_username")],
        [InlineKeyboardButton("📞 Телефон", callback_data="osint_phone")],
    ]

    await query.edit_message_text(
        "🕵️ OSINT-методи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def osint_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Відправ username (без @)"
    )
    context.user_data["osint"] = "username"

async def osint_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Відправ номер телефону"
    )
    context.user_data["osint"] = "phone"

async def osint_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("osint")

    if mode == "username":
        await update.message.reply_text(
            f"🔍 OSINT username:\n"
            f"- Telegram\n"
            f"- GitHub\n"
            f"- Instagram\n\n"
            f"Введено: {update.message.text}"
        )

    elif mode == "phone":
        await update.message.reply_text(
            f"📞 OSINT phone:\n"
            f"- Telegram\n"
            f"- WhatsApp\n\n"
            f"Введено: {update.message.text}"
        )

    context.user_data["osint"] = None

# =======================
# FILE SAVE (NO DELETE)
# =======================
async def save_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
    else:
        return

    cur.execute(
        "INSERT INTO files (user_id, file_id, file_type) VALUES (?, ?, ?)",
        (user_id, file_id, file_type)
    )
    db.commit()

    await update.message.reply_text("📁 Файл збережено в БД")

# =======================
# OWNER PANEL
# =======================
async def owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM files")
    files = cur.fetchone()[0]

    await update.message.reply_text(
        f"👑 Панель власника\n\n"
        f"Користувачів: {users}\n"
        f"Файлів: {files}"
    )

# =======================
# HTTP SERVER (KOYEB)
# =======================
async def health(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# =======================
# MAIN
# =======================
async def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("owner", owner))
    application.add_handler(CallbackQueryHandler(profile, pattern="profile"))
    application.add_handler(CallbackQueryHandler(osint_menu, pattern="osint"))
    application.add_handler(CallbackQueryHandler(osint_username, pattern="osint_username"))
    application.add_handler(CallbackQueryHandler(osint_phone, pattern="osint_phone"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, osint_handler))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, save_files))

    await application.initialize()
    await application.start()
    await application.bot.initialize()

    await run_web()

    await application.stop()

if __name__ == "__main__":
    asyncio.run(main())
