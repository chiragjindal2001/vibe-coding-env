#!/usr/bin/env python3
"""
Inference Script — vibe-coding-env
===================================
MANDATORY environment variables:
  API_BASE_URL   The API endpoint for the LLM  (e.g. https://router.huggingface.co/v1)
  MODEL_NAME     The model identifier to use   (e.g. Qwen/Qwen2.5-72B-Instruct)
  HF_TOKEN       Your Hugging Face / API key

Usage:
  python3 inference.py --task task_1_todo_html
  python3 inference.py --all
  python3 inference.py --all --max-steps 20
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))

from client import VibeCodingClient

# ── Mandatory config from environment ──────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "dummy-key"
MODEL_NAME   = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
ENV_URL      = os.getenv("ENV_URL") or "http://0.0.0.0:7860"

BENCHMARK         = "vibe-coding-env"
MAX_STEPS         = 20
MAX_TOKENS        = 4096
MAX_PARSE_RETRIES = 3

ALL_TASKS = [
    "task_1_todo_html",
    "task_2_auth_express",
    "task_3_notes_express",
]

SYSTEM_PROMPT = """You are an expert web developer competing in a vibe-coding hackathon.
Your goal is to implement a web application that passes functional tests.

Available actions (respond with EXACTLY ONE JSON object per turn):
  write_file      — write/overwrite a file         {"action_type": "write_file", "file_path": "...", "file_content": "..."}
  read_file       — read a file                    {"action_type": "read_file", "file_path": "..."}
  browser_goto    — navigate to a PATH             {"action_type": "browser_goto", "url": "/"}
  browser_click   — click a CSS selector           {"action_type": "browser_click", "selector": "#btn"}
  browser_fill    — fill an input                  {"action_type": "browser_fill", "selector": "#inp", "value": "text"}
  browser_get_text — get element text              {"action_type": "browser_get_text", "selector": "#el"}
  browser_evaluate — run JavaScript                {"action_type": "browser_evaluate", "script": "..."}
  run_command     — safe shell command             {"action_type": "run_command", "command": "ls"}
  declare_done    — submit for grading             {"action_type": "declare_done"}

STRATEGY:
1. Read the task description carefully
2. Check the skeleton with read_file
3. Write your FULL implementation in one write_file call
4. Verify in the browser, fix bugs if needed
5. Call declare_done when satisfied

RULES:
- HTML task  → single index.html file
- Express/Auth task → single server.js file
- Node task  → single server.js file
- Use the EXACT ids and classes from the task — the grader checks them
- After write_file the server auto-reloads; navigate to verify
- 20 steps maximum — be efficient

CRITICAL JSON RULES:
- Output ONLY the JSON object, nothing else
- Use standard JSON double-quoted strings
- Escape newlines as \\n, tabs as \\t, quotes as \\"
- NEVER use triple quotes or backtick template literals
- NEVER output two JSON objects in one response"""


# ── Structured log helpers (REQUIRED FORMAT) ───────────────────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float,
             done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    action_clean = str(action).replace(" ", "_")[:60]
    print(
        f"[STEP] step={step} action={action_clean} "
        f"reward={reward:.2f} done={str(done).lower()} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float,
            rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ── Startup diagnostics ─────────────────────────────────────────────────────

def print_diagnostics(tasks_to_run: list) -> None:
    """Print environment info before anything else runs."""
    print(f"[DEBUG] Python: {sys.version}", flush=True)
    print(f"[DEBUG] Platform: {platform.platform()}", flush=True)
    print(f"[DEBUG] Working dir: {os.getcwd()}", flush=True)
    print(f"[DEBUG] Script: {__file__}", flush=True)
    print(f"[DEBUG] Args: {sys.argv}", flush=True)
    print(f"[DEBUG] API_BASE_URL: {API_BASE_URL}", flush=True)
    print(f"[DEBUG] MODEL_NAME: {MODEL_NAME}", flush=True)
    print(f"[DEBUG] ENV_URL: {ENV_URL}", flush=True)
    print(f"[DEBUG] HF_TOKEN set: {bool(API_KEY and API_KEY != 'dummy-key')}",
          flush=True)
    print(f"[DEBUG] Tasks: {tasks_to_run}", flush=True)

    # Check python/python3 availability
    for cmd in ["python", "python3"]:
        try:
            r = subprocess.run([cmd, "--version"],
                               capture_output=True, text=True, timeout=5)
            ver = (r.stdout.strip() or r.stderr.strip())
            print(f"[DEBUG] {cmd}: {ver}", flush=True)
        except FileNotFoundError:
            print(f"[DEBUG] {cmd}: NOT FOUND", flush=True)
        except Exception as e:
            print(f"[DEBUG] {cmd}: ERROR {e}", flush=True)

    # Check required files exist
    for f in ["client.py", "models.py", "openenv.yaml",
              "server/app.py", "server/environment.py"]:
        exists = Path(f).exists()
        print(f"[DEBUG] File {f}: {'EXISTS' if exists else 'MISSING'}",
              flush=True)


# ── JSON parsing helpers ────────────────────────────────────────────────────

def _sanitize_nonstandard_strings(text: str) -> str:
    def _escape(s: str) -> str:
        s = s.replace('\\', '\\\\')
        s = s.replace('"', '\\"')
        s = s.replace('\n', '\\n')
        s = s.replace('\r', '\\r')
        s = s.replace('\t', '\\t')
        return s

    text = re.sub(
        r'(:\s*)"""(.*?)"""',
        lambda m: m.group(1) + '"' + _escape(m.group(2)) + '"',
        text, flags=re.DOTALL,
    )

    m = re.search(r':\s*\n?`', text)
    if m:
        open_pos  = m.end()
        close_pos = text.rfind('`')
        if close_pos > open_pos:
            prefix = text[:m.start()] + ': '
            inner  = _escape(text[open_pos:close_pos])
            suffix = text[close_pos + 1:]
            text   = prefix + '"' + inner + '"' + suffix

    return text


def parse_action(text: str) -> Optional[dict]:
    text = text.strip()
    decoder = json.JSONDecoder()

    def _try_parse(s: str) -> Optional[dict]:
        idx = 0
        while idx < len(s):
            start = s.find("{", idx)
            if start == -1:
                break
            try:
                obj, _ = decoder.raw_decode(s, start)
                if isinstance(obj, dict) and "action_type" in obj:
                    return obj
            except Exception:
                pass
            idx = start + 1
        return None

    result = _try_parse(text)
    if result:
        return result

    sanitized = _sanitize_nonstandard_strings(text)
    if sanitized != text:
        result = _try_parse(sanitized)
        if result:
            return result

    for pattern in (r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```'):
        m = re.search(pattern, text)
        if m:
            block = _sanitize_nonstandard_strings(m.group(1))
            result = _try_parse(block)
            if result:
                return result

    return None


def screenshot_to_data_uri(b64: str) -> str:
    return f"data:image/png;base64,{b64}"


def _strip_images(messages: list) -> list:
    result = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text_only = [b for b in content if b.get("type") != "image_url"]
            if not text_only:
                text_only = [{"type": "text",
                               "text": "(screenshot omitted — model is text-only)"}]
            result.append({**msg, "content": text_only})
        else:
            result.append(msg)
    return result


def _flatten_content(messages: list) -> list:
    result = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            )
            result.append({**msg, "content": text or "(empty)"})
        else:
            result.append(msg)
    return result


def _add_image(content: list, b64: str, vision: bool) -> None:
    if vision and b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": screenshot_to_data_uri(b64)},
        })


# ── Episode runner ──────────────────────────────────────────────────────────

def run_episode(
    llm: OpenAI,
    env_client: VibeCodingClient,
    task_id: str,
    max_steps: int = MAX_STEPS,
) -> dict:
    """Run one full episode. Always emits [START] and [END] lines."""
    rewards: List[float] = []
    steps_taken = 0
    score   = 0.0
    success = False
    obs: dict = {}

    # [START] — always emitted first
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        obs = env_client.reset(task_id=task_id)
    except Exception as exc:
        print(f"[DEBUG] reset failed: {exc}", flush=True)
        log_end(success=False, steps=0, score=0.0, rewards=[])
        return {
            "task_id": task_id, "final_score": 0.0, "steps_taken": 0,
            "flows_passing": 0, "flows_total": 0, "functional_score": 0.0,
            "code_quality_score": 0.0, "visual_score": 0.0,
        }

    vision: bool        = False   # safer default for text-only models
    array_content: bool = True

    user_text = (
        f"TASK: {obs.get('task_description', '')}\n\n"
        f"FRAMEWORK: {obs.get('framework_hint', '')}\n\n"
        f"WORKSPACE FILES: {obs.get('workspace_files', [])}\n\n"
        "The browser is already open at the app root. "
        "Use browser_goto with paths like '/' or '/login', not full URLs. "
        "Start by reading the skeleton file, then write your full solution."
    )

    first_content: list = [{"type": "text", "text": user_text}]
    _add_image(first_content, obs.get("screenshot_b64", ""), vision)

    messages: list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": first_content},
    ]

    step          = 0
    parse_retries = 0

    try:
        while step < max_steps and not obs.get("done", False):
            step += 1
            steps_taken = step

            if step > 1:
                time.sleep(1)

            # ── LLM call ────────────────────────────────────────────────
            assistant_text = ""
            try:
                completion = llm.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    max_tokens=MAX_TOKENS,
                    temperature=0.2,
                )
                assistant_text = completion.choices[0].message.content or ""

            except Exception as exc:
                err = str(exc)

                if "429" in err or "413" in err or "rate" in err.lower():
                    print(f"[DEBUG] Rate limited at step {step}. Waiting 20s...",
                          flush=True)
                    time.sleep(20)
                    try:
                        completion = llm.chat.completions.create(
                            model=MODEL_NAME, messages=messages,
                            max_tokens=MAX_TOKENS, temperature=0.2,
                        )
                        assistant_text = \
                            completion.choices[0].message.content or ""
                    except Exception as exc2:
                        print(f"[DEBUG] Still failing: {exc2}", flush=True)
                        break

                elif array_content and "must be a string" in err.lower():
                    array_content = False
                    vision = False
                    messages = _flatten_content(_strip_images(messages))
                    try:
                        completion = llm.chat.completions.create(
                            model=MODEL_NAME, messages=messages,
                            max_tokens=MAX_TOKENS, temperature=0.2,
                        )
                        assistant_text = \
                            completion.choices[0].message.content or ""
                    except Exception as exc2:
                        print(f"[DEBUG] Flatten retry failed: {exc2}", flush=True)
                        break

                elif vision and (
                    "image"  in err.lower() or
                    "vision" in err.lower() or
                    "404"    in err
                ):
                    vision = False
                    messages = _strip_images(messages)
                    try:
                        completion = llm.chat.completions.create(
                            model=MODEL_NAME, messages=messages,
                            max_tokens=MAX_TOKENS, temperature=0.2,
                        )
                        assistant_text = \
                            completion.choices[0].message.content or ""
                    except Exception as exc2:
                        print(f"[DEBUG] No-vision retry failed: {exc2}",
                              flush=True)
                        break

                else:
                    print(f"[DEBUG] LLM error at step {step}: {exc}", flush=True)
                    break

            # ── Parse action ─────────────────────────────────────────────
            action = parse_action(assistant_text)
            if action is None:
                parse_retries += 1
                if parse_retries >= MAX_PARSE_RETRIES:
                    print("[DEBUG] Max parse retries — stopping", flush=True)
                    break
                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your last response could not be parsed as JSON. "
                        "Output ONLY a valid JSON object, "
                        'e.g. {"action_type": "read_file", "file_path": "index.html"}'
                    ),
                })
                continue

            parse_retries = 0
            action_type   = action.get("action_type", "unknown")

            # ── Execute ───────────────────────────────────────────────────
            try:
                obs = env_client.step(action)
            except Exception as step_exc:
                print(f"[DEBUG] Step error: {step_exc}", flush=True)
                obs = {
                    **obs,
                    "last_action_error": str(step_exc),
                    "done": False,
                    "reward": 0.0,
                }

            reward = float(obs.get("reward", 0.0))
            done   = bool(obs.get("done", False))
            error  = obs.get("last_action_error") or None
            rewards.append(reward)

            # [STEP] — emitted after every env.step()
            log_step(step=step, action=action_type,
                     reward=reward, done=done, error=error)

            feedback_text = obs.get("feedback") or ""
            if error:
                feedback_text += f"\n\nERROR: {error}"
            next_content: list = [{"type": "text", "text": feedback_text}]
            _add_image(next_content, obs.get("screenshot_b64", ""), vision)

            messages.append({"role": "assistant", "content": assistant_text})
            if array_content:
                messages.append({"role": "user", "content": next_content})
            else:
                messages.append({"role": "user",
                                  "content": feedback_text or "(empty)"})

            if done:
                score = float(obs.get("reward", 0.0))
                break

        # Force grading if episode didn't end naturally
        if not obs.get("done", False):
            print("[DEBUG] Step limit reached — forcing declare_done", flush=True)
            try:
                obs     = env_client.step({"action_type": "declare_done"})
                score   = float(obs.get("reward", 0.0))
                reward  = score
                error   = obs.get("last_action_error") or None
                rewards.append(reward)
                log_step(step=steps_taken + 1, action="declare_done",
                         reward=reward, done=True, error=error)
            except Exception as exc:
                print(f"[DEBUG] declare_done failed: {exc}", flush=True)
                score = 0.0

        success = score >= 0.1

    except Exception as outer_exc:
        print(f"[DEBUG] Outer exception: {outer_exc}", flush=True)
        score   = 0.0
        success = False

    # [END] — always emitted, even on exception
    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return {
        "task_id":            task_id,
        "final_score":        score,
        "steps_taken":        steps_taken,
        "flows_passing":      obs.get("flows_passing", 0),
        "flows_total":        obs.get("flows_total", 0),
        "functional_score":   obs.get("functional_score", 0.0),
        "code_quality_score": obs.get("code_quality_score", 0.0),
        "visual_score":       obs.get("visual_score", 0.0),
    }


# ── CLI entry point ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the vibe-coding agent against the environment"
    )
    parser.add_argument("--task", type=str,
                        choices=ALL_TASKS,
                        help="Single task ID to run")
    parser.add_argument("--all",       action="store_true",
                        help="Run all tasks sequentially (default)")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    parser.add_argument("--env-url",   type=str, default=ENV_URL)
    args = parser.parse_args()

    # Default: run all tasks if no specific task given
    if not args.task:
        args.all = True

    tasks_to_run = ALL_TASKS if args.all else [args.task]

    # ── Startup diagnostics ─────────────────────────────────────────────
    print_diagnostics(tasks_to_run)

    # ── Connect to environment ───────────────────────────────────────────
    env_client = None
    try:
        env_client = VibeCodingClient(base_url=args.env_url)
        health = env_client.health()
        print(f"[DEBUG] Environment health: {health}", flush=True)
    except Exception as exc:
        print(f"[DEBUG] Cannot reach environment at {args.env_url}: {exc}",
              flush=True)
        # Emit START+END for every task so output parser has something to read
        for task_id in tasks_to_run:
            log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
            log_end(success=False, steps=0, score=0.0, rewards=[])
        sys.exit(0)

    if not MODEL_NAME:
        print("[DEBUG] WARNING: MODEL_NAME not set", flush=True)
    if not API_KEY or API_KEY == "dummy-key":
        print("[DEBUG] WARNING: HF_TOKEN not set", flush=True)

    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    for task_id in tasks_to_run:
        try:
            run_episode(
                llm=llm,
                env_client=env_client,
                task_id=task_id,
                max_steps=args.max_steps,
            )
        except Exception as exc:
            print(f"[DEBUG] run_episode crashed for {task_id}: {exc}", flush=True)
            log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)
            log_end(success=False, steps=0, score=0.0, rewards=[])


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[DEBUG] Top-level crash: {exc}", flush=True)
        sys.exit(0)