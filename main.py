import os
import json
import time
import sqlite3
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN") or "PASTE_TOKEN_HERE"
OWNER_ID = 8468189353
DAILY_LIMIT_USER = 10
DB_FILE = "bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ================= HEALTH SERVER (KOYEB FIX) =================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 8000), HealthHandler)
    server.serve_forever()

# ================= DATABASE =================

def db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'user',
        created_at INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        user_id INTEGER,
        date TEXT,
        count INTEGER,
        PRIMARY KEY (user_id, date)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS stored_entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        value TEXT,
        raw_data TEXT,
        hits INTEGER DEFAULT 1,
        first_seen INTEGER,
        last_seen INTEGER
    )
    """)

    con.commit()
    con.close()

# ================= USERS / ROLES =================

def get_user(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None

def ensure_user(user_id: int):
    if not get_user(user_id):
        con = db()
        cur = con.cursor()
        role = "owner" if user_id == OWNER_ID else "user"
        cur.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (user_id, role, int(time.time()))
        )
        con.commit()
        con.close()

# ================= LIMITS =================

def check_limit(user_id: int) -> bool:
    role = get_user(user_id)
    if role in ("admin", "owner"):
        return True

    today = time.strftime("%Y-%m-%d")
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT count FROM requests WHERE user_id=? AND date=?",
        (user_id, today)
    )
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO requests VALUES (?, ?, ?)",
            (user_id, today, 1)
        )
        con.commit()
        con.close()
        return True

    if row[0] >= DAILY_LIMIT_USER:
        con.close()
        return False

    cur.execute(
        "UPDATE requests SET count=count+1 WHERE user_id=? AND date=?",
        (user_id, today)
    )
    con.commit()
    con.close()
    return True

# ================= OSINT CORE =================

def detect_type(text: str) -> str:
    if "@" in text and "." in text:
        return "email"
    if text.replace("+", "").isdigit():
        return "phone"
    if len(text) >= 3:
        return "username"
    return "unknown"

def search_local_db(entity_type: str, value: str) -> Dict[str, Any]:
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT hits, raw_data, first_seen, last_seen FROM stored_entities WHERE type=? AND value=?",
        (entity_type, value)
    )
    row = cur.fetchone()
    con.close()

    if not row:
        return {"found": False}

    return {
        "found": True,
        "hits": row[0],
        "data": json.loads(row[1]),
        "first_seen": row[2],
        "last_seen": row[3],
    }

def save_entity(entity_type: str, value: str, data: Dict[str, Any]):
    now = int(time.time())
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT id FROM stored_entities WHERE type=? AND value=?",
        (entity_type, value)
    )
    row = cur.fetchone()

    if row:
        cur.execute("""
        UPDATE stored_entities
        SET hits=hits+1, last_seen=?, raw_data=?
        WHERE id=?
        """, (now, json.dumps(data), row[0]))
    else:
        cur.execute("""
        INSERT INTO stored_entities
        (type, value, raw_data, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        """, (entity_type, value, json.dumps(data), now, now))

    con.commit()
    con.close()

# ================= AI SIMULATION =================

def ai_analyze(text: str) -> Dict[str, Any]:
    return {
        "intent": "osint",
        "type": detect_type(text),
        "query": text
    }

# ================= BOT HANDLERS =================

def start(update: Update, context: CallbackContext):
    ensure_user(update.effective_user.id)

    kb = ReplyKeyboardMarkup(
        [["🤖 AI", "📊 Статус"]],
        resize_keyboard=True
    )

    update.message.reply_text(
        "🤖 AI-OSINT бот\n\nНапиши будь-який запит:",
        reply_markup=kb
    )

def status(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    role = get_user(user_id)

    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stored_entities")
    entities = cur.fetchone()[0]
    con.close()

    update.message.reply_text(
        f"📊 Статус\n\n"
        f"👤 Роль: {role}\n"
        f"👥 Користувачів: {users}\n"
        f"🗃 Записів у БД: {entities}"
    )

def handle_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    ensure_user(user_id)

    text = update.message.text.strip()

    if text == "📊 Статус":
        return status(update, context)

    if not check_limit(user_id):
        update.message.reply_text("⛔ Ліміт запитів вичерпано")
        return

    ai = ai_analyze(text)

    entity_type = ai["type"]
    value = ai["query"]

    local = search_local_db(entity_type, value)

    result_data = {
        "type": entity_type,
        "value": value,
        "timestamp": int(time.time())
    }

    if local["found"]:
        result_data["history_hits"] = local["hits"]
        result_data["note"] = "Знайдено у базі"
    else:
        result_data["note"] = "Новий запис"

    save_entity(entity_type, value, result_data)

    reply = (
        f"🔎 Тип: {entity_type}\n"
        f"📌 Значення: {value}\n\n"
        f"🗃 {result_data['note']}\n"
    )

    if local["found"]:
        reply += f"🔁 Запитів раніше: {local['hits']}\n"

    update.message.reply_text(reply)

# ================= RUN =================

def main():
    init_db()

    # 🔥 запускаємо health-server для Koyeb
    threading.Thread(target=run_health_server, daemon=True).start()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
