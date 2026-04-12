---
title: Vibe Coding Env
emoji: 🖥️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
tags:
  - openenv
  - reinforcement-learning
  - vibe-coding
  - web-development
---

# vibe-coding-env

A web-development training environment for [OpenEnv](https://huggingface.co/openenv).
An AI agent writes real web application code, sees it running in a live headless browser, and gets scored on whether it actually works — end to end.

Built for reinforcement learning: every `write_file` action returns a **partial reward signal** (fast 2-check probe), and a full Playwright-based grade is issued on `declare_done`.

---

## Why This Environment Is Useful

**Real execution, not simulation.**
The agent's code is actually served by a live web server (Python `http.server`, Node.js/Express, or uvicorn). A real Chromium browser navigates to it, clicks buttons, fills forms, and verifies outcomes — exactly like a human QA tester would.

**Meaningful reward at every step.**
Most coding environments only reward at the end. Here, after every `write_file` the environment runs a fast 2-check probe (~0.5 s total): is the server responding? Is the primary UI element usable? This gives the RL agent a training signal mid-episode, not just at the end.

**Multi-framework coverage.**
Three tasks span plain HTML/JS, Node.js/Express REST APIs, and session-based auth — so the agent must generalize across tech stacks, not memorize one pattern.

**Grounded in browser interaction.**
The agent can navigate, click, fill inputs, evaluate JavaScript, and read page text via real Playwright actions — the same tools a human developer uses to verify their work in the browser.

**Structured, reproducible scoring.**
Every submission produces the same decomposed score: Functional (Playwright flows) + Code Quality (static analysis) + Visual (DOM heuristics). This makes progress measurable and comparable across runs.

**Safe sandbox.**
Each episode gets a fresh temporary workspace. The agent cannot escape the workspace (path traversal is blocked), and only safe shell commands (`ls`, `cat`, `node --check`, etc.) are permitted.

---

## Tasks

### Task 1 — Todo List `(HTML + JavaScript)` · Easy

Build a fully functional todo list in a **single `index.html`** file — no frameworks, no build step.

| What the grader checks | Element |
|---|---|
| Add a todo item | `#todo-input` + `#add-btn` → `.todo-item` appears |
| Mark complete | `.todo-checkbox` click → `.todo-item` gets class `completed` |
| Delete a todo | `.delete-btn` click → `.todo-item` removed from DOM |
| Live counter | `#todo-count` updates to show remaining incomplete todos |

The agent must implement all CRUD behavior with vanilla JS and make the page look reasonable with CSS.

---

### Task 2 — Auth System `(Node.js + Express.js)` · Medium

Build a session-based authentication web app in a **single `server.js`** file.

| Route | Behaviour |
|---|---|
| `GET /login` | Login form with `input[name=email]`, `input[name=password]`, `#login-btn`, `#login-error` |
| `POST /login` | Authenticate → redirect to `/dashboard`, or show error |
| `GET /register` | Registration form with `input[name=name]`, `input[name=email]`, `input[name=password]`, `#register-btn` |
| `POST /register` | Create user → redirect to `/login` |
| `GET /dashboard` | Protected — shows `#welcome-msg`, `#orders-table`, `.order-row` per order, `#logout-link` |
| `GET /logout` | Destroy session → redirect to `/login` |

Pre-seeded user: **Alice Smith** (`alice@test.com` / `password123`) with 2 orders.
Sessions managed with `express-session`.

---

### Task 3 — Notes App `(Node.js + Express.js)` · Hard

Build a notes app with a REST API backend and a fetch-based frontend, all in a **single `server.js`** file.

| API Endpoint | Behaviour |
|---|---|
| `GET /api/notes` | Return JSON array of all notes |
| `POST /api/notes` | Create note `{title, content}` → return new note |
| `DELETE /api/notes/:id` | Delete note by id → `{success: true}` |

Required frontend elements: `#notes-container`, `.note-card` per note, `#note-count`, `#note-title`, `#note-content`, `#add-note-btn`, `.delete-btn` per card.

Pre-seeded notes: **"Welcome"** and **"Getting Started"** must exist on server start.

---

## Scoring

```
total = 0.70 × functional + 0.20 × code_quality + 0.10 × visual
```

| Component | Weight | Method |
|---|---|---|
| **Functional** | 70% | Playwright browser flows (add, complete, delete, counter, login, register, etc.) |
| **Code Quality** | 20% | Static analysis — ruff linting, AST checks, no hardcoded secrets, clean structure |
| **Visual** | 10% | DOM heuristics — meaningful title, styled elements, no raw error pages |

### Partial Reward (mid-episode signal)

After every `write_file` action, a fast 2-check probe runs:
1. **HTTP ping** — is the server responding on port 8000? (+0.5 of budget)
2. **Primary element check** — is the main input usable in the browser? (+0.5 of budget)

```
reward = clamp(delta / total_checks, -0.1, +0.3)
```

This gives the agent a positive signal the moment working code is written, and a small negative signal if a previously-working server breaks.

---

## Action Space

```jsonc
// Write or overwrite a file
{"action_type": "write_file", "file_path": "index.html", "file_content": "..."}

// Read a file from the workspace
{"action_type": "read_file", "file_path": "server.js"}

// Navigate the browser to a path
{"action_type": "browser_goto", "url": "/login"}

// Click a CSS selector
{"action_type": "browser_click", "selector": "#add-btn"}

// Fill an input field
{"action_type": "browser_fill", "selector": "#todo-input", "value": "Buy milk"}

// Get text content of an element
{"action_type": "browser_get_text", "selector": "#todo-count"}

// Run JavaScript in the browser
{"action_type": "browser_evaluate", "script": "document.title"}

// Safe shell command (ls, cat, node --check, etc.)
{"action_type": "run_command", "command": "node --check server.js"}

// Submit for grading (triggers full Playwright evaluation)
{"action_type": "declare_done"}
```

---

## Observation Space

Each step returns:

| Field | Description |
|---|---|
| `task_description` | Full requirement text |
| `framework_hint` | Tech stack and file naming guidance |
| `screenshot_b64` | Base64 PNG of the current browser state |
| `feedback` | Result of the last action (file written, nav result, partial reward info) |
| `reward` | Step reward (partial signal on write_file, final score on declare_done) |
| `cumulative_reward` | Running total reward for the episode |
| `flows_passing` / `flows_total` | Playwright flow results (populated after declare_done) |
| `step_count` / `max_steps` | Episode progress (max 25 steps) |
| `done` | True when episode ends |
| `workspace_files` | List of files currently in the workspace |

---

## Quick Start

```bash
# Set credentials
export API_BASE_URL="https://api.groq.com/openai/v1"   # or any OpenAI-compatible endpoint
export HF_TOKEN="your_api_key"
export MODEL_NAME="llama-3.3-70b-versatile"
export ENV_URL="https://chirag2412-vibe-coding-env.hf.space"

# Run a single task
python3 inference.py --task task_1_todo_html

# Run all tasks sequentially
python3 inference.py --all

# Limit steps per episode
python3 inference.py --all --max-steps 15
```

### Running Locally with Docker

```bash
# Build
docker build -t vibe-coding-env .

# Start environment server
docker run -d --name vibe-server -p 7860:7860 vibe-coding-env

# Run inference (in a separate terminal)
export ENV_URL="http://localhost:7860"
python3 inference.py --task task_1_todo_html
```

---

## Project Structure

```
vibe-coding-env/
├── inference.py              # Agent loop — LLM → action → observation
├── client.py                 # HTTP client for the environment server
├── models.py                 # Pydantic models: Action, Observation, State
├── server/
│   ├── app.py                # FastAPI server exposing /reset /step /state
│   └── environment.py        # Core environment logic (browser, workspace, grader)
├── graders/
│   ├── grader.py             # Main grader + fast partial grader
│   ├── code_quality.py       # Static analysis (ruff, AST)
│   ├── visual.py             # DOM heuristic scoring
│   └── usability.py          # Element usability checks (used by partial grader)
└── tasks/
    ├── task_1_todo_html/     # Skeleton + requirement
    ├── task_2_auth_express/  # Skeleton + requirement
    └── task_3_notes_express/ # Skeleton + requirement
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_BASE_URL` | `https://router.huggingface.co/v1` | LLM API base URL |
| `MODEL_NAME` | `Qwen/Qwen2.5-72B-Instruct` | Model identifier |
| `HF_TOKEN` | — | API key (also read from `API_KEY`) |
| `ENV_URL` | `http://0.0.0.0:7860` | Environment server URL |
