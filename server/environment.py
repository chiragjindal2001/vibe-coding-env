"""
VibeCodingEnvironment - OpenEnv environment for vibe coding tasks.

CRITICAL: Playwright browser stays alive across ALL steps within one episode.
Never call browser.close() or page.close() between steps.
"""
from __future__ import annotations
import os
import shutil
import socket
import subprocess
import tempfile
import time
import base64
import urllib.request
from pathlib import Path
from typing import Optional

from openenv.core.env_server import Environment

# ── Constants ──────────────────────────────────────────────────────────────
MAX_STEPS: int = 25
TASK_SERVER_PORT: int = 8000
TASK_SERVER_HOST: str = "127.0.0.1"
TASK_SERVER_URL: str = f"http://{TASK_SERVER_HOST}:{TASK_SERVER_PORT}"


class VibeCodingEnvironment(Environment):
    """
    Environment that keeps Playwright alive across ALL steps in an episode.
    Framework is auto-detected from workspace files.
    """

    def __init__(self):
        # Playwright — persists across ALL steps (never closed between steps)
        self._playwright = None
        self._browser = None
        self._page = None

        # Subprocess running the task server (uvicorn / node / http.server)
        self._server_process: Optional[subprocess.Popen] = None
        self._workspace: Optional[str] = None
        self._framework: str = "html"

        # Episode state
        from models import VibeCodingState
        self._state = VibeCodingState()

    # ── Playwright lifecycle ───────────────────────────────────────────────

    def _ensure_playwright(self) -> None:
        """Start Playwright once per environment instance. Never called twice."""
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        if self._page is None:
            self._page = self._browser.new_page(
                viewport={"width": 1280, "height": 720}
            )

    def _take_screenshot(self) -> Optional[str]:
        if self._page is None:
            return None
        try:
            png = self._page.screenshot(timeout=5000)
            return base64.b64encode(png).decode()
        except Exception:
            return None

    # ── Server lifecycle ───────────────────────────────────────────────────

    def _port_in_use(self, port: int = TASK_SERVER_PORT) -> bool:
        """Return True if something is already listening on the port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((TASK_SERVER_HOST, port)) == 0

    def _free_port(self, port: int = TASK_SERVER_PORT) -> None:
        """Best-effort: kill whatever is holding the port (Linux only)."""
        if not self._port_in_use(port):
            return
        for cmd in (
            ["fuser", "-k", f"{port}/tcp"],
            ["lsof", "-ti", f":{port}"],
        ):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3
                )
                if cmd[0] == "lsof" and result.stdout.strip():
                    for pid in result.stdout.strip().split():
                        subprocess.run(
                            ["kill", "-9", pid],
                            capture_output=True, timeout=2
                        )
                time.sleep(0.4)
                if not self._port_in_use(port):
                    return
            except Exception:
                continue

    def _stop_server(self) -> None:
        if self._server_process and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
                self._server_process.wait(timeout=2)
        self._server_process = None
        # Belt-and-suspenders: free the port in case the process leaked
        self._free_port(TASK_SERVER_PORT)

    def _detect_framework(self) -> str:
        workspace = Path(self._workspace)
        if (workspace / "main.py").exists():
            return "python"
        if (workspace / "server.js").exists() or (workspace / "package.json").exists():
            return "nodejs"
        return "html"

    def _start_server(self) -> None:
        workspace = self._workspace

        if self._framework == "python":
            req = Path(workspace) / "requirements.txt"
            if req.exists():
                try:
                    subprocess.run(
                        ["pip", "install", "-r", str(req), "-q", "--quiet"],
                        cwd=workspace, timeout=60,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            # --reload means file writes are auto-applied without a restart
            self._server_process = subprocess.Popen(
                [
                    "uvicorn", "main:app",
                    "--port", str(TASK_SERVER_PORT),
                    "--host", TASK_SERVER_HOST,
                    "--reload",
                ],
                cwd=workspace,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        elif self._framework == "nodejs":
            try:
                subprocess.run(
                    ["npm", "install", "--silent", "--prefer-offline"],
                    cwd=workspace, timeout=90,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            self._server_process = subprocess.Popen(
                ["node", "server.js"],
                cwd=workspace,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        else:  # html
            self._server_process = subprocess.Popen(
                ["python", "-m", "http.server", str(TASK_SERVER_PORT)],
                cwd=workspace,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        started = self._wait_for_server(timeout=10)
        if not started:
            # Surface this so the agent sees it in feedback
            print(
                f"[VibeCodingEnv] WARNING: server did not respond on "
                f"{TASK_SERVER_URL} within 10 s (framework={self._framework})"
            )

    def _wait_for_server(self, timeout: int = 10) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                urllib.request.urlopen(TASK_SERVER_URL, timeout=1)
                return True
            except Exception:
                time.sleep(0.3)
        return False

    def _list_workspace_files(self) -> list:
        if not self._workspace:
            return []
        result = []
        for f in Path(self._workspace).rglob("*"):
            if (
                f.is_file()
                and "node_modules" not in str(f)
                and "__pycache__" not in str(f)
            ):
                result.append(str(f.relative_to(self._workspace)))
        return sorted(result)

    # ── OpenEnv required interface ─────────────────────────────────────────

    def reset(self, task_id: str = None, **kwargs):
        from models import VibeCodingState, VibeCodingObservation
        from tasks.task_definitions import TASKS

        self._stop_server()

        # Task selection
        if task_id is None:
            import random
            task_id = random.choice(list(TASKS.keys()))
        if task_id not in TASKS:
            task_id = list(TASKS.keys())[0]
        task = TASKS[task_id]

        # Fresh workspace
        if self._workspace and os.path.exists(self._workspace):
            try:
                shutil.rmtree(self._workspace)
            except Exception:
                pass
        self._workspace = tempfile.mkdtemp(prefix="vibe_")

        # Copy skeleton into workspace
        skeleton_dir = (
            Path(__file__).parent.parent / "tasks" / task["skeleton_dir"]
        )
        if skeleton_dir.exists():
            shutil.copytree(str(skeleton_dir), self._workspace, dirs_exist_ok=True)

        # Copy per-task requirements.txt if present (e.g. FastAPI task)
        task_req = (
            Path(__file__).parent.parent / "tasks" / task_id / "requirements.txt"
        )
        if task_req.exists():
            shutil.copy(str(task_req), os.path.join(self._workspace, "requirements.txt"))

        # Detect framework and boot task server
        self._framework = task.get("framework") or self._detect_framework()
        self._start_server()

        # Ensure browser is alive (persists across steps)
        self._ensure_playwright()

        try:
            self._page.goto(
                TASK_SERVER_URL, timeout=10000, wait_until="domcontentloaded"
            )
        except Exception:
            pass

        self._state = VibeCodingState(
            task_id=task_id,
            framework=self._framework,
            current_url=TASK_SERVER_URL,
            step_count=0,
            cumulative_reward=0.0,
            concluded=False,
            workspace_files=self._list_workspace_files(),
        )

        return VibeCodingObservation(
            task_id=task_id,
            task_description=task["description"],
            framework_hint=task["framework_hint"],
            screenshot_b64=self._take_screenshot(),
            current_url=TASK_SERVER_URL,
            page_title=self._safe_title(),
            feedback="Environment ready. Read the requirement and start coding!",
            step_count=0,
            max_steps=MAX_STEPS,
            done=False,
            workspace_files=self._list_workspace_files(),
        )

    def step(self, action):
        from models import VibeCodingObservation
        from graders.usability import safe_click, safe_fill, safe_get_text

        self._state.step_count += 1
        error: Optional[str] = None
        feedback: str = ""

        # Guard: ensure we have an action_type
        atype: str = getattr(action, "action_type", None) or ""
        if not atype:
            error = "action_type is required"
        else:
            try:
                if atype == "write_file":
                    feedback = self._do_write_file(
                        action.file_path, action.file_content
                    )

                elif atype == "read_file":
                    feedback = self._do_read_file(action.file_path)

                elif atype == "browser_goto":
                    url = action.url or "/"
                    if not url.startswith("http"):
                        url = f"{TASK_SERVER_URL}{url}"
                    self._page.goto(
                        url, timeout=10000, wait_until="domcontentloaded"
                    )
                    try:
                        self._page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    feedback = f"Navigated to {url}"

                elif atype == "browser_click":
                    ok, msg = safe_click(self._page, action.selector)
                    feedback = msg
                    if not ok:
                        error = msg
                    else:
                        try:
                            self._page.wait_for_load_state(
                                "networkidle", timeout=2000
                            )
                        except Exception:
                            pass

                elif atype == "browser_fill":
                    ok, msg = safe_fill(
                        self._page, action.selector, action.value or ""
                    )
                    feedback = msg
                    if not ok:
                        error = msg

                elif atype == "browser_get_text":
                    text, msg = safe_get_text(self._page, action.selector)
                    feedback = text if text is not None else msg

                elif atype == "browser_evaluate":
                    result = self._page.evaluate(action.script or "null")
                    feedback = str(result)

                elif atype == "run_command":
                    feedback = self._do_run_command(action.command or "")

                elif atype == "declare_done":
                    return self._declare_done()

                else:
                    error = f"Unknown action_type: {atype!r}"

            except Exception as exc:
                error = str(exc)

        current_url = self._safe_url()
        self._state.current_url = current_url
        done = self._state.concluded or self._state.step_count >= MAX_STEPS

        return VibeCodingObservation(
            task_id=self._state.task_id,
            task_description="",
            framework_hint="",
            screenshot_b64=self._take_screenshot(),
            current_url=current_url,
            page_title=self._safe_title(),
            feedback=feedback,
            last_action_error=error,
            reward=0.0,
            cumulative_reward=self._state.cumulative_reward,
            flows_passing=self._state.flows_passing,
            flows_total=self._state.flows_total,
            step_count=self._state.step_count,
            max_steps=MAX_STEPS,
            done=done,
            workspace_files=self._list_workspace_files(),
        )

    @property
    def state(self):
        return self._state

    # ── Action implementations ─────────────────────────────────────────────

    def _do_write_file(self, file_path: Optional[str], content: Optional[str]) -> str:
        if not file_path:
            return "Error: file_path is required"
        if content is None:
            return "Error: file_content is required"

        # Prevent path traversal
        target = Path(self._workspace) / file_path
        try:
            target.resolve().relative_to(Path(self._workspace).resolve())
        except ValueError:
            return "Error: path traversal outside workspace is not allowed"

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        if self._framework == "python" and str(file_path).endswith(".py"):
            # Only .py changes trigger uvicorn reload; templates/assets do not
            time.sleep(2.5)
            if not self._wait_for_server(timeout=20):
                return (
                    f"Wrote {file_path} ({len(content)} chars)\n"
                    "WARNING: server did not respond after write — possible import error in main.py. "
                    "Check your imports and fix any missing dependencies."
                )
        elif self._framework == "nodejs":
            # Node has no hot-reload; restart the server
            self._stop_server()
            time.sleep(0.3)
            self._start_server()
            if not self._wait_for_server(timeout=5):
                return (
                    f"Wrote {file_path} ({len(content)} chars)\n"
                    "WARNING: server failed to start after write — likely a syntax error in server.js. "
                    "Use run_command with 'node --check server.js' to find the error, then fix and rewrite the file."
                )

        return f"Wrote {file_path} ({len(content)} chars)"

    def _do_read_file(self, file_path: Optional[str]) -> str:
        if not file_path:
            return "Error: file_path is required"
        target = Path(self._workspace) / file_path
        if not target.exists():
            return f"Error: {file_path} not found in workspace"
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return f"Error reading {file_path}: {exc}"

    def _do_run_command(self, command: str) -> str:
        cmd = command.strip()
        allowed = ("ls", "cat ", "find ", "head ", "tail ", "wc ", "node --check ")
        is_allowed = cmd == "ls" or any(cmd.startswith(p) for p in allowed)
        if not is_allowed:
            return "Error: only ls, cat, find, head, tail, wc, node --check are permitted"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=self._workspace, timeout=5,
            )
            return (result.stdout or result.stderr or "")[:2000]
        except subprocess.TimeoutExpired:
            return "Error: command timed out"
        except Exception as exc:
            return f"Error running command: {exc}"

    def _declare_done(self):
        from models import VibeCodingObservation
        from graders.grader import grade_submission
        from tasks.task_definitions import TASKS

        task = TASKS.get(self._state.task_id, {})

        try:
            result = grade_submission(
                page=self._page,
                workspace=self._workspace,
                framework=self._framework,
                task_id=self._state.task_id,
                task=task,
            )
        except Exception as exc:
            result = {
                "total_score": 0.0,
                "functional_score": 0.0,
                "code_quality_score": 0.0,
                "visual_score": 0.0,
                "flows_passing": 0,
                "flows_total": 0,
                "feedback": f"Grading failed unexpectedly: {exc}",
            }

        self._state.concluded = True
        self._state.cumulative_reward = result["total_score"]
        self._state.flows_passing = result["flows_passing"]
        self._state.flows_total = result["flows_total"]

        return VibeCodingObservation(
            task_id=self._state.task_id,
            task_description="",
            framework_hint="",
            screenshot_b64=self._take_screenshot(),
            current_url=self._safe_url(),
            page_title=self._safe_title(),
            feedback=result["feedback"],
            reward=result["total_score"],
            cumulative_reward=result["total_score"],
            flows_passing=result["flows_passing"],
            flows_total=result["flows_total"],
            code_quality_score=result["code_quality_score"],
            step_count=self._state.step_count,
            max_steps=MAX_STEPS,
            done=True,
            workspace_files=self._list_workspace_files(),
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _safe_url(self) -> str:
        try:
            return self._page.url if self._page else ""
        except Exception:
            return ""

    def _safe_title(self) -> str:
        try:
            return self._page.evaluate("document.title", timeout=3000) if self._page else ""
        except Exception:
            return ""

    def close(self) -> None:
        """Explicit cleanup. Call this instead of relying on __del__."""
        self._stop_server()
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
                self._page = None
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
