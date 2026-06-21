from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.versions import (
    CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
    CURRENT_PRESET_SCHEMA_VERSION,
    CURRENT_PROMPT_TEMPLATE_VERSION,
)
from app.models.prompt_run import PromptRunORM
from app.schemas.prompt import PromptRunCreate, PromptRunRead, PromptRunStats

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {"youtube_url", "youtube_urls", "ytdlp_cookies_file"}


def _sanitize_form_data(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in SENSITIVE_FIELDS}


class PromptRunService:
    def __init__(self, db: Session):
        self.db = db

    def record_run(self, data: PromptRunCreate) -> PromptRunRead | None:
        try:
            prompt_bytes = data.prompt_text.encode("utf-8") if data.prompt_text else b""
            snapshot = _sanitize_form_data(data.form_data)
            run = PromptRunORM(
                id=str(uuid.uuid4()),
                created_at=time.time(),
                status=data.status,
                prompt_chars=len(prompt_bytes) if prompt_bytes else None,
                prompt_hash=hashlib.sha256(prompt_bytes).hexdigest() if prompt_bytes else None,
                health_score=data.health_score,
                health_level=data.health_level,
                error_message=data.error_message,
                preset_name=snapshot.get("preset_name"),
                rewrite_style=snapshot.get("rewrite_style"),
                duration_ms=data.duration_ms,
                form_snapshot_json=json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
                preset_schema_version=CURRENT_PRESET_SCHEMA_VERSION,
                prompt_template_version=CURRENT_PROMPT_TEMPLATE_VERSION,
                json_output_schema_version=CURRENT_JSON_OUTPUT_SCHEMA_VERSION,
            )
            self.db.add(run)
            self.db.commit()
            return PromptRunRead.model_validate(run, from_attributes=True)
        except Exception as e:
            logger.warning("Failed to record prompt run: %s", e)
            return None

    def get_stats(self, since: float | None = None) -> PromptRunStats:
        base = select(PromptRunORM)
        if since is not None:
            base = base.where(PromptRunORM.created_at >= since)

        total = self.db.scalar(
            select(func.count()).select_from(PromptRunORM).where(*(base.whereclause,) if since else ())
        )
        success = (
            self.db.scalar(
                select(func.count())
                .select_from(PromptRunORM)
                .where(PromptRunORM.status == "success")
                .where(*(base.whereclause,) if since else ())
            )
            or 0
        )

        avg_health = self.db.scalar(
            select(func.avg(PromptRunORM.health_score))
            .where(PromptRunORM.status == "success")
            .where(*(base.whereclause,) if since else ())
        )

        top_presets_rows = (
            self.db.execute(
                select(PromptRunORM.preset_name, func.count().label("c"))
                .where(PromptRunORM.preset_name.isnot(None))
                .where(*(base.whereclause,) if since else ())
                .group_by(PromptRunORM.preset_name)
                .order_by(desc("c"))
                .limit(10)
            )
            .all()
        )

        top_styles_rows = (
            self.db.execute(
                select(PromptRunORM.rewrite_style, func.count().label("c"))
                .where(PromptRunORM.rewrite_style.isnot(None))
                .where(*(base.whereclause,) if since else ())
                .group_by(PromptRunORM.rewrite_style)
                .order_by(desc("c"))
                .limit(10)
            )
            .all()
        )

        daily_rows = (
            self.db.execute(
                select(
                    func.date(PromptRunORM.created_at, "unixepoch").label("day"),
                    func.count().label("c"),
                    func.avg(PromptRunORM.health_score).label("avg_h"),
                )
                .where(PromptRunORM.created_at >= (time.time() - 30 * 86400))
                .group_by(func.date(PromptRunORM.created_at, "unixepoch"))
                .order_by(desc("day"))
                .limit(30)
            )
            .all()
        )

        now = time.time()
        last_7d_start = now - 7 * 86400
        prev_7d_start = now - 14 * 86400
        last_7d_count = (
            self.db.scalar(
                select(func.count())
                .select_from(PromptRunORM)
                .where(PromptRunORM.created_at >= last_7d_start)
            )
            or 0
        )
        prev_7d_count = (
            self.db.scalar(
                select(func.count())
                .select_from(PromptRunORM)
                .where(PromptRunORM.created_at >= prev_7d_start)
                .where(PromptRunORM.created_at < last_7d_start)
            )
            or 0
        )

        return PromptRunStats(
            total_runs=total or 0,
            success_count=success,
            error_count=(total or 0) - success,
            avg_health_score=round(float(avg_health), 1) if avg_health is not None else None,
            top_presets=[{"name": r[0], "count": r[1]} for r in top_presets_rows],
            top_rewrite_styles=[{"style": r[0], "count": r[1]} for r in top_styles_rows],
            daily_counts=[
                {
                    "date": r[0],
                    "count": r[1],
                    "avg_health": round(float(r[2]), 1) if r[2] else None,
                }
                for r in daily_rows
            ],
            last_7d_count=last_7d_count,
            prev_7d_count=prev_7d_count,
        )
