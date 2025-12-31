import os
import time
import asyncio
import sqlite3
import psutil
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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
        joined_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        file_name TEXT,
        saved_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        at TEXT
    )
    """)

    c.connection.commit()
    c.connection.close()

def log(uid, action):
    c = db().cursor()
    c.execute(
        "INSERT INTO logs (user_id, action, at) VALUES (?, ?, ?)",
        (uid, action, datetime.utcnow().isoformat())
    )
    c.connection.commit()
    c.connection.close()

# ================== SECURITY ==================
def is_owner(uid: int) -> bool:
    return uid == OWNER_ID

def anti_spam(uid: int, sec=2):
    now = time.time()
    last = USER_COOLDOWN.get(uid, 0)
    if now - last < sec:
        return False
    USER_COOLDOWN[uid] = now
    return True

# ================== KEYBOARDS ==================
def main_menu(uid):
    buttons = [
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("👤 Профіль", callback_data="profile")],
        [InlineKeyboardButton("🕵️ OSINT", callback_data="osint_menu")],
    ]
    if is_owner(uid):
        buttons.append(
            [InlineKeyboardButton("🛠 Admin", callback_data="admin")]
        )
    return InlineKeyboardMarkup(buttons)

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    c = db().cursor()

    c.execute("""
        INSERT OR IGNORE INTO users
        VALUES (?, ?, ?, ?)
    """, (u.id, u.username, u.first_name, datetime.utcnow().isoformat()))

    c.connection.commit()
    c.connection.close()

    log(u.id, "start")

    await update.message.reply_text(
        "🦭 *Меню тюленя 5.0*\n\nОбери дію:",
        parse_mode="Markdown",
        reply_markup=main_menu(u.id)
    )

# ================== CALLBACK HANDLERS ==================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if not anti_spam(uid):
        return

    # ---------- BACK ----------
    if q.data == "back":
        await q.edit_message_text(
            "🦭 Головне меню:",
            reply_markup=main_menu(uid)
        )

    # ---------- STATUS ----------
    elif q.data == "status":
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        uptime = int(time.time() - START_TIME)

        c = db().cursor()
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        files = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        c.connection.close()

        await q.edit_message_text(
            f"📊 *Статус*\n\n"
            f"⏱ Uptime: {uptime}s\n"
            f"🧠 CPU: {cpu}%\n"
            f"💾 RAM: {ram}%\n"
            f"👥 Users: {users}\n"
            f"📁 Files: {files}",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    # ---------- PROFILE ----------
    elif q.data == "profile":
        u = q.from_user
        role = "OWNER" if is_owner(u.id) else "USER"

        c = db().cursor()
        joined = c.execute(
            "SELECT joined_at FROM users WHERE user_id=?",
            (u.id,)
        ).fetchone()
        c.connection.close()

        await q.edit_message_text(
            f"👤 *Профіль*\n\n"
            f"ID: `{u.id}`\n"
            f"Username: @{u.username}\n"
            f"Role: {role}\n"
            f"Joined: {joined[0] if joined else '—'}",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    # ---------- OSINT MENU ----------
    elif q.data == "osint_menu":
        await q.edit_message_text(
            "🕵️ *OSINT*\n\nНадішли ID або @username",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )
        context.user_data["osint"] = True

    # ---------- ADMIN ----------
    elif q.data == "admin" and is_owner(uid):
        c = db().cursor()
        logs = c.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        c.connection.close()

        await q.edit_message_text(
            f"🛠 *ADMIN*\n\n"
            f"🧾 Logs: {logs}\n"
            f"👑 Owner ID: {OWNER_ID}",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

# ================== OSINT TEXT ==================
async def osint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("osint"):
        return

    q = update.message.text.strip()
    c = db().cursor()

    if q.isdigit():
        res = c.execute(
            "SELECT * FROM users WHERE user_id=?",
            (int(q),)
        ).fetchone()
    else:
        res = c.execute(
            "SELECT * FROM users WHERE username LIKE ?",
            (q.replace("@", ""),)
        ).fetchone()

    c.connection.close()
    context.user_data["osint"] = False

    if not res:
        await update.message.reply_text("❌ Не знайдено")
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
        INSERT INTO files (user_id, file_id, file_name, saved_at)
        VALUES (?, ?, ?, ?)
    """, (
        u.id,
        file.file_id,
        getattr(file, "file_name", "photo"),
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
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, osint_text))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, save_file))

    await app.initialize()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
