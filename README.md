# vibe-coding-env

OpenEnv hackathon submission: an environment that trains AI agents to build web applications by "vibe coding" — writing code, running it in a real browser, and iterating based on visual feedback.

## Overview

The agent is given a web app specification and must implement it within 25 steps. It can write files, navigate the browser, click/fill elements, and evaluate JavaScript. A deterministic grader scores the submission across three dimensions:

- **Functional (70%)**: Playwright user flows that test exact CSS selectors and user interactions
- **Code Quality (20%)**: Static analysis — syntax, complexity, structure, security
- **Visual (10%)**: DOM-based heuristics checking layout, semantics, and styling

## Tasks

| Task | Framework | Flows |
|------|-----------|-------|
| `task_1_todo_html` | Plain HTML/JS | Add, complete, delete, counter |
| `task_2_auth_fastapi` | FastAPI + Jinja2 | Register, login, dashboard, logout, invalid login |
| `task_3_notes_express` | Node.js + Express | Pre-seeded notes, add, delete, count |

## Quick Start

```bash
# Install dependencies
pip install -r server/requirements.txt
playwright install chromium --with-deps

# Start the environment server (port 7860 = OpenEnv API; task servers run on 8000)
uvicorn server.app:app --port 7860

# In another terminal, run inference
export ANTHROPIC_API_KEY=sk-...
python inference.py --task task_1_todo_html
python inference.py --all
```

## Architecture

```
vibe-coding-env/
├── models.py              # VibeCodingAction, VibeCodingObservation, VibeCodingState
├── client.py              # HTTP client for the environment
├── inference.py           # Claude agent that solves tasks
├── openenv.yaml           # OpenEnv spec
├── pyproject.toml
├── server/
│   ├── app.py             # FastAPI app via create_app()
│   ├── environment.py     # VibeCodingEnvironment (Playwright stays alive!)
│   └── requirements.txt
├── graders/
│   ├── grader.py          # Orchestrates all graders
│   ├── usability.py       # safe_click, safe_fill, check_element_usability
│   ├── visual.py          # DOM-based visual heuristics
│   └── code_quality.py    # Syntax, complexity, structure, security
└── tasks/
    ├── task_definitions.py
    ├── task_1_todo_html/
    │   ├── requirement.txt
    │   ├── hints.txt
    │   └── skeleton/index.html
    ├── task_2_auth_fastapi/
    │   ├── requirement.txt
    │   ├── hints.txt
    │   ├── requirements.txt
    │   └── skeleton/main.py
    └── task_3_notes_express/
        ├── requirement.txt
        ├── hints.txt
        └── skeleton/{server.js,package.json}
```

## Critical Design Decisions

1. **Playwright stays alive**: The browser instance persists across all steps in an episode. It is only closed when the environment is garbage collected.

2. **uvicorn --reload**: Python (FastAPI) tasks use uvicorn with `--reload` so file writes auto-apply without restarting.

3. **declare_done grading**: Grading only runs when the agent explicitly calls `declare_done` (or steps run out). No LLM calls — all grading is deterministic Playwright flows + static analysis.

4. **Step limit enforcement**: `done=True` is returned when `step_count >= 25` or after `declare_done`.
