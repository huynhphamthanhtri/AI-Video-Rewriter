from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


BatchStatus = Literal["pending", "running", "done", "error", "cancelled"]
BatchItemStatus = Literal["pending", "running", "done", "error", "cancelled"]


class BatchItemProgress(BaseModel):
    index: int = Field(ge=0)
    source_url: str
    status: BatchItemStatus = "pending"
    task_id: str | None = None
    job_id: str | None = None
    states: list[dict] = Field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    started_at: float | None = None
    ended_at: float | None = None


class BatchProgress(BaseModel):
    batch_id: str
    status: BatchStatus = "pending"
    total_items: int
    current_index: int = 0
    items: list[BatchItemProgress]
    started_at: float | None = None
    ended_at: float | None = None
    error: str | None = None


class BatchAutoSubmitResponse(BatchProgress):
    pass
