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

A universal vibe coding training environment for OpenEnv.
An AI agent writes web app code in any framework (HTML/JS, FastAPI, Express.js),
sees it running in a real headless browser, and gets scored on whether it works.

## Scoring
- Functional (70%) — Playwright browser flows
- Code Quality (20%) — ruff, AST analysis, security checks
- Visual (10%) — DOM heuristics

## Tasks
- task_1_todo_html — Todo list in plain HTML/JS (Easy)
- task_2_auth_fastapi — Auth system in FastAPI/Python (Medium)
- task_3_notes_express — Notes app in Express.js/Node.js (Hard)

## Quick Start
\`\`\`bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="your_token"
export ENV_URL="https://chirag2412-vibe-coding-env.hf.space"

python inference.py --all
\`\`\`