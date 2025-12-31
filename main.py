import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# -----------------------------
# App init
# -----------------------------
app = FastAPI(
    title="OSINT Platform",
    description="Private OSINT platform",
    version="1.0.0"
)

templates = Jinja2Templates(directory="templates")

# -----------------------------
# Routes
# -----------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.get("/health")
async def health():
    return {"status": "ok"}

# -----------------------------
# Run (local only)
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
