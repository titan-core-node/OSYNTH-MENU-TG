import os
import asyncio
import logging
import time
import json
import aiosqlite

from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("TG_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", "8000"))

DB_FILE = "osynth.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ================== DATABASE ==================

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT,
            created_at INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS osint_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            entity_type TEXT,
            value TEXT,
            created_at INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            file_type TEXT,
            created_at INTEGER
        )
        """)

        await db.commit()

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT role FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()

        if not row:
            role = "owner" if user_id == OWNER_ID else "user"
            await db.execute(
                "INSERT INTO users (user_id, role, created_at) VALUES (?, ?, ?)",
                (user_id, role, int(time.time()))
            )
            await db.commit()

async def get_user_role(user_id: int) -> str:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT role FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else "user"

# ================== OSINT ==================

def detect_entity(text: str) -> str:
    if "@" in text and "." in text:
        return "email"
    if text.replace("+", "").isdigit():
        return "phone"
    if len(text) >= 3:
        return "username"
    return "unknown"

async def save_osint(user_id: int, entity_type: str, value: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO osint_queries (user_id, entity_type, value, created_at) VALUES (?, ?, ?, ?)",
            (user_id, entity_type, value, int(time.time()))
        )
        await db.commit()

# ================== BOT HANDLERS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user(user_id)

    await update.message.reply_text(
        "🤖 OSYNTH OSINT BOT\n\n"
        "🔹 Надішли текст — OSINT аналіз\n"
        "🔹 Надішли файл — він збережеться\n"
        "🔹 /status — статус\n"
        "🔹 /profile — профіль"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user(user_id)
    role = await get_user_role(user_id)

    await update.message.reply_text(
        f"👤 Профіль\n\n"
        f"ID: {user_id}\n"
        f"Роль: {role}"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_FILE) as db:
        users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        osint = await (await db.execute("SELECT COUNT(*) FROM osint_queries")).fetchone()
        files = await (await db.execute("SELECT COUNT(*) FROM files")).fetchone()

    await update.message.reply_text(
        "📊 Статус системи\n\n"
        f"👤 Користувачів: {users[0]}\n"
        f"🔎 OSINT запитів: {osint[0]}\n"
        f"📁 Файлів: {files[0]}"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user(user_id)

    text = update.message.text.strip()
    entity = detect_entity(text)

    await save_osint(user_id, entity, text)

    await update.message.reply_text(
        f"🔎 OSINT\n\n"
        f"Тип: {entity}\n"
        f"Значення: {text}\n\n"
        f"✅ Збережено в базі"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user(user_id)

    file = None
    file_type = "unknown"

    if update.message.document:
        file = update.message.document
        file_type = "document"
    elif update.message.photo:
        file = update.message.photo[-1]
        file_type = "photo"

    if not file:
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO files (user_id, file_id, file_type, created_at) VALUES (?, ?, ?, ?)",
            (user_id, file.file_id, file_type, int(time.time()))
        )
        await db.commit()

    await update.message.reply_text("📁 Файл збережено (не буде видалений)")

# ================== HTTP SERVER (KOYEB) ==================

async def health(request):
    return web.Response(text="OK")

async def start_web():
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# ================== MAIN ==================

async def main():
    await init_db()
    await start_web()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    await application.initialize()
    await application.start()

    logging.info("OSYNTH BOT STARTED")

    await application.stop_running()

if __name__ == "__main__":
    asyncio.run(main())
