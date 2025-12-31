import os
import time
import asyncio
import sqlite3
import psutil
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
TOKEN = os.getenv("TG_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
DB_NAME = "database.db"
START_TIME = time.time()
USER_COOLDOWN = {}

# ================== DATABASE ==================
def db():
    return sqlite3.connect(DB_NAME)

def init_db():
    c = db().cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TEXT,
        last_action TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        file_name TEXT,
        file_type TEXT,
        saved_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        at TEXT
    )""")

    c.connection.commit()
    c.connection.close()

# ================== SECURITY ==================
def is_owner(uid: int):
    return uid == OWNER_ID

def anti_spam(uid: int, seconds=2):
    now = time.time()
    last = USER_COOLDOWN.get(uid, 0)
    if now - last < seconds:
        return False
    USER_COOLDOWN[uid] = now
    return True

def log(uid, action):
    c = db().cursor()
    c.execute(
        "INSERT INTO logs (user_id, action, at) VALUES (?, ?, ?)",
        (uid, action, datetime.utcnow().isoformat())
    )
    c.connection.commit()
    c.connection.close()

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user

    c = db().cursor()
    c.execute("""
        INSERT OR IGNORE INTO users
        VALUES (?, ?, ?, ?, ?)
    """, (u.id, u.username, u.first_name, datetime.utcnow().isoformat(), "start"))
    c.connection.commit()
    c.connection.close()

    log(u.id, "start")

    await update.message.reply_text(
        "🦭 *Меню тюленя 5.0*\n\n"
        "🔐 Безпека: активна\n"
        "🕵️ OSINT: доступний\n"
        "📊 /status — стан системи\n"
        "👤 /profile — профіль",
        parse_mode="Markdown"
    )

# ================== STATUS ==================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = int(time.time() - START_TIME)

    c = db().cursor()
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    files = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    c.connection.close()

    await update.message.reply_text(
        f"📊 *Статус бота*\n\n"
        f"⏱ Uptime: {uptime}s\n"
        f"🧠 CPU: {cpu}%\n"
        f"💾 RAM: {ram}%\n"
        f"👥 Users: {users}\n"
        f"📁 Files: {files}",
        parse_mode="Markdown"
    )

# ================== PROFILE ==================
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    role = "OWNER" if is_owner(u.id) else "USER"

    c = db().cursor()
    joined = c.execute(
        "SELECT joined_at FROM users WHERE user_id=?",
        (u.id,)
    ).fetchone()
    c.connection.close()

    await update.message.reply_text(
        f"👤 *Профіль*\n\n"
        f"ID: `{u.id}`\n"
        f"Username: @{u.username}\n"
        f"Role: {role}\n"
        f"Joined: {joined[0] if joined else '—'}",
        parse_mode="Markdown"
    )

# ================== OSINT ==================
async def osint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ /osint <username|id>")
        return

    q = context.args[0]
    c = db().cursor()

    if q.isdigit():
        res = c.execute(
            "SELECT * FROM users WHERE user_id=?",
            (int(q),)
        ).fetchone()
    else:
        res = c.execute(
            "SELECT * FROM users WHERE username=?",
            (q.replace("@", ""),)
        ).fetchone()

    c.connection.close()

    if not res:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text(
        f"🕵️ *OSINT RESULT*\n\n"
        f"ID: {res[0]}\n"
        f"Username: @{res[1]}\n"
        f"Name: {res[2]}\n"
        f"Joined: {res[3]}",
        parse_mode="Markdown"
    )

# ================== FILE SAVE ==================
async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    m = update.message
    file = m.document or (m.photo[-1] if m.photo else None)
    if not file:
        return

    c = db().cursor()
    c.execute("""
        INSERT INTO files (user_id, file_id, file_name, file_type, saved_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        u.id,
        file.file_id,
        getattr(file, "file_name", "photo"),
        "file",
        datetime.utcnow().isoformat()
    ))
    c.connection.commit()
    c.connection.close()

    log(u.id, "file_saved")
    await m.reply_text("📁 Файл збережено")

# ================== MAIN ==================
async def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("osint", osint))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, save_file))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
