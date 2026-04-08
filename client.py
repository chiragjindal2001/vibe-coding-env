"""
HTTP client for vibe-coding-env.
Connects to the OpenEnv server's /reset, /step, /state endpoints.
"""
from __future__ import annotations
import httpx


class VibeCodingClient:
    """Synchronous HTTP client for the vibe-coding environment."""

    def __init__(self, base_url: str = "http://127.0.0.1:7860", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def health(self) -> dict:
        r = self._client.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    def reset(self, task_id: str = None, **kwargs) -> dict:
        payload = {}
        if task_id:
            payload["task_id"] = task_id
        payload.update(kwargs)
        r = self._client.post(f"{self.base_url}/reset", json=payload, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        # OpenEnv wraps in {"observation": {...}}
        return data.get("observation", data)

    def step(self, action: dict, timeout: float = None) -> dict:
        payload = {"action": action}
        # declare_done triggers grading (Playwright flows) which can take >30s
        t = timeout or (180.0 if action.get("action_type") == "declare_done" else self.timeout)
        r = self._client.post(f"{self.base_url}/step", json=payload, timeout=t)
        r.raise_for_status()
        data = r.json()
        return data.get("observation", data)

    def state(self) -> dict:
        r = self._client.get(f"{self.base_url}/state")
        r.raise_for_status()
        return r.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
