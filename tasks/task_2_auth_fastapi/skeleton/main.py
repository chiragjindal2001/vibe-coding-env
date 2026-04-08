"""
FastAPI Auth App skeleton.
TODO: Implement all routes to pass the functional tests.
"""
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="vibe-coding-secret-key-2024")

templates = Jinja2Templates(directory="templates")

# ── Pre-seeded data (do not remove alice!) ─────────────────────────────────
USERS = {
    "alice@test.com": {
        "name": "Alice Smith",
        "email": "alice@test.com",
        "password": "password123",
    }
}

ORDERS = {
    "alice@test.com": [
        {"id": 1, "item": "Laptop Pro", "status": "Delivered", "date": "2024-01-15"},
        {"id": 2, "item": "Wireless Mouse", "status": "Processing", "date": "2024-01-20"},
        {"id": 3, "item": "USB-C Hub", "status": "Shipped", "date": "2024-01-22"},
    ]
}

# ── TODO: Implement these routes ───────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse("/login")


@app.get("/login")
async def login_page(request: Request):
    # TODO: render templates/login.html
    pass


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    # TODO: check USERS dict, set request.session["user_email"], redirect to /dashboard
    pass


@app.get("/register")
async def register_page(request: Request):
    # TODO: render templates/register.html
    pass


@app.post("/register")
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    # TODO: add user to USERS dict, redirect to /login
    pass


@app.get("/dashboard")
async def dashboard(request: Request):
    # TODO: check session, get user data, render templates/dashboard.html
    pass


@app.get("/logout")
async def logout(request: Request):
    # TODO: clear session, redirect to /login
    pass
