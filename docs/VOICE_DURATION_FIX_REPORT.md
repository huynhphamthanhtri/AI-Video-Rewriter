# Voice Duration Fix — Final Implementation Report

## 1. Final Summary

The voice-duration fix is complete.

TTS duration is now measured before video cutting. The render pipeline generates natural TTS once, probes the real audio durations, and uses those durations as the timing source of truth. Voice audio is no longer trimmed with `atrim` to force-fit scene duration.

When voice is longer than the original scene, `SegmentPlanner` decides whether to use `light_speedup`, `footage_extend`, or `freeze_frame`. Video segments are extended using available source footage when possible; otherwise the final frame is frozen for the required duration. Subtitle timing follows the adjusted voice timeline by mutating `payload.srt` before SRT generation.

## 2. Final Files Changed

| File | Purpose |
|------|---------|
| `backend/app/schemas/render.py` | Added TTS fit policies, `freeze_frame_duration`, `SegmentPlanItem`, `MAX_FREEZE_FRAME_SECONDS`, and `seconds_to_srt_timestamp()`. |
| `backend/app/services/tts_tools.py` | Split natural TTS generation from final voiceover building; removed `atrim` trimming; reused existing generated TTS files. |
| `backend/app/services/segment_planner.py` | New planner that uses real TTS durations to choose `no_change`, `light_speedup`, `footage_extend`, or `freeze_frame`. |
| `backend/app/services/video_tools.py` | Reordered render pipeline, applied segment plans to payload, added freeze-frame cutting, serialized `segment_plan`, fixed FFmpeg `tpad` behavior. |
| `backend/app/services/json_validator.py` | Skips duration auto-fix when the TTS timing planner owns duration alignment. |
| `backend/app/api/routes.py` | Passes render options into JSON validation so TTS planner mode can skip duration auto-fix. |
| `backend/app/services/gemini_automation.py` | Passes render options into JSON validation when available. |
| `tests/test_json_validator.py` | Added tests for TTS hybrid skip and legacy `segment_uniform` auto-fix behavior. |
| `tests/test_subtitle_generator.py` | Added test proving adjusted `payload.srt` timestamps are emitted directly. |
| `tests/test_voice_duration_pipeline.py` | Added integration-style timing tests with stubbed natural TTS durations. |
| `tests/test_voice_duration_mock_e2e.py` | Added mocked local E2E test covering `footage_extend` and `freeze_frame`. |
| `docs/VOICE_DURATION_FIX_REPORT.md` | Final implementation report. |

## 3. Final Pipeline

```text
download sources
→ generate natural TTS once
→ ffprobe TTS durations
→ SegmentPlanner
→ mutate payload timing/source_end/freeze_frame
→ cut/concat video
→ build voiceover from existing TTS files
→ mix voiceover
→ generate subtitle from adjusted payload.srt
→ burn/export
```

## 4. Critical Bugs Found and Fixed

### Bug 1 — Original atrim voice cut

Root cause:
`TtsVoiceoverService.generate_voiceover()` applied `atrim=0:{slot}` when generated audio exceeded the cue slot, silently cutting voice audio.

Fix:
TTS generation was split into `generate_natural_tts()` and final voiceover building. Natural audio is silence-cleaned only, probed, and never trimmed. Overflow is handled by SegmentPlanner/video extension.

Test evidence:
`tests/test_voice_duration_mock_e2e.py` verifies voiceover duration equals 5.0s and 6.0s in overflow scenarios, with output video duration matching or exceeding voiceover duration.

### Bug 2 — Hybrid policy speed-first deviation

Root cause:
The first SegmentPlanner implementation attempted max speed first for large hybrid overflows, which could convert a >10% overflow into `light_speedup` instead of extension.

Fix:
Hybrid policy now follows the approved rule: overflow ratio <= 10% and required speed <= max speed uses `light_speedup`; otherwise it uses video extension with `speed_factor = 1.0`.

Test evidence:
`tests/test_voice_duration_pipeline.py` verifies 4.3s voice over 4.0s scene uses `light_speedup`, while 5.0s voice over 4.0s scene uses `footage_extend` with `speed_factor = 1.0`.

### Bug 3 — Freeze frame double-extension

Root cause:
The payload mutation initially extended `source_end` for all decisions and also set `freeze_frame_duration`. For `freeze_frame`, this could produce `scene + extend + freeze`.

Fix:
`source_end` is extended only for `footage_extend`. For `freeze_frame`, `source_end` is unchanged and only `freeze_frame_duration` is set.

Test evidence:
`tests/test_voice_duration_pipeline.py` verifies freeze with original 4.0s scene and 2.0s freeze produces final segment duration 6.0s, not 8.0s. Mocked E2E verifies final freeze output video duration is 6.0s.

### Bug 4 — Subtitle last cue not extending to voice end

Root cause:
SRT shifting only moved subsequent cues by accumulated segment extension. It did not extend the current segment's last cue to the adjusted voice end.

Fix:
`_apply_segment_plan_to_payload()` extends the last cue end for each extended segment by `extend_seconds` after applying accumulated timeline shifts.

Test evidence:
`tests/test_voice_duration_pipeline.py` verifies the last cue end extends from 4.0s to 5.0s for `footage_extend` and to 6.0s for `freeze_frame`. `tests/test_subtitle_generator.py` verifies adjusted `payload.srt` timestamps are emitted directly.

### Bug 5 — FFmpeg tpad trimmed by `-t`

Root cause:
The first freeze-frame cutter command allowed `-t` to limit output duration, trimming frames added by `tpad`. `tpad` was also placed after `fps`, which did not produce the intended final duration in the E2E case.

Fix:
For freeze segments, `-t` is placed before `-i` to limit input read, and `tpad=stop_mode=clone:stop_duration=X` is placed before `fps,setpts,setsar` in the filter chain.

Test evidence:
The mocked E2E initially failed with freeze output duration 4.0s. After the fix, `tests/test_voice_duration_mock_e2e.py` passes and reports freeze output video duration 6.0s.

## 5. render_plan.json Format

Example:

```json
{
  "segment_plan": [
    {
      "segment_id": 1,
      "natural_voice_duration": 6.0,
      "extend_seconds": 2.0,
      "decision": "freeze_frame",
      "source_id": "source_1",
      "source_remaining_seconds": 0.0,
      "speed_factor": 1.0,
      "freeze_duration": 2.0,
      "warning": "",
      "original_scene_duration": 4.0,
      "final_scene_duration": 6.0
    }
  ]
}
```

## 6. Test Results

Commands run:

```powershell
python.exe -m pytest tests/test_json_validator.py -q
python.exe -m pytest tests/test_subtitle_generator.py -q
python.exe -m pytest tests/test_voice_duration_pipeline.py -q
python.exe -m pytest tests/test_voice_duration_mock_e2e.py -q -s
python.exe -m pytest tests/ -q
```

Results:

```text
Unit tests: passed
Integration tests: passed
Mocked E2E: passed
Full suite: 276 passed
```

## 7. E2E Verification

Mocked E2E summary file:

```text
E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\summary.json
```

### Case A — footage_extend

Artifacts:

```text
output video:     E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\footage_extend\outputs\footage_extend_20260623_013925\footage_extend_final.mp4
render_plan.json: E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\footage_extend\outputs\footage_extend_20260623_013925\footage_extend_render_plan.json
generated SRT:    E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\footage_extend\outputs\footage_extend_20260623_013925\footage_extend_subtitle.srt
voiceover wav:    E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\footage_extend\outputs\footage_extend_20260623_013925\voiceover.wav
```

Verification:

```text
video_duration: 5.0
voiceover_duration: 5.0
decision: footage_extend
original_scene_duration: 4.0
final_scene_duration: 5.0
extend_seconds: 1.0
freeze_duration: null
```

### Case B — freeze_frame

Artifacts:

```text
output video:     E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\freeze_frame\outputs\freeze_frame_20260623_013926\freeze_frame_final.mp4
render_plan.json: E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\freeze_frame\outputs\freeze_frame_20260623_013926\freeze_frame_render_plan.json
generated SRT:    E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\freeze_frame\outputs\freeze_frame_20260623_013926\freeze_frame_subtitle.srt
voiceover wav:    E:\AUTO_REVIEW\outputs\_step8_voice_duration_e2e\freeze_frame\outputs\freeze_frame_20260623_013926\voiceover.wav
```

Verification:

```text
video_duration: 6.0
voiceover_duration: 6.0
decision: freeze_frame
original_scene_duration: 4.0
final_scene_duration: 6.0
extend_seconds: 2.0
freeze_duration: 2.0
```

## 8. Remaining Unverified Item

Real external VieNeu TTS API was not verified in Step 8. Mocked local TTS WAVs were used to avoid external dependency while still exercising the real downstream render pipeline.

## 9. Known Risks

- Real TTS provider latency/failure can still affect render completion and should be handled operationally.
- Long freeze frames may look visually static, especially when overflow is large.
- Large voice overflow may need future scene replacement, cue splitting, or script shortening rather than long freezes.
- Freeze frame duration is capped by `MAX_FREEZE_FRAME_SECONDS = 3.0`; overflow beyond the cap emits a warning and remains a quality risk.

## 10. Post-Merge Validation

Mocked E2E is passing, but real external VieNeu TTS was not exercised during Step 8. This validation is not required before merge, but should be performed after deployment or in the first internal production verification run.

### Scenario 1 — footage_extend

Requirements:

```text
real VieNeu request
voice_duration > scene_duration
source footage available
```

Collect:

```text
render_plan.json
output video
voiceover wav
ffprobe durations
```

### Scenario 2 — freeze_frame

Requirements:

```text
real VieNeu request
voice_duration > scene_duration
no remaining source footage
```

Collect:

```text
render_plan.json
output video
voiceover wav
ffprobe durations
```

### Success Criteria

```text
voice is not trimmed
subtitle reaches voice end
video duration >= voice duration
render_plan decision matches expected behavior
```

## 11. Final Status

READY FOR FINAL REVIEW
