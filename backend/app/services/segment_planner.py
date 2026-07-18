from __future__ import annotations

import logging
import math
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

# Safe speed limits for bidirectional sync optimizer (hardcoded, not configurable)
# Video slowdown helps give voice more room when voice > scene
SAFE_VIDEO_MIN_SOFT = 0.92
SAFE_VIDEO_MAX_SOFT = 1.15
SAFE_VOICE_MAX_SOFT = 1.25
SYNC_TOLERANCE_SECONDS = 0.25
SYNC_TOLERANCE_RATIO = 0.05

# Hard trim guardrail: when residual even after capped speedup >= threshold,
# force output duration to voice_duration + target_padding.
# Only triggers when dead air is clearly excessive.
DEAD_AIR_HARD_TRIM_THRESHOLD = 4.0
DEAD_AIR_TARGET_PADDING = 0.25

# Soft trim guardrail: when residual after capped speedup still exceeds
# voice_duration + dynamic padding by a clear margin, apply soft normalization
# instead of keeping excessive dead air.
SOFT_DEAD_AIR_RATIO = 0.10
SOFT_DEAD_AIR_MIN_PADDING = 0.50
SOFT_DEAD_AIR_MAX_PADDING = 1.00
SOFT_DEAD_AIR_TRIGGER_SECONDS = 0.0
SOFT_DEAD_AIR_MIN_FINAL_SECONDS = 3.0


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

    @staticmethod
    def _soft_dead_air_padding(voice_duration: float) -> float:
        return min(
            SOFT_DEAD_AIR_MAX_PADDING,
            max(SOFT_DEAD_AIR_MIN_PADDING, voice_duration * SOFT_DEAD_AIR_RATIO),
        )

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
            video_speed_factor=1.0,
        )

        overflow = total_natural - scene_duration
        tolerance = max(SYNC_TOLERANCE_SECONDS, scene_duration * SYNC_TOLERANCE_RATIO)

        # Case A: within tolerance — no change
        if abs(overflow) <= tolerance:
            plan.duration_delta_seconds = 0.0
            self._attach_timing_warning(plan)
            return plan

        # ── Case B: voice longer than scene ──
        if overflow > 0:
            ratio = total_natural / scene_duration
            # Balanced: slow down video (=> scene lasts longer) and speed up voice
            #   voice / voice_speed <= scene / video_speed  (video_speed < 1.0)
            #   => voice_speed >= ratio * video_speed
            #   Equal perceptual load: video_speed = 1/sqrt(ratio), voice_speed = sqrt(ratio)
            ideal_video = 1.0 / math.sqrt(ratio)
            if ideal_video >= SAFE_VIDEO_MIN_SOFT:
                # Neither cap hit — use exact balanced fit
                video_speed = ideal_video
                voice_speed = math.sqrt(ratio)
            else:
                # Video hits min cap — voice must compensate more
                video_speed = SAFE_VIDEO_MIN_SOFT
                voice_speed = ratio * video_speed

            if voice_speed <= max_speed:
                eff_scene = scene_duration / video_speed
                plan.video_speed_factor = video_speed
                plan.speed_factor = voice_speed
                plan.decision = "sync_speed_balance"
                plan.required_duration = eff_scene
                plan.duration_delta_seconds = eff_scene - scene_duration
                self._attach_timing_warning(plan)
                return plan

            # Even with max slowdown + max speedup it doesn't fully fit
            # Fall back to existing logic (no video speed adjustment)
            return self._fallback_overflow(plan, overflow, policy, max_speed)

        # ── Case C: voice shorter than scene — conservative trim ──
        underflow_ratio = scene_duration / total_natural  # e.g. 10/9.3 = 1.075
        if underflow_ratio <= SAFE_VIDEO_MAX_SOFT:
            video_speed = underflow_ratio
            final_dur = scene_duration / video_speed
            plan.video_speed_factor = video_speed
            plan.speed_factor = 1.0
            plan.decision = "sync_video_trim_speedup"
            plan.required_duration = final_dur
            plan.duration_delta_seconds = final_dur - scene_duration  # negative
            self._attach_timing_warning(plan)
            return plan

        # Underflow too large — apply capped speedup first, then soft or hard trim
        video_speed = SAFE_VIDEO_MAX_SOFT
        speedup_duration = scene_duration / video_speed
        residual = speedup_duration - total_natural

        if residual >= DEAD_AIR_HARD_TRIM_THRESHOLD:
            target_duration = total_natural + DEAD_AIR_TARGET_PADDING
            trim_duration = max(total_natural, min(target_duration, speedup_duration))
            plan.video_speed_factor = video_speed
            plan.speed_factor = 1.0
            plan.decision = "sync_video_hard_trim"
            plan.required_duration = trim_duration
            plan.duration_delta_seconds = trim_duration - scene_duration
            plan.warning = (
                f"Scene {segment_id}: hard trim to voice+{DEAD_AIR_TARGET_PADDING:.0f}s "
                f"via video speed {video_speed:.2f}x. "
                f"Scene {scene_duration:.1f}s vs voice {total_natural:.1f}s."
            )
            self._attach_timing_warning(plan)
            return plan

        # ── Soft trim: normalize residual when still excessive after capped speedup ──
        padding = self._soft_dead_air_padding(total_natural)
        target_duration = total_natural + padding
        extra_after_target = speedup_duration - target_duration

        if extra_after_target >= SOFT_DEAD_AIR_TRIGGER_SECONDS:
            final_dur = max(target_duration, SOFT_DEAD_AIR_MIN_FINAL_SECONDS)
            final_dur = min(final_dur, speedup_duration)
            plan.video_speed_factor = video_speed
            plan.speed_factor = 1.0
            plan.decision = "sync_video_soft_trim"
            plan.required_duration = final_dur
            plan.duration_delta_seconds = final_dur - scene_duration
            plan.warning = (
                f"Scene {segment_id}: soft trim dead air via video speed {video_speed:.2f}x. "
                f"Scene {scene_duration:.1f}s vs voice {total_natural:.1f}s, "
                f"target {final_dur:.1f}s."
            )
            self._attach_timing_warning(plan)
            return plan

        final_dur = speedup_duration
        plan.video_speed_factor = video_speed
        plan.speed_factor = 1.0
        plan.decision = "sync_video_trim_speedup_capped"
        plan.required_duration = final_dur
        plan.duration_delta_seconds = final_dur - scene_duration
        plan.warning = (
            f"Scene {segment_id}: dead air reduced via video speed {video_speed:.2f}x. "
            f"Scene {scene_duration:.1f}s vs voice {total_natural:.1f}s."
        )
        self._attach_timing_warning(plan)
        return plan

    def _fallback_overflow(
        self,
        plan: SegmentPlanItem,
        overflow: float,
        policy: str,
        max_speed: float,
    ) -> SegmentPlanItem:
        """Original overflow logic (unchanged). No video speed adjustment."""
        scene_duration = plan.scene_duration
        total_natural = plan.natural_voice_duration
        source_id = plan.source_id
        source_remaining = plan.source_remaining_seconds

        if policy == "extend_video":
            return self._to_extend(plan, overflow, 1.0)

        if policy in ("segment_uniform", "speed_up_voice"):
            speed_factor = min(max_speed, total_natural / scene_duration)
            if speed_factor == max_speed:
                capped_duration = total_natural / speed_factor
                if capped_duration > scene_duration * 1.5:
                    needed_extend = capped_duration - scene_duration
                    capped_extend = min(needed_extend, scene_duration)
                    plan = self._to_extend(plan, capped_extend, speed_factor)
                    plan.overrun_seconds = max(0.0, needed_extend - capped_extend)
                    if plan.decision == "freeze_frame":
                        residual = capped_extend - plan.extend_seconds
                        if residual > 0:
                            plan.speed_factor = min(max_speed, total_natural / max(scene_duration + plan.extend_seconds, 0.1))
                            plan.decision = "hybrid_extend_speedup"
                    plan.duration_delta_seconds = plan.required_duration - scene_duration
                    self._attach_timing_warning(plan)
                    return plan
            plan.speed_factor = speed_factor
            plan.decision = "light_speedup"
            plan.required_duration = scene_duration
            plan.duration_delta_seconds = 0.0
            self._attach_timing_warning(plan)
            return plan

        # Hybrid (default)
        plan = self._to_extend(plan, overflow, 1.0)
        if plan.decision == "freeze_frame":
            residual = overflow - plan.extend_seconds
            if residual > 0:
                speed_factor = min(max_speed, total_natural / max(scene_duration + plan.extend_seconds, 0.1))
                plan.speed_factor = speed_factor
                plan.decision = "hybrid_extend_speedup"
        plan.duration_delta_seconds = plan.required_duration - scene_duration
        self._attach_timing_warning(plan)
        return plan

    def _to_extend(
        self,
        plan: SegmentPlanItem,
        extend_seconds: float,
        speed_factor: float,
    ) -> SegmentPlanItem:
        plan.speed_factor = speed_factor
        plan.extend_seconds = extend_seconds
        plan.required_duration = plan.scene_duration + extend_seconds
        plan.duration_delta_seconds = plan.required_duration - plan.scene_duration

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
                plan.duration_delta_seconds = plan.required_duration - plan.scene_duration
        self._attach_timing_warning(plan)
        return plan

    def _attach_timing_warning(self, plan: SegmentPlanItem) -> None:
        voice_speed = plan.speed_factor or 1.0
        post_voice = plan.natural_voice_duration / voice_speed
        residual = plan.required_duration - post_voice
        parts = []
        if residual >= 2.0:
            parts.append(f"SEVERE_DEAD_AIR: residual={residual:.1f}s after sync={plan.decision}")
        elif residual >= 1.0:
            parts.append(f"DEAD_AIR: residual={residual:.1f}s after sync={plan.decision}")
        if residual <= -0.5:
            parts.append(f"VOICE_OVERFLOW: voice overflows scene by {abs(residual):.1f}s")
        if voice_speed >= 1.10:
            parts.append(f"VOICE_SPEED_LIMIT: voice speed={voice_speed:.2f}x, no room for longer voice")
        if plan.decision == "sync_video_trim_speedup_capped" and residual >= 0.5:
            parts.append(f"CAP_REACHED_STILL_MISMATCH: capped at video_speed_max={SAFE_VIDEO_MAX_SOFT:.2f}x but residual={residual:.1f}s remains")
        if plan.decision == "sync_video_hard_trim":
            parts.append(f"HARD_TRIM_DEAD_AIR: trimmed output to voice+{DEAD_AIR_TARGET_PADDING:.0f}s after residual exceeded {DEAD_AIR_HARD_TRIM_THRESHOLD:.1f}s")
        if plan.decision == "sync_video_soft_trim":
            trim_padding = max(0.0, plan.required_duration - plan.natural_voice_duration)
            parts.append(f"SOFT_TRIM_DEAD_AIR: trimmed to voice+{trim_padding:.1f}s padding")
        if parts:
            suffix = " | ".join(parts)
            plan.warning = (plan.warning + " | " + suffix) if plan.warning else suffix

    def compute_srt_shifts(
        self,
        plans: list[SegmentPlanItem],
        payload: GeminiPayloadSchema,
    ) -> dict[int, float]:
        """Accumulate duration_delta_seconds across ordered segments to compute per-cue SRT shifts.

        Each segment's duration delta (from extend, video_speed_factor, or both)
        shifts all subsequent cues (including those within the same segment)
        forward or backward.

        Returns: {cue_index: total_shift_seconds}
        """
        segments = sorted(payload.video_segments, key=lambda s: s.order)
        plan_by_seg = {p.segment_id: p for p in plans}
        shifts: dict[int, float] = {}
        accum = 0.0
        for seg in segments:
            p = plan_by_seg.get(seg.segment_id)
            delta = p.duration_delta_seconds if p else 0.0
            for idx in range(seg.subtitle_start, seg.subtitle_end + 1):
                shifts[idx] = accum
            accum += delta
        return shifts
