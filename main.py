from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import init_db, get_db
from auth import hash_password, verify_password

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ================= INIT =================
init_db()

# === create admin if not exists ===
db = get_db()
c = db.cursor()

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "GPT seal"

c.execute("SELECT * FROM users WHERE username=?", (ADMIN_LOGIN,))
if not c.fetchone():
    c.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (ADMIN_LOGIN, hash_password(ADMIN_PASSWORD), "admin")
    )
    db.commit()

db.close()

# ================= ROUTES =================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    user = c.fetchone()
    db.close()

    if not user:
        return RedirectResponse("/login", status_code=302)

    if not verify_password(password, user[0]):
        return RedirectResponse("/login", status_code=302)

    if user[1] == "admin":
        return RedirectResponse("/admin", status_code=302)

    return RedirectResponse("/", status_code=302)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})
