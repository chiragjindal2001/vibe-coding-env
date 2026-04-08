"""
Inference Script — vibe-coding-env
===================================
MANDATORY environment variables:
  API_BASE_URL   The API endpoint for the LLM  (e.g. https://router.huggingface.co/v1)
  MODEL_NAME     The model identifier to use   (e.g. Qwen/Qwen2.5-72B-Instruct)
  HF_TOKEN       Your Hugging Face / API key

Usage:
  python inference.py --task task_1_todo_html
  python inference.py --all
  python inference.py --all --max-steps 20
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))

from client import VibeCodingClient

# ── Mandatory config from environment ──────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
MODEL_NAME   = os.getenv("MODEL_NAME")
ENV_URL      = os.getenv("ENV_URL", "http://0.0.0.0:7860")

MAX_STEPS        = 20
MAX_TOKENS       = 4096
MAX_PARSE_RETRIES = 3   # consecutive unparseable responses before giving up

SYSTEM_PROMPT = """You are an expert web developer competing in a vibe-coding hackathon.
Your goal is to implement a web application that passes functional tests.

Available actions (respond with EXACTLY ONE JSON object per turn):
  write_file      — write/overwrite a file         {"action_type": "write_file", "file_path": "...", "file_content": "..."}
  read_file       — read a file                    {"action_type": "read_file", "file_path": "..."}
  browser_goto    — navigate to a PATH (not full URL)  {"action_type": "browser_goto", "url": "/notes"}
  browser_click   — click a CSS selector           {"action_type": "browser_click", "selector": "#btn"}
  browser_fill    — fill an input                  {"action_type": "browser_fill", "selector": "#inp", "value": "text"}
  browser_get_text — get element text              {"action_type": "browser_get_text", "selector": "#el"}
  browser_evaluate — run JavaScript                {"action_type": "browser_evaluate", "script": "..."}
  run_command     — safe shell command             {"action_type": "run_command", "command": "ls"}  (ls, cat, find, head, tail, wc, node --check allowed)
  declare_done    — submit for grading             {"action_type": "declare_done"}

STRATEGY:
1. Read the task description carefully
2. Check the skeleton with read_file
3. Write your FULL implementation in one write_file call
4. Verify in the browser, fix bugs if needed
5. Call declare_done when satisfied

RULES:
- HTML task  → single index.html file
- FastAPI task → main.py + templates/*.html (write ALL template files)
- Node task  → single server.js file
- Use the EXACT ids and classes from the task — the grader checks them
- After write_file the server auto-reloads; navigate to verify
- 20 steps maximum — be efficient

CRITICAL JSON RULES — your output is parsed by a strict JSON parser:
- Output ONLY the JSON object, nothing else (no explanation, no markdown)
- Use standard JSON double-quoted strings: "file_content": "line1\\nline2"
- Escape newlines as \\n, tabs as \\t, quotes as \\"
- NEVER use triple quotes (\"\"\"...\"\"\") — they are NOT valid JSON
- NEVER output two JSON objects in one response"""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _sanitize_nonstandard_strings(text: str) -> str:
    """
    Convert non-JSON string delimiters to properly escaped JSON strings,
    but ONLY when they appear as JSON values (after a JSON key colon).

    Uses rfind for backticks so nested backtick template literals inside
    JS code don't confuse the parser — we always find the LAST (outer) closing ` .

    Handles:
      - Python triple-quoted strings: \"\"\"...\"\"\"
      - JS backtick template literals: `...`  (with nested backticks inside)
    """
    def _escape(s: str) -> str:
        s = s.replace('\\', '\\\\')
        s = s.replace('"', '\\"')
        s = s.replace('\n', '\\n')
        s = s.replace('\r', '\\r')
        s = s.replace('\t', '\\t')
        return s

    # ── Triple-quote (no nesting expected) ──────────────────────────────────
    text = re.sub(
        r'(:\s*)"""(.*?)"""',
        lambda m: m.group(1) + '"' + _escape(m.group(2)) + '"',
        text, flags=re.DOTALL,
    )

    # ── Backtick (JS code may have nested template literals) ─────────────────
    # Find the opening pattern (colon + optional whitespace + backtick)
    m = re.search(r':\s*\n?`', text)
    if m:
        open_pos = m.end()          # index right after the opening backtick
        close_pos = text.rfind('`') # LAST backtick = outer closing one
        if close_pos > open_pos:
            prefix = text[:m.start()] + ': '
            inner  = _escape(text[open_pos:close_pos])
            suffix = text[close_pos + 1:]
            text   = prefix + '"' + inner + '"' + suffix

    return text


def parse_action(text: str) -> dict | None:
    """
    Extract a JSON action object from the model response.
    Uses raw_decode so nested braces in file_content don't confuse the parser.
    """
    text = text.strip()
    decoder = json.JSONDecoder()

    def _try_parse(s: str) -> dict | None:
        """Try raw_decode from every '{' position."""
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

    # 1. Direct parse
    result = _try_parse(text)
    if result:
        return result

    # 2. Sanitize triple quotes and retry
    sanitized = _sanitize_nonstandard_strings(text)
    if sanitized != text:
        result = _try_parse(sanitized)
        if result:
            return result

    # 3. Strip markdown fences and retry
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


def _strip_images(messages: list[dict]) -> list[dict]:
    """Remove all image_url blocks from a message list (for text-only models)."""
    result = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text_only = [b for b in content if b.get("type") != "image_url"]
            if not text_only:
                text_only = [{"type": "text", "text": "(screenshot omitted — model is text-only)"}]
            result.append({**msg, "content": text_only})
        else:
            result.append(msg)
    return result


def _flatten_content(messages: list[dict]) -> list[dict]:
    """Convert array content blocks to plain strings (for models like Groq)."""
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


def _add_image(content: list[dict], b64: str, vision: bool) -> None:
    """Append an image block only when the model supports vision."""
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
    verbose: bool = True,
) -> dict:
    """
    Run one full episode.

    Args:
        llm:        Shared OpenAI client.
        env_client: Connected VibeCodingClient.
        task_id:    Which task to solve.
        max_steps:  Hard cap on agent steps.
        verbose:    Print step-by-step progress.
    """
    if verbose:
        print(f"START {task_id}")

    obs = env_client.reset(task_id=task_id)

    if verbose:
        print(f"Description: {obs['task_description'][:200]}...")
        print(f"Framework:   {obs['framework_hint']}")

    # Assume vision is supported until the model proves otherwise
    vision: bool = True
    # Some models (e.g. Groq) require plain string content, not arrays
    array_content: bool = True

    # Build first user message
    user_text = (
        f"TASK: {obs['task_description']}\n\n"
        f"FRAMEWORK: {obs['framework_hint']}\n\n"
        f"WORKSPACE FILES: {obs['workspace_files']}\n\n"
        "The browser is already open at the app root. "
        "Use browser_goto with paths like '/' or '/register', not full URLs. "
        "Start by reading the skeleton file, then write your solution."
    )
    first_content: list[dict] = [{"type": "text", "text": user_text}]
    _add_image(first_content, obs.get("screenshot_b64"), vision)

    messages: list[dict] = [
        {"role": "system",  "content": SYSTEM_PROMPT},
        {"role": "user",    "content": first_content},
    ]

    step = 0
    final_score = 0.0
    parse_retries = 0

    while step < max_steps and not obs.get("done", False):
        step += 1

        # Small delay between steps to avoid hitting per-minute rate limits
        if step > 1:
            time.sleep(1)

        # ── LLM call ────────────────────────────────────────────────────────
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
            # Rate limited (429/413) — wait and retry once
            if "429" in err or "413" in err or "rate" in err.lower():
                wait = 20
                print(f"  [step {step}] Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                try:
                    completion = llm.chat.completions.create(
                        model=MODEL_NAME,
                        messages=messages,
                        max_tokens=MAX_TOKENS,
                        temperature=0.2,
                    )
                    assistant_text = completion.choices[0].message.content or ""
                except Exception as exc2:
                    print(f"  [step {step}] Still rate limited: {exc2}")
                    break
            # Model requires plain string content (e.g. Groq) — flatten and retry
            elif array_content and "must be a string" in err.lower():
                array_content = False
                vision = False
                if verbose:
                    print(f"  [step {step}] Model requires string content — flattening and retrying")
                messages = _flatten_content(_strip_images(messages))
                try:
                    completion = llm.chat.completions.create(
                        model=MODEL_NAME,
                        messages=messages,
                        max_tokens=MAX_TOKENS,
                        temperature=0.2,
                    )
                    assistant_text = completion.choices[0].message.content or ""
                except Exception as exc2:
                    print(f"  [step {step}] LLM error after retry: {exc2}")
                    break
            # Model doesn't support image input — strip images and retry once
            elif vision and ("image" in err.lower() or "404" in err):
                vision = False
                if verbose:
                    print(f"  [step {step}] Model is text-only — dropping screenshots and retrying")
                messages = _strip_images(messages)
                try:
                    completion = llm.chat.completions.create(
                        model=MODEL_NAME,
                        messages=messages,
                        max_tokens=MAX_TOKENS,
                        temperature=0.2,
                    )
                    assistant_text = completion.choices[0].message.content or ""
                except Exception as exc2:
                    print(f"  [step {step}] LLM error after retry: {exc2}")
                    break
            else:
                print(f"  [step {step}] LLM error: {exc}")
                break

        if verbose:
            print(f"  Model: {assistant_text[:200]}...")

        # ── Parse action ─────────────────────────────────────────────────────
        action = parse_action(assistant_text)
        if action is None:
            parse_retries += 1
            if verbose:
                print(f"  Unparseable response ({parse_retries}/{MAX_PARSE_RETRIES})")
            if parse_retries >= MAX_PARSE_RETRIES:
                if verbose:
                    print("  Max parse retries hit — forcing declare_done")
                break
            messages.append({"role": "assistant", "content": assistant_text})
            messages.append({
                "role": "user",
                "content": (
                    "Your last response could not be parsed as JSON. "
                    'Output ONLY a valid JSON object, e.g. {"action_type": "read_file", "file_path": "index.html"}'
                ),
            })
            continue

        parse_retries = 0

        if verbose:
            print(f"STEP {step} {action.get('action_type', 'unknown')}")

        # ── Execute ─────────────────────────────────────────────────────────
        try:
            obs = env_client.step(action)
        except Exception as step_exc:
            # Step timed out or network error — treat as a non-fatal error and continue
            print(f"  [step {step}] Step error (continuing): {step_exc}")
            obs = {**obs, "last_action_error": f"Step error: {step_exc}", "done": False}
            continue

        if verbose:
            if obs.get("last_action_error"):
                print(f"  ERROR: {obs['last_action_error']}")
            elif obs.get("feedback"):
                print(f"  Feedback: {obs['feedback'][:120]}")
            if obs.get("done"):
                print(f"\n  DONE!  Score: {obs.get('reward', 0):.3f}")
                print(f"  {obs.get('feedback', '')[:600]}")

        # Build next message
        feedback_text = obs.get("feedback") or ""
        if obs.get("last_action_error"):
            feedback_text += f"\n\nERROR: {obs['last_action_error']}"
        next_content: list[dict] = [{"type": "text", "text": feedback_text}]
        _add_image(next_content, obs.get("screenshot_b64"), vision)

        messages.append({"role": "assistant", "content": assistant_text})
        if array_content:
            messages.append({"role": "user", "content": next_content})
        else:
            messages.append({"role": "user", "content": feedback_text or "(empty)"})

        if obs.get("done"):
            final_score = obs.get("reward", 0.0)
            break

    # If episode didn't end naturally, force grading
    if not obs.get("done", False):
        if verbose:
            print("\n  Step limit reached — forcing declare_done")
        obs = env_client.step({"action_type": "declare_done"})
        final_score = obs.get("reward", 0.0)
        if verbose:
            print(f"  Final score: {final_score:.3f}")

    return {
        "task_id":            task_id,
        "final_score":        final_score,
        "steps_taken":        step,
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
    parser.add_argument("--task",      type=str,  help="Single task ID to run")
    parser.add_argument("--all",       action="store_true", help="Run all tasks")
    parser.add_argument("--max-steps", type=int,  default=MAX_STEPS)
    parser.add_argument("--env-url",   type=str,  default=ENV_URL)
    parser.add_argument("--verbose",   action="store_true", default=True)
    args = parser.parse_args()

    env_client = VibeCodingClient(base_url=args.env_url)
    try:
        health = env_client.health()
        print(f"Environment health: {health}")
    except Exception as exc:
        print(f"Cannot reach environment at {args.env_url}: {exc}")
        print("Start the server first:  uvicorn server.app:app --port 7860")
        sys.exit(1)

    # Warn early if mandatory env vars are missing — the checker sets these
    if not MODEL_NAME:
        print("WARNING: MODEL_NAME env var is not set — LLM calls will fail")
    if not API_KEY:
        print("WARNING: HF_TOKEN / API_KEY env var is not set")

    # One shared OpenAI-compatible client for all episodes
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    if args.all:
        tasks_to_run = [
            "task_1_todo_html",
            "task_2_auth_fastapi",
            "task_3_notes_express",
        ]
    elif args.task:
        tasks_to_run = [args.task]
    else:
        parser.print_help()
        sys.exit(1)

    results = []
    total_start = time.time()

    for task_id in tasks_to_run:
        t0 = time.time()
        result = run_episode(
            llm=llm,
            env_client=env_client,
            task_id=task_id,
            max_steps=args.max_steps,
            verbose=args.verbose,
        )
        elapsed = time.time() - t0
        result["elapsed_seconds"] = round(elapsed, 1)
        results.append(result)
        print(f"END {task_id} {result['final_score']:.3f}"
            f"  flows={result['flows_passing']}/{result['flows_total']}"
            f"  quality={result['code_quality_score']:.3f}"
            f"  visual={result['visual_score']:.3f}"
            f"  time={elapsed:.0f}s"
        )

    total_elapsed = time.time() - total_start

    if len(results) > 1:
        avg = sum(r["final_score"] for r in results) / len(results)
        print(f"\n{'='*60}")
        print(f"SUMMARY  avg={avg:.3f}  total={total_elapsed:.0f}s")
        for r in results:
            print(f"  {r['task_id']}: {r['final_score']:.3f}  ({r['elapsed_seconds']}s)")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
