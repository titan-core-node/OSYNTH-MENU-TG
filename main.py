from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import time

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB_NAME = "database.db"

def db():
    return sqlite3.connect(DB_NAME)

def init_db():
    c = db().cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        role TEXT,
        created_at INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS osint_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT,
        result TEXT,
        at INTEGER
    )
    """)
    c.connection.commit()
    c.connection.close()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )
