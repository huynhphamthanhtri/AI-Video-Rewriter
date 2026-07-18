import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.render import GeminiPayloadSchema, RenderOptions, srt_timestamp_to_seconds
from app.services.tts_tools import (
    TTS_STUDIO_MAX_CHARS,
    TTS_MAX_PAIR_AUTO_SHIFT_SECONDS,
    TTS_MAX_TOTAL_AUTO_SHIFT_SECONDS,
    EdgeTtsSynthesizer,
    TtsCuePlan,
    TtsVoiceoverService,
    _run,
    alternate_edge_tts_voice,
    generate_standalone_tts,
    list_edge_tts_voices,
    resolve_edge_tts_voice,
    tts_studio_outputs_dir,
)


class TestRun:
    def test_missing_executable_raises_readable_error(self):
        with pytest.raises(RuntimeError, match="Không tìm thấy executable"):
            _run(["nonexistent_cmd_fixture"])


class TestEdgeVoiceResolution:
    def _payload(self, language: str) -> GeminiPayloadSchema:
        return GeminiPayloadSchema.model_validate({
            "metadata": {"video_title": "Test", "rewrite_style": "Viral", "target_audience": "all", "tone": "neutral", "target_duration": "short", "target_language": language},
            "rewrite_script": {"full_text": "test"},
            "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:01,000", "text": "test"}],
            "video_segments": [{"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:01.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "test"}],
        })

    def test_japanese_auto_defaults_to_nanami(self):
        payload = self._payload("Japanese")
        voice = resolve_edge_tts_voice(RenderOptions(tts_voice_id="auto", tts_voice_gender="female"), payload)
        assert voice["id"] == "ja-JP-NanamiNeural"

    def test_wrong_locale_specific_voice_is_ignored(self):
        payload = self._payload("Japanese")
        voice = resolve_edge_tts_voice(RenderOptions(tts_voice_id="vi-VN-HoaiMyNeural", tts_voice_gender="female"), payload)
        assert voice["id"] == "ja-JP-NanamiNeural"

    def test_matching_locale_specific_voice_is_kept(self):
        payload = self._payload("English")
        voice = resolve_edge_tts_voice(RenderOptions(tts_voice_id="en-US-GuyNeural", tts_voice_gender="female"), payload)
        assert voice["id"] == "en-US-GuyNeural"

    def test_korean_auto_male_uses_korean_male_voice(self):
        payload = self._payload("Korean")
        voice = resolve_edge_tts_voice(RenderOptions(tts_voice_id="auto", tts_voice_gender="male"), payload)
        assert voice["id"] == "ko-KR-InJoonNeural"

    def test_legacy_vieneu_options_migrate_to_edge(self):
        options = RenderOptions.model_validate({"tts_engine": "vieneu_turbo", "tts_voice_mode": "clone", "tts_voice_id": "ngoc"})
        assert options.tts_engine == "edge_tts"
        assert options.tts_voice_mode == "preset"
        assert options.tts_voice_id == "auto"

    def test_alternate_voice_same_locale(self):
        alt = alternate_edge_tts_voice({"id": "vi-VN-HoaiMyNeural", "locale": "vi-VN"})
        assert alt is not None
        assert alt["id"] == "vi-VN-NamMinhNeural"


class TestSplitLongCue:
    def test_short_text_no_split(self):
        service = TtsVoiceoverService()
        text = "Hello world"
        parts = service._split_long_cue(text, max_chars=200)
        assert parts == [text]

    def test_long_text_split_by_sentence(self):
        service = TtsVoiceoverService()
        text = "First sentence. Second sentence. Third sentence."
        parts = service._split_long_cue(text, max_chars=20)
        assert len(parts) >= 2


class TestEdgeTtsRetry:
    def test_is_transient_error_detects_no_audio(self):
        from app.services.tts_tools import EdgeTtsSynthesizer
        exc = Exception("No audio was received. Please verify that your parameters are correct.")
        assert EdgeTtsSynthesizer._is_transient_error(exc)

    def test_is_transient_error_detects_connection(self):
        from app.services.tts_tools import EdgeTtsSynthesizer
        exc = Exception("Connection refused")
        assert EdgeTtsSynthesizer._is_transient_error(exc)

    def test_is_transient_error_ignores_other(self):
        from app.services.tts_tools import EdgeTtsSynthesizer
        exc = Exception("Invalid voice ID: foobar")
        assert not EdgeTtsSynthesizer._is_transient_error(exc)

    def test_is_transient_error_case_insensitive(self):
        from app.services.tts_tools import EdgeTtsSynthesizer
        exc = Exception("NO AUDIO WAS RECEIVED")
        assert EdgeTtsSynthesizer._is_transient_error(exc)


class TestNormalizeTtsText:
    def test_newline_replaced_with_space(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("giữa đường\ncao tốc")
        assert result == "giữa đường cao tốc"

    def test_carriage_return_newline_replaced(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("dòng 1\r\ndòng 2")
        assert result == "dòng 1 dòng 2"

    def test_multiple_whitespace_collapsed(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("a    b\t\nc")
        assert result == "a b c"

    def test_control_chars_removed(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("xin\x00 chào\x1f bạn")
        assert result == "xin chào bạn"

    def test_leading_trailing_stripped(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("  \n  hello world \t  ")
        assert result == "hello world"

    def test_vietnamese_diacritics_preserved(self):
        from app.services.tts_tools import _normalize_tts_text
        text = "Sự thật kinh hoàng đằng sau đứa trẻ"
        result = _normalize_tts_text(text)
        assert result == text

    def test_clean_text_unchanged(self):
        from app.services.tts_tools import _normalize_tts_text
        text = "Hello world. This is a test."
        result = _normalize_tts_text(text)
        assert result == text

    def test_empty_string_returns_empty(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("")
        assert result == ""

    def test_only_whitespace_returns_empty(self):
        from app.services.tts_tools import _normalize_tts_text
        result = _normalize_tts_text("   \n  \t  ")
        assert result == ""


class TestLoggerDefined:
    def test_logger_is_defined(self):
        import logging
        from app.services import tts_tools
        assert isinstance(tts_tools.logger, logging.Logger)
        assert tts_tools.logger.name == "app.services.tts_tools"

    def test_logger_warning_does_not_crash(self, caplog):
        from app.services.tts_tools import logger
        logger.warning("test warning message")
        assert "test warning message" in caplog.text


class TestGenerateVoiceoverTiming:
    """Tests that generate_voiceover() uses SRT start timing directly without global re-pin."""

    def _make_silence_wav(self, path, duration_sec=0.5):
        import struct
        import wave
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = 16000
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(struct.pack("<h", 0) * int(rate * duration_sec))

    def test_generate_voiceover_uses_srt_start_without_global_repin(self, tmp_path, monkeypatch):
        from app.services.tts_tools import TtsVoiceoverService
        monkeypatch.setattr("app.services.tts_tools._run", lambda *a, **kw: None)
        monkeypatch.setattr("app.services.tts_tools.probe_audio_duration", lambda p: 1.5)

        payload = GeminiPayloadSchema.model_validate({
            "metadata": {"video_title": "T", "rewrite_style": "Viral", "target_audience": "all", "tone": "neutral", "target_duration": "short", "target_language": "Vietnamese"},
            "rewrite_script": {"full_text": "test"},
            "srt": [
                {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000", "text": "One"},
                {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000", "text": "Two"},
            ],
            "video_segments": [
                {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:04.000", "subtitle_start": 1, "subtitle_end": 2, "scene_description": "s"},
            ],
        })
        output_dir = tmp_path / "output"
        ws = tmp_path / "ws"
        output_dir.mkdir()
        ws.mkdir()
        fitted = ws / "tts" / "fitted"
        fitted.mkdir(parents=True)
        for i in [1, 2]:
            self._make_silence_wav(fitted / f"cue_{i:04d}.wav")
        options = RenderOptions(tts_engine="edge_tts", tts_voice_mode="preset")
        result = TtsVoiceoverService().generate_voiceover(
            payload, output_dir, ws, options, video_duration=10.0,
            segment_speeds={1: 1.0},
        )
        import json
        from pathlib import Path
        plan_path = result.get("tts_plan_path")
        if plan_path:
            plan_path = Path(plan_path)
        else:
            plan_path = output_dir / "tts_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {"cues": []}
        cues = plan.get("cues", []) if isinstance(plan, dict) else plan
        if not cues:
            return
        start_0 = cues[0].get("start_seconds", 0)
        start_1 = cues[1].get("start_seconds", 0)
        assert start_0 == 0.0, f"cue 1 should start at 0.0, got {start_0}"
        assert start_1 == 2.0, f"cue 2 should start at 2.0 (its SRT start), got {start_1}"

    def test_generate_voiceover_does_not_mutate_payload_srt_timing(self, tmp_path, monkeypatch):
        from app.services.tts_tools import TtsVoiceoverService
        monkeypatch.setattr("app.services.tts_tools._run", lambda *a, **kw: None)
        monkeypatch.setattr("app.services.tts_tools.probe_audio_duration", lambda p: 1.0)

        payload = GeminiPayloadSchema.model_validate({
            "metadata": {"video_title": "T", "rewrite_style": "Viral", "target_audience": "all", "tone": "neutral", "target_duration": "short", "target_language": "Vietnamese"},
            "rewrite_script": {"full_text": "test"},
            "srt": [
                {"index": 1, "start": "00:00:00,000", "end": "00:00:03,000", "text": "One"},
            ],
            "video_segments": [
                {"segment_id": 1, "order": 1, "source_start": "00:00:00.000", "source_end": "00:00:03.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "s"},
            ],
        })
        orig_start = payload.srt[0].start
        orig_end = payload.srt[0].end
        output_dir = tmp_path / "output"
        ws = tmp_path / "ws"
        output_dir.mkdir()
        ws.mkdir()
        fitted = ws / "tts" / "fitted"
        fitted.mkdir(parents=True)
        self._make_silence_wav(fitted / "cue_0001.wav")
        options = RenderOptions(tts_engine="edge_tts", tts_voice_mode="preset")
        TtsVoiceoverService().generate_voiceover(
            payload, output_dir, ws, options, video_duration=5.0,
            segment_speeds={1: 1.0},
        )
        assert payload.srt[0].start == orig_start, "payload SRT start was mutated"
        assert payload.srt[0].end == orig_end, "payload SRT end was mutated"


class TestGenerateStandaloneTts:
    def test_rejects_invalid_voice(self):
        with pytest.raises(ValueError, match="Voice.*không tồn tại"):
            generate_standalone_tts("nonexistent-voice", "Hello")

    def test_rejects_empty_text(self):
        valid_id = list_edge_tts_voices()[0]["id"]
        with pytest.raises(ValueError, match="Text rỗng"):
            generate_standalone_tts(valid_id, "   ")

    def test_rejects_long_text(self):
        valid_id = list_edge_tts_voices()[0]["id"]
        long_text = "a" * (TTS_STUDIO_MAX_CHARS + 1)
        with pytest.raises(ValueError, match="Text quá dài"):
            generate_standalone_tts(valid_id, long_text)

    def test_rejects_invalid_format(self):
        valid_id = list_edge_tts_voices()[0]["id"]
        with pytest.raises(ValueError, match="Format không hợp lệ"):
            generate_standalone_tts(valid_id, "Hello", output_format="ogg")

    @patch.object(EdgeTtsSynthesizer, "synthesize_to_file")
    def test_wav_unique_output(self, mock_synth):
        """Two calls produce unique file names and both are .wav."""
        mock_synth.return_value = None
        valid_id = list_edge_tts_voices()[0]["id"]
        p1 = generate_standalone_tts(valid_id, "Hello world")
        p2 = generate_standalone_tts(valid_id, "Second text")
        assert isinstance(p1, Path)
        assert isinstance(p2, Path)
        assert p1.suffix == ".wav"
        assert p2.suffix == ".wav"
        assert p1 != p2, "Output file names must be unique"
        assert p1.parent == tts_studio_outputs_dir()
        assert p2.parent == tts_studio_outputs_dir()

    @patch.object(EdgeTtsSynthesizer, "synthesize_to_file")
    @patch("app.services.tts_tools._run")
    def test_mp3_converts_and_returns_mp3(self, mock_run, mock_synth):
        """MP3 format calls _run for conversion and returns .mp3."""
        mock_synth.return_value = None
        mock_run.return_value = None
        valid_id = list_edge_tts_voices()[0]["id"]
        path = generate_standalone_tts(valid_id, "Hello", output_format="mp3")
        assert isinstance(path, Path)
        assert path.suffix == ".mp3"
        assert mock_run.called
        call_args = mock_run.call_args
        assert call_args is not None
        assert "-codec:a" in call_args[0][0]
        assert "libmp3lame" in call_args[0][0]


class TestTtsTimingOverlap:
    def test_overlapping_plans_raises(self):
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="Cue 1", start_seconds=0.0, end_seconds=10.0, slot_duration=10.0, generated_duration=9.0, applied_speed=1.0, final_duration=9.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="Cue 2 overlaps", start_seconds=5.0, end_seconds=8.0, slot_duration=3.0, generated_duration=3.0, applied_speed=1.0, final_duration=3.0, status="ok"),
        ]
        with pytest.raises(RuntimeError, match="TTS_TIMING_OVERLAP"):
            TtsVoiceoverService._validate_no_voiceover_overlap(plans)

    def test_non_overlapping_plans_pass(self):
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="Cue 1", start_seconds=0.0, end_seconds=6.0, slot_duration=6.0, generated_duration=5.0, applied_speed=1.0, final_duration=5.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="Cue 2", start_seconds=6.0, end_seconds=12.0, slot_duration=6.0, generated_duration=5.0, applied_speed=1.0, final_duration=5.0, status="ok"),
        ]
        try:
            TtsVoiceoverService._validate_no_voiceover_overlap(plans)
        except RuntimeError:
            pytest.fail("Non-overlapping plans should not raise")

    def test_tiny_overlap_below_threshold_passes(self):
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="Cue 1", start_seconds=0.0, end_seconds=6.05, slot_duration=6.05, generated_duration=6.0, applied_speed=1.0, final_duration=6.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="Cue 2", start_seconds=6.0, end_seconds=12.0, slot_duration=6.0, generated_duration=5.0, applied_speed=1.0, final_duration=5.0, status="ok"),
        ]
        try:
            TtsVoiceoverService._validate_no_voiceover_overlap(plans)
        except RuntimeError:
            pytest.fail("Tiny overlap below 0.25s threshold should not raise")


class TestReconcilePayloadTtsTimeline:

    @staticmethod
    def _make_payload(cues: list[dict]) -> GeminiPayloadSchema:
        srt_items = []
        for c in cues:
            srt_items.append({
                "index": c["index"],
                "start": c["start"],
                "end": c["end"],
                "text": c.get("text", "test"),
            })
        return GeminiPayloadSchema.model_validate({
            "metadata": {"video_title": "Test", "rewrite_style": "Viral", "target_audience": "all", "tone": "neutral", "target_duration": "short"},
            "rewrite_script": {"full_text": "test"},
            "srt": srt_items,
            "video_segments": [],
        })

    def test_shift_1_346s_passes(self):
        """Cue 1 overflows slot by 1.296s => cue 2 needs 1.346s shift (real case)."""
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000"},
            {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=2.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=3.296, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=2.0, end_seconds=4.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["applied"] is True
        assert len(report["adjustments"]) == 1
        adj_cue2 = report["adjustments"][0]
        assert adj_cue2["cue_index"] == 2
        assert adj_cue2["shift_seconds"] == pytest.approx(1.346, abs=0.001)

    def test_fail_pair_cap_raises_and_writes_file(self, tmp_path):
        """Shift above the configured pair cap raises and writes diagnostics."""
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000"},
            {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=2.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=13.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=2.0, end_seconds=4.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
        ]
        with pytest.raises(RuntimeError, match="TTS_TIMING_RECONCILE_FAILED"):
            TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans, output_dir=tmp_path)

        fail_file = tmp_path / "tts_timeline_reconciliation_failed.json"
        assert fail_file.exists()
        data = json.loads(fail_file.read_text(encoding="utf-8"))
        assert data["failed"] is True
        assert data["failure_code"] == "TTS_TIMING_RECONCILE_FAILED"
        assert data["failed_cue_index"] == 2
        assert data["required_shift_seconds"] > TTS_MAX_PAIR_AUTO_SHIFT_SECONDS

    def test_total_cap_raises_and_writes_file(self, tmp_path):
        """Cumulative shift above the configured total cap raises diagnostics."""
        payload = self._make_payload([
            {"index": i, "start": f"00:00:0{idx * 5 // 10},{idx * 5 % 10 * 100:03d}", "end": f"00:00:0{(idx + 1) * 5 // 10},{(idx + 1) * 5 % 10 * 100:03d}"}
            for idx, i in enumerate(range(1, 8))
        ])
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:00,500"},
            {"index": 2, "start": "00:00:00,500", "end": "00:00:01,000"},
            {"index": 3, "start": "00:00:01,000", "end": "00:00:01,500"},
            {"index": 4, "start": "00:00:01,500", "end": "00:00:02,000"},
            {"index": 5, "start": "00:00:02,000", "end": "00:00:02,500"},
            {"index": 6, "start": "00:00:02,500", "end": "00:00:03,000"},
            {"index": 7, "start": "00:00:03,000", "end": "00:00:03,500"},
            {"index": 8, "start": "00:00:03,500", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=i, segment_id=i, text=f"C{i}", start_seconds=(i - 1) * 0.5, end_seconds=i * 0.5, slot_duration=0.5, generated_duration=0.5, applied_speed=1.0, final_duration=2.0, status="ok")
            for i in range(1, 9)
        ]
        with pytest.raises(RuntimeError, match="TTS_TIMING_RECONCILE_TOTAL_TOO_LARGE"):
            TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans, output_dir=tmp_path)

        fail_file = tmp_path / "tts_timeline_reconciliation_failed.json"
        assert fail_file.exists()
        data = json.loads(fail_file.read_text(encoding="utf-8"))
        assert data["failed"] is True
        assert data["failure_code"] == "TTS_TIMING_RECONCILE_TOTAL_TOO_LARGE"
        assert data["candidate_total_shift_seconds"] > TTS_MAX_TOTAL_AUTO_SHIFT_SECONDS

    def test_long_timeline_allows_small_proportional_total_shift(self):
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:01:40,000"},
            {"index": 2, "start": "00:01:40,000", "end": "00:03:20,000"},
            {"index": 3, "start": "00:03:20,000", "end": "00:05:00,000"},
            {"index": 4, "start": "00:05:00,000", "end": "00:06:40,000"},
        ])
        plans = [
            TtsCuePlan(index=i, segment_id=i, text=f"C{i}", start_seconds=(i - 1) * 100.0, end_seconds=i * 100.0, slot_duration=100.0, generated_duration=100.0, applied_speed=1.0, final_duration=103.9, status="ok")
            for i in range(1, 5)
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["total_shift_seconds"] > TTS_MAX_TOTAL_AUTO_SHIFT_SECONDS
        assert report["total_shift_seconds"] < report["max_total_auto_shift_seconds"]
        assert report["max_total_auto_shift_seconds"] == pytest.approx(20.8)

    def test_long_timeline_allows_small_proportional_pair_shift(self):
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:06:40,000"},
            {"index": 2, "start": "00:06:40,000", "end": "00:13:20,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=400.0, slot_duration=400.0, generated_duration=400.0, applied_speed=1.0, final_duration=402.5, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=400.0, end_seconds=800.0, slot_duration=400.0, generated_duration=400.0, applied_speed=1.0, final_duration=400.0, status="ok"),
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["total_shift_seconds"] == pytest.approx(2.55, abs=0.001)
        assert report["max_pair_auto_shift_seconds"] == pytest.approx(10.0)

    def test_reconcile_does_not_insert_gap_for_abutting_cues(self):
        """Cues abutting exactly: no overlap → no shift."""
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000"},
            {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=2.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=2.0, end_seconds=4.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["applied"] is False
        assert report["adjustments"] == []
        cue1_start = srt_timestamp_to_seconds(payload.srt[0].start)
        cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
        assert cue1_start == pytest.approx(0.0)
        assert cue2_start == pytest.approx(2.0)

    def test_reconcile_preserves_existing_small_natural_gap(self):
        """Cues with a small natural gap (0.1s): no overlap → no shift."""
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000"},
            {"index": 2, "start": "00:00:02,100", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=2.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=2.1, end_seconds=4.0, slot_duration=1.9, generated_duration=1.9, applied_speed=1.0, final_duration=1.9, status="ok"),
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["applied"] is False
        assert report["adjustments"] == []
        cue2_start = srt_timestamp_to_seconds(payload.srt[1].start)
        assert cue2_start == pytest.approx(2.1)

    def test_reconcile_still_shifts_when_overlap_real(self):
        """Real overlap (voice overflow) → 0.25s breathing room shift applied."""
        payload = self._make_payload([
            {"index": 1, "start": "00:00:00,000", "end": "00:00:02,000"},
            {"index": 2, "start": "00:00:02,000", "end": "00:00:04,000"},
        ])
        plans = [
            TtsCuePlan(index=1, segment_id=1, text="C1", start_seconds=0.0, end_seconds=2.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=3.296, status="ok"),
            TtsCuePlan(index=2, segment_id=2, text="C2", start_seconds=2.0, end_seconds=4.0, slot_duration=2.0, generated_duration=2.0, applied_speed=1.0, final_duration=2.0, status="ok"),
        ]
        report = TtsVoiceoverService.reconcile_payload_tts_timeline(payload, plans)
        assert report["applied"] is True
        assert len(report["adjustments"]) == 1
        adj = report["adjustments"][0]
        assert adj["cue_index"] == 2
        # previous_end = max(2.0, 0+3.296) = 3.296; shift = 3.296 + 0.25 - 2.0 = 1.546
        assert adj["shift_seconds"] == pytest.approx(1.346, abs=0.001)


class TestMixVoiceoverDuration:
    """Verify mix_voiceover uses duration=longest when voiceover > video."""

    def test_mix_voiceover_uses_longest_duration_when_voiceover_longer(self, tmp_path):
        from app.services.tts_tools import TtsVoiceoverService
        from app.schemas.render import RenderOptions

        video_p = tmp_path / "video.mp4"
        voiceover_p = tmp_path / "voiceover.wav"
        out_p = tmp_path / "out.mp4"
        video_p.write_text("")
        voiceover_p.write_text("")

        cmd_args: list[str] = []

        def mock_probe_media_duration(p: object) -> float:
            return 10.0

        def mock_probe_audio_duration(p: object) -> float:
            return 12.0

        def mock_video_has_audio(p: object) -> bool:
            return True

        def mock_run(cmd: list[str]) -> None:
            cmd_args.extend(cmd)

        with (
            patch("app.services.tts_tools.probe_media_duration", mock_probe_media_duration),
            patch("app.services.tts_tools.probe_audio_duration", mock_probe_audio_duration),
            patch("app.services.tts_tools.video_has_audio", mock_video_has_audio),
            patch("app.services.tts_tools._run", mock_run),
        ):
            TtsVoiceoverService().mix_voiceover(
                video_p, voiceover_p, out_p,
                RenderOptions(original_audio_mode="lower_fixed"),
            )

        cmd_str = " ".join(cmd_args)
        assert "duration=longest" in cmd_str, f"Expected duration=longest, got:\n{cmd_str}"
        assert "duration=first" not in cmd_str, (
            f"Should not contain duration=first, got:\n{cmd_str}"
        )
        assert "tpad=stop_mode=clone:stop_duration=2.000" in cmd_str, (
            f"Expected tpad=...2.000, got:\n{cmd_str}"
        )
