from __future__ import annotations
from typing import Optional
from pydantic import Field, ConfigDict
from openenv.core.env_server import Action, Observation, State


class VibeCodingAction(Action):
    model_config = ConfigDict(extra="ignore")  # silently drop unknown fields (e.g. "message")

    action_type: str
    file_path: Optional[str] = None
    file_content: Optional[str] = None
    url: Optional[str] = None
    selector: Optional[str] = None
    value: Optional[str] = None
    script: Optional[str] = None
    command: Optional[str] = None


class VibeCodingObservation(Observation):
    task_id: str = ""
    task_description: str = ""
    framework_hint: str = ""
    screenshot_b64: Optional[str] = None
    current_url: str = ""
    page_title: str = ""
    feedback: str = ""
    last_action_error: Optional[str] = None
    reward: float = 0.0
    cumulative_reward: float = 0.0
    flows_passing: int = 0
    flows_total: int = 0
    code_quality_score: float = 0.0
    step_count: int = 0
    max_steps: int = 25
    done: bool = False
    workspace_files: list = Field(default_factory=list)


class VibeCodingState(State):
    task_id: str = ""
    framework: str = ""
    current_url: str = ""
    flows_passing: int = 0
    flows_total: int = 0
    step_count: int = 0
    cumulative_reward: float = 0.0
    concluded: bool = False
    workspace_files: list = Field(default_factory=list)
