"""
Task definitions with framework info, descriptions, and functional test flows.
Each task has Playwright-based user flows for the functional grader.
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


# ── Helper: read requirement file safely ──────────────────────────────────

def _read_requirement(task_id: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    req_path = os.path.join(base, task_id, "requirement.txt")
    try:
        with open(req_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return f"Build the web application described for {task_id}."


# ── Helper: wait for element with short timeout ────────────────────────────

def _wait(page: Page, selector: str, timeout: int = 3000) -> bool:
    try:
        page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False


# ── Task 1: Todo HTML - Functional Flows ───────────────────────────────────

def _todo_flow_add(page: Page) -> tuple[bool, str]:
    """Add a todo item and verify it appears."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        if not _wait(page, "#todo-input"):
            return False, "Missing #todo-input"
        page.fill("#todo-input", "Buy groceries")
        if not _wait(page, "#add-btn"):
            return False, "Missing #add-btn"
        page.click("#add-btn")
        page.wait_for_timeout(500)
        items = page.query_selector_all(".todo-item")
        if not items:
            return False, "No .todo-item elements found after adding"
        text = page.inner_text("body")
        if "Buy groceries" not in text:
            return False, "Todo text not visible"
        return True, "Added todo successfully"
    except Exception as e:
        return False, f"Add flow error: {e}"


def _todo_flow_complete(page: Page) -> tuple[bool, str]:
    """Add todo then mark as complete (checkbox + .completed class)."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        _wait(page, "#todo-input")
        page.fill("#todo-input", "Test complete")
        page.click("#add-btn")
        page.wait_for_timeout(500)
        checkbox = page.query_selector(".todo-checkbox")
        if not checkbox:
            return False, "Missing .todo-checkbox"
        checkbox.click()
        page.wait_for_timeout(300)
        completed = page.query_selector(".completed")
        if not completed:
            return False, ".completed class not added after checking"
        return True, "Completed todo successfully"
    except Exception as e:
        return False, f"Complete flow error: {e}"


def _todo_flow_delete(page: Page) -> tuple[bool, str]:
    """Add todo then delete it."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        _wait(page, "#todo-input")
        page.fill("#todo-input", "Delete me")
        page.click("#add-btn")
        page.wait_for_timeout(500)
        items_before = len(page.query_selector_all(".todo-item"))
        delete_btn = page.query_selector(".delete-btn")
        if not delete_btn:
            return False, "Missing .delete-btn"
        delete_btn.click()
        page.wait_for_timeout(300)
        items_after = len(page.query_selector_all(".todo-item"))
        if items_after >= items_before:
            return False, f"Item count didn't decrease: {items_before} → {items_after}"
        return True, "Deleted todo successfully"
    except Exception as e:
        return False, f"Delete flow error: {e}"


def _todo_flow_counter(page: Page) -> tuple[bool, str]:
    """Verify counter element shows number of remaining tasks."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        counter = page.query_selector("#todo-count")
        if not counter:
            return False, "Missing #todo-count element"
        _wait(page, "#todo-input")
        page.fill("#todo-input", "Counter test")
        page.click("#add-btn")
        page.wait_for_timeout(500)
        count_text = page.inner_text("#todo-count")
        # Should contain a number
        import re
        if not re.search(r'\d', count_text):
            return False, f"Counter has no number: '{count_text}'"
        return True, f"Counter works: '{count_text}'"
    except Exception as e:
        return False, f"Counter flow error: {e}"


# ── Task 2: Auth FastAPI - Functional Flows ────────────────────────────────

def _auth_flow_register(page: Page) -> tuple[bool, str]:
    """Register a new user."""
    try:
        page.goto("http://127.0.0.1:8000/register", timeout=8000, wait_until="domcontentloaded")
        if not _wait(page, "input[name='name']"):
            return False, "Registration form not found (missing name input)"
        page.fill("input[name='name']", "Test User")
        page.fill("input[name='email']", "testuser@example.com")
        page.fill("input[name='password']", "password123")
        if not _wait(page, "#register-btn"):
            return False, "Missing #register-btn"
        page.click("#register-btn")
        page.wait_for_load_state("networkidle", timeout=5000)
        # Should redirect to login
        if "login" not in page.url and "register" in page.url:
            return False, f"Didn't redirect after register, still at: {page.url}"
        return True, "Registration successful"
    except Exception as e:
        return False, f"Register flow error: {e}"


def _auth_flow_login(page: Page) -> tuple[bool, str]:
    """Login with pre-seeded user alice."""
    try:
        page.goto("http://127.0.0.1:8000/login", timeout=8000, wait_until="domcontentloaded")
        if not _wait(page, "input[name='email']"):
            return False, "Login form not found"
        page.fill("input[name='email']", "alice@test.com")
        page.fill("input[name='password']", "password123")
        if not _wait(page, "#login-btn"):
            return False, "Missing #login-btn"
        page.click("#login-btn")
        page.wait_for_load_state("networkidle", timeout=5000)
        if "dashboard" not in page.url:
            return False, f"Didn't redirect to dashboard, at: {page.url}"
        return True, "Login successful"
    except Exception as e:
        return False, f"Login flow error: {e}"


def _auth_flow_dashboard(page: Page) -> tuple[bool, str]:
    """Login then verify dashboard shows user info and orders."""
    try:
        # Login first
        page.goto("http://127.0.0.1:8000/login", timeout=8000, wait_until="domcontentloaded")
        _wait(page, "input[name='email']")
        page.fill("input[name='email']", "alice@test.com")
        page.fill("input[name='password']", "password123")
        page.click("#login-btn")
        page.wait_for_load_state("networkidle", timeout=5000)

        if "dashboard" not in page.url:
            return False, "Couldn't reach dashboard"

        if not _wait(page, "#welcome-msg"):
            return False, "Missing #welcome-msg"
        if not _wait(page, "#orders-table"):
            return False, "Missing #orders-table"

        text = page.inner_text("body").lower()
        if "alice" not in text and "smith" not in text:
            return False, "User name not shown on dashboard"

        order_rows = page.query_selector_all(".order-row")
        if not order_rows:
            return False, "No .order-row elements found"

        return True, f"Dashboard shows user and {len(order_rows)} orders"
    except Exception as e:
        return False, f"Dashboard flow error: {e}"


def _auth_flow_logout(page: Page) -> tuple[bool, str]:
    """Login then logout, verify redirect to login."""
    try:
        page.goto("http://127.0.0.1:8000/login", timeout=8000, wait_until="domcontentloaded")
        _wait(page, "input[name='email']")
        page.fill("input[name='email']", "alice@test.com")
        page.fill("input[name='password']", "password123")
        page.click("#login-btn")
        page.wait_for_load_state("networkidle", timeout=5000)

        # Click logout
        logout = page.query_selector("#logout-link") or page.query_selector("a[href='/logout']")
        if not logout:
            return False, "No logout link found"
        logout.click()
        page.wait_for_load_state("networkidle", timeout=5000)
        if "login" not in page.url:
            return False, f"Logout didn't redirect to login, at: {page.url}"
        return True, "Logout successful"
    except Exception as e:
        return False, f"Logout flow error: {e}"


def _auth_flow_invalid_login(page: Page) -> tuple[bool, str]:
    """Login with wrong password, verify error shown."""
    try:
        page.goto("http://127.0.0.1:8000/login", timeout=8000, wait_until="domcontentloaded")
        _wait(page, "input[name='email']")
        page.fill("input[name='email']", "alice@test.com")
        page.fill("input[name='password']", "wrongpassword")
        page.click("#login-btn")
        page.wait_for_load_state("networkidle", timeout=3000)

        # Should stay on login and show error
        error_el = page.query_selector("#login-error")
        body_text = page.inner_text("body").lower()
        has_error = (
            (error_el and error_el.is_visible()) or
            "invalid" in body_text or
            "incorrect" in body_text or
            "wrong" in body_text or
            "error" in body_text
        )
        if not has_error:
            return False, "No error shown for invalid login"
        return True, "Invalid login shows error correctly"
    except Exception as e:
        return False, f"Invalid login flow error: {e}"


# ── Task 3: Notes Express - Functional Flows ───────────────────────────────

def _notes_flow_preseeded(page: Page) -> tuple[bool, str]:
    """Verify pre-seeded notes are visible on load."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)  # Let fetch complete
        if not _wait(page, "#notes-container"):
            return False, "Missing #notes-container"
        text = page.inner_text("body")
        if "Welcome" not in text:
            return False, "Pre-seeded 'Welcome' note not visible"
        if "Getting Started" not in text:
            return False, "Pre-seeded 'Getting Started' note not visible"
        cards = page.query_selector_all(".note-card")
        if len(cards) < 2:
            return False, f"Expected ≥2 note cards, found {len(cards)}"
        return True, f"Pre-seeded notes visible ({len(cards)} cards)"
    except Exception as e:
        return False, f"Pre-seeded flow error: {e}"


def _notes_flow_add(page: Page) -> tuple[bool, str]:
    """Add a new note via the UI."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        if not _wait(page, "#note-title"):
            return False, "Missing #note-title input"
        if not _wait(page, "#note-content"):
            return False, "Missing #note-content textarea"

        cards_before = len(page.query_selector_all(".note-card"))
        page.fill("#note-title", "My Test Note")
        page.fill("#note-content", "Test content here")

        if not _wait(page, "#add-note-btn"):
            return False, "Missing #add-note-btn"
        page.click("#add-note-btn")
        page.wait_for_timeout(800)

        cards_after = len(page.query_selector_all(".note-card"))
        if cards_after <= cards_before:
            return False, f"Note count didn't increase: {cards_before} → {cards_after}"
        text = page.inner_text("body")
        if "My Test Note" not in text:
            return False, "New note title not visible"
        return True, "Added note successfully"
    except Exception as e:
        return False, f"Add note flow error: {e}"


def _notes_flow_delete(page: Page) -> tuple[bool, str]:
    """Delete a note and verify removal."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        cards_before = len(page.query_selector_all(".note-card"))
        if cards_before == 0:
            return False, "No note cards to delete"

        delete_btn = page.query_selector(".delete-btn")
        if not delete_btn:
            return False, "Missing .delete-btn"
        delete_btn.click()
        page.wait_for_timeout(800)

        cards_after = len(page.query_selector_all(".note-card"))
        if cards_after >= cards_before:
            return False, f"Card count didn't decrease: {cards_before} → {cards_after}"
        return True, f"Deleted note: {cards_before} → {cards_after}"
    except Exception as e:
        return False, f"Delete note flow error: {e}"


def _notes_flow_count(page: Page) -> tuple[bool, str]:
    """Verify note count element updates."""
    try:
        page.goto("http://127.0.0.1:8000", timeout=8000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        count_el = page.query_selector("#note-count")
        if not count_el:
            return False, "Missing #note-count"

        import re
        count_text = count_el.inner_text()
        if not re.search(r'\d', count_text):
            return False, f"#note-count has no number: '{count_text}'"

        # Add a note and verify count increases
        if _wait(page, "#note-title", 2000):
            before_text = count_el.inner_text()
            page.fill("#note-title", "Count test note")
            page.fill("#note-content", "content")
            page.click("#add-note-btn")
            page.wait_for_timeout(800)
            after_text = count_el.inner_text()
            if before_text == after_text:
                return False, f"Count didn't update: '{before_text}' → '{after_text}'"

        return True, f"Note count works: '{count_text}'"
    except Exception as e:
        return False, f"Count flow error: {e}"


# ── Task Registry ──────────────────────────────────────────────────────────

TASKS = {
    "task_1_todo_html": {
        "description": _read_requirement("task_1_todo_html"),
        "framework_hint": "Plain HTML + CSS + JavaScript. Single index.html file. No frameworks.",
        "framework": "html",
        "skeleton_dir": "task_1_todo_html/skeleton",
        "flows": [
            ("add_todo", _todo_flow_add),
            ("complete_todo", _todo_flow_complete),
            ("delete_todo", _todo_flow_delete),
            ("counter_updates", _todo_flow_counter),
        ]
    },
    "task_2_auth_express": {
        "description": _read_requirement("task_2_auth_express"),
        "framework_hint": "Node.js + Express.js. Single server.js file. Run: node server.js.",
        "framework": "nodejs",
        "skeleton_dir": "task_2_auth_express/skeleton",
        "flows": [
            ("register_user", _auth_flow_register),
            ("login_valid", _auth_flow_login),
            ("dashboard_orders", _auth_flow_dashboard),
            ("logout", _auth_flow_logout),
            ("invalid_login_error", _auth_flow_invalid_login),
        ]
    },
    "task_3_notes_express": {
        "description": _read_requirement("task_3_notes_express"),
        "framework_hint": "Node.js + Express.js. Single server.js file. Run: node server.js.",
        "framework": "nodejs",
        "skeleton_dir": "task_3_notes_express/skeleton",
        "flows": [
            ("preseeded_notes", _notes_flow_preseeded),
            ("add_note", _notes_flow_add),
            ("delete_note", _notes_flow_delete),
            ("note_count", _notes_flow_count),
        ]
    }
}
