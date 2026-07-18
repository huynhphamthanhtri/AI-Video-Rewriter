from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GeminiPassMetric:
    name: str
    attempt: int
    prompt_chars: int
    response_chars: int
    duration_seconds: float
    valid: bool
    error_count: int = 0


@dataclass
class PipelineTelemetry:
    """Privacy-safe timing metrics for one automation task."""

    started_at: float = field(default_factory=time.time)
    gemini_passes: list[GeminiPassMetric] = field(default_factory=list)

    def record_gemini_pass(self, *, name: str, attempt: int, prompt_text: str,
                           response_text: str, started_at: float, valid: bool,
                           errors: list[str] | None = None) -> None:
        self.gemini_passes.append(GeminiPassMetric(
            name=name,
            attempt=attempt,
            prompt_chars=len(prompt_text),
            response_chars=len(response_text),
            duration_seconds=round(max(0.0, time.perf_counter() - started_at), 3),
            valid=valid,
            error_count=len(errors or []),
        ))

    def snapshot(self) -> dict[str, Any]:
        passes = [asdict(item) for item in self.gemini_passes]
        return {
            "elapsed_seconds": round(max(0.0, time.time() - self.started_at), 3),
            "gemini_pass_count": len(passes),
            "gemini_retry_count": sum(item["attempt"] > 1 for item in passes),
            "prompt_chars_total": sum(item["prompt_chars"] for item in passes),
            "response_chars_total": sum(item["response_chars"] for item in passes),
            "gemini_seconds_total": round(sum(item["duration_seconds"] for item in passes), 3),
            "gemini_passes": passes,
        }
