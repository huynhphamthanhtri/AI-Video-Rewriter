from __future__ import annotations

import logging
from typing import Any

from app.schemas.render import (
    GeminiPayloadSchema,
    MAX_FREEZE_FRAME_SECONDS,
    RenderOptions,
    SegmentPlanItem,
    clip_timestamp_to_seconds,
    srt_timestamp_to_seconds,
)

logger = logging.getLogger(__name__)


class SegmentPlanner:
    """Decides per-segment action when natural TTS duration exceeds scene duration.

    Called after generate_natural_tts(), before video cutting.
    Does not modify the payload — only returns a plan that the RenderPipeline applies.
    """

    def plan(
        self,
        payload: GeminiPayloadSchema,
        options: RenderOptions,
        natural_durations: dict[int, float],
        source_durations: dict[str, float] | None = None,
    ) -> list[SegmentPlanItem]:
        """Analyze each segment and return a plan item per segment.

        Args:
            payload: Full Gemini payload with segments and SRT.
            options: Render options (tts_fit_policy, tts_max_speed, ...).
            natural_durations: {cue_index: natural_duration_seconds} from generate_natural_tts().
            source_durations: {source_id: total_duration_seconds} — optional, defaults to 0.

        Returns:
            List of SegmentPlanItem, one per segment, ordered by segment.order.
        """
        source_durations = source_durations or {}
        segments = sorted(payload.video_segments, key=lambda s: s.order)
        srt_by_index = {item.index: item for item in payload.srt}

        plans: list[SegmentPlanItem] = []
        for segment in segments:
            srt_indices = range(segment.subtitle_start, segment.subtitle_end + 1)
            total_natural = sum(natural_durations.get(idx, 0.0) for idx in srt_indices)
            scene_duration = segment.duration_seconds
            source_id = segment.source_id or ""
            source_end_sec = clip_timestamp_to_seconds(segment.source_end)
            source_remaining = max(0.0, source_durations.get(source_id, 0.0) - source_end_sec)

            plan = self._decide(
                segment_id=segment.segment_id,
                scene_duration=scene_duration,
                total_natural=total_natural,
                source_id=source_id,
                source_remaining=source_remaining,
                policy=options.tts_fit_policy,
                max_speed=options.tts_max_speed,
            )
            plans.append(plan)

        return plans

    def _decide(
        self,
        segment_id: int,
        scene_duration: float,
        total_natural: float,
        source_id: str,
        source_remaining: float,
        policy: str,
        max_speed: float,
    ) -> SegmentPlanItem:
        plan = SegmentPlanItem(
            segment_id=segment_id,
            scene_duration=scene_duration,
            natural_voice_duration=total_natural,
            required_duration=scene_duration,
            extend_seconds=0.0,
            decision="no_change",
            source_id=source_id,
            source_remaining_seconds=source_remaining,
            speed_factor=1.0,
        )

        overflow = total_natural - scene_duration
        if overflow <= 0:
            return plan

        if policy == "extend_video":
            return self._to_extend(plan, overflow, 1.0)

        if policy in ("segment_uniform", "speed_up_voice"):
            speed_factor = min(max_speed, total_natural / scene_duration)
            plan.speed_factor = speed_factor
            plan.decision = "light_speedup"
            plan.required_duration = scene_duration
            return plan

        # Hybrid (default)
        overflow_pct = overflow / scene_duration if scene_duration > 0 else 0.0
        if overflow_pct <= 0.10:
            speed_factor = min(max_speed, total_natural / scene_duration)
            plan.speed_factor = speed_factor
            plan.decision = "light_speedup"
            plan.required_duration = scene_duration
            return plan

        # Overflow > 10% — extend_video (no speed-up, full extension)
        return self._to_extend(plan, overflow, 1.0)

    def _to_extend(
        self,
        plan: SegmentPlanItem,
        extend_seconds: float,
        speed_factor: float,
    ) -> SegmentPlanItem:
        plan.speed_factor = speed_factor
        plan.extend_seconds = extend_seconds
        plan.required_duration = plan.scene_duration + extend_seconds

        if plan.source_remaining_seconds >= extend_seconds:
            plan.decision = "footage_extend"
        else:
            plan.decision = "freeze_frame"
            capped = min(extend_seconds, MAX_FREEZE_FRAME_SECONDS)
            plan.freeze_duration = capped
            if extend_seconds > MAX_FREEZE_FRAME_SECONDS:
                plan.warning = (
                    f"Freeze frame {extend_seconds:.2f}s exceeds max "
                    f"{MAX_FREEZE_FRAME_SECONDS:.1f}s. Capped at {capped:.1f}s."
                )
                plan.extend_seconds = capped
                plan.required_duration = plan.scene_duration + capped
        return plan

    def compute_srt_shifts(
        self,
        plans: list[SegmentPlanItem],
        payload: GeminiPayloadSchema,
    ) -> dict[int, float]:
        """Accumulate extend_seconds across ordered segments to compute per-cue SRT shifts.

        Each segment's extension shifts all subsequent cues (including those
        within the same segment after the overflow point) forward.
        For simplicity, the entire segment's SRT range is shifted by the
        accumulated extension from prior segments.

        Returns: {cue_index: total_shift_seconds}
        """
        segments = sorted(payload.video_segments, key=lambda s: s.order)
        plan_by_seg = {p.segment_id: p for p in plans}
        shifts: dict[int, float] = {}
        accum = 0.0
        for seg in segments:
            p = plan_by_seg.get(seg.segment_id)
            extend = p.extend_seconds if p else 0.0
            for idx in range(seg.subtitle_start, seg.subtitle_end + 1):
                shifts[idx] = accum
            accum += extend
        return shifts
