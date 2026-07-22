from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


def parse_silences(log_text: str | None, media_duration: float) -> list[dict]:
    silences: list[dict] = []
    pending_start: float | None = None
    for line in (log_text or "").splitlines():
        start_match = SILENCE_START.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
        end_match = SILENCE_END.search(line)
        if end_match:
            end = float(end_match.group(1))
            duration = float(end_match.group(2))
            start = pending_start if pending_start is not None else max(0.0, end - duration)
            silences.append({"start": round(start, 3), "end": round(end, 3), "duration": round(duration, 3)})
            pending_start = None
    if pending_start is not None and media_duration > pending_start:
        silences.append({
            "start": round(pending_start, 3),
            "end": round(media_duration, 3),
            "duration": round(media_duration - pending_start, 3),
        })
    return silences


def inspect_video(path: Path, *, max_silence: float, max_trailing_silence: float) -> dict:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    metadata = json.loads(probe.stdout)
    duration = float((metadata.get("format") or {}).get("duration") or 0)
    stream_types = {stream.get("codec_type") for stream in metadata.get("streams") or []}
    silence = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=0.5", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    silences = parse_silences(silence.stderr, duration)
    trailing = next((item["duration"] for item in reversed(silences) if abs(item["end"] - duration) <= 0.25), 0.0)
    longest = max((item["duration"] for item in silences), default=0.0)
    checks = {
        "has_video": "video" in stream_types,
        "has_audio": "audio" in stream_types,
        "duration_positive": duration > 0,
        "internal_silence_ok": all(
            item["duration"] <= max_silence or abs(item["end"] - duration) <= 0.25 for item in silences
        ),
        "trailing_silence_ok": trailing <= max_trailing_silence,
    }
    return {
        "path": str(path.resolve()),
        "passed": all(checks.values()),
        "checks": checks,
        "duration_seconds": round(duration, 3),
        "longest_silence_seconds": round(longest, 3),
        "trailing_silence_seconds": round(trailing, 3),
        "silences": silences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic publish-quality gate for a rendered voiceover video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-silence", type=float, default=2.5)
    parser.add_argument("--max-trailing-silence", type=float, default=1.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect_video(args.video, max_silence=args.max_silence, max_trailing_silence=args.max_trailing_silence)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
