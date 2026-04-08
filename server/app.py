"""
FastAPI app for vibe-coding-env.

WHY NOT create_app():
  OpenEnv's create_app / HTTPEnvServer creates a brand-new VibeCodingEnvironment
  instance on every POST /reset and discards it after the response. A subsequent
  POST /step hits a completely different instance where _workspace is None,
  breaking write_file, browser actions, and grading.

  Instead we keep ONE singleton environment instance alive for the lifetime of
  the server process and route all requests through it. This guarantees:
    - Playwright browser persists across steps
    - Workspace files written in one step are visible in the next
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any

from server.environment import VibeCodingEnvironment
from models import VibeCodingAction


# ── Singleton environment ─────────────────────────────────────────────────
# One instance for the lifetime of the server process. This is intentional —
# Playwright and subprocesses are expensive to create; we reuse them across
# all reset()/step() calls.
_env = VibeCodingEnvironment()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Clean up browser and server subprocess on shutdown
    _env.close()


app = FastAPI(title="vibe-coding-env", lifespan=lifespan)


# ── Request / response models ─────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_id: str | None = None

    class Config:
        extra = "allow"


class StepRequest(BaseModel):
    action: dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/reset")
def reset(request: ResetRequest = None):
    if request is None:
        request = ResetRequest()
    kwargs = request.model_dump(exclude_none=True)
    task_id = kwargs.pop("task_id", None)
    obs = _env.reset(task_id=task_id, **kwargs)
    return {"observation": obs.model_dump()}


@app.post("/step")
def step(request: StepRequest):
    action = VibeCodingAction(**request.action)
    obs = _env.step(action)
    return {"observation": obs.model_dump()}


@app.get("/state")
def state():
    return _env.state.model_dump()


@app.get("/schema")
def schema():
    return {
        "action": VibeCodingAction.model_json_schema(),
        "observation": __import__("models").VibeCodingObservation.model_json_schema(),
        "state": __import__("models").VibeCodingState.model_json_schema(),
    }
