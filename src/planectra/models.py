from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    attempt_number: int | None = None


class PlanRecord(BaseModel):
    plan_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_uuid: str
    project_name: str
    initial_prompt: str
    plan_content: str
    conversation: list[ConversationTurn] = []
    num_attempts: int = 1
    plan_issues: str | None = None
    improvement_summary: str | None = None
    rag_usefulness: str | None = None
    user_comment: str | None = None
    retrieved_plan_uuids: list[str] = []
    session_id: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict = {}


class ProjectConfig(BaseModel):
    project_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    project_dirs: list[str] = []
    use_rag: bool = True
    top_k: int = 3
    include_user_comment: bool = True
    scan_project_ids: list[str] = []
    embedding_model: str = "all-MiniLM-L6-v2"
    rag_verbosity: Literal["compact", "standard", "full"] = "standard"
    max_rag_tokens: int = 4000
    include_reasoning_in_drafts: bool = False


class GlobalConfig(BaseModel):
    version: str = "0.1.0"
    default_top_k: int = 3
    socket_path: str = ""
    dir_to_project: dict[str, str] = {}


class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.in_plan_mode = False
        self.rag_done = False
        self.initial_prompt: str | None = None
        self.iteration_count = 0
        self.retrieved_plan_uuids: list[str] = []
        self.transcript_path: str | None = None
