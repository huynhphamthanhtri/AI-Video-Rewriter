from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.live_benchmark import ROOT, _request_json
from scripts.video_quality_gate import inspect_video


def run_batch(base_url: str, sources: list[dict], timeout_seconds: int) -> dict:
    urls = [source["media_url"] for source in sources]
    payload = {
        "form_data": {
            "youtube_url": urls[0],
            "youtube_urls": urls,
            "source_mode": "multi",
            "rewrite_style": "Tự chọn",
            "target_language": "Tiếng Việt",
            "target_duration": "Tự động",
            "user_instruction": "Tự chọn phong cách phù hợp cho từng nguồn; giữ đúng nội dung, cảnh khớp lời, liền mạch và ít khoảng lặng.",
        },
        "render_options": {
            "tts_mode": "voiceover",
            "tts_engine": "edge_tts",
            "tts_voice_mode": "preset",
            "tts_voice_id": "auto",
            "tts_emotion": "natural",
            "vertical_mode": "none",
            "render_quality": "balanced",
            "output_resolution": "auto",
            "video_encoder": "auto",
            "title_mode": "auto",
            "video_speed": 1.0,
        },
        "subtitle_mode": "none",
        "headless": True,
        "gemini_thinking_mode": "standard",
        "gemini_analysis_mode": "fast",
    }
    started = time.monotonic()
    submitted = _request_json(f"{base_url}/api/gemini/batch-auto-submit", payload=payload, timeout=120)
    batch_id = submitted["batch_id"]
    deadline = started + timeout_seconds
    while time.monotonic() < deadline:
        state = _request_json(f"{base_url}/api/gemini/batch/{batch_id}", timeout=30)
        if state.get("status") in {"done", "error", "cancelled"}:
            break
        time.sleep(5)
    else:
        state = {"batch_id": batch_id, "status": "timeout", "items": []}

    items: list[dict] = []
    for item in state.get("items") or []:
        result = item.get("result") or {}
        video_path = Path(result["final_video_path"]) if result.get("final_video_path") else None
        quality = inspect_video(video_path, max_silence=2.5, max_trailing_silence=1.5) if video_path and video_path.exists() else None
        items.append({
            "index": item.get("index"),
            "source_url": item.get("source_url"),
            "status": item.get("status"),
            "error": item.get("error"),
            "final_video_path": str(video_path) if video_path else None,
            "quality": quality,
        })
    passed = (
        state.get("status") == "done"
        and len(items) == len(sources)
        and all(item["status"] == "done" and (item["quality"] or {}).get("passed") for item in items)
    )
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "status": state.get("status"),
        "passed": passed,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live list-of-links to rendered-videos E2E gate.")
    parser.add_argument("--ids", nargs="+", default=["real_degraded", "visual_coffee_run"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8007")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "benchmark" / "live_batch_e2e.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "benchmark" / "manifest.json").read_text(encoding="utf-8"))
    by_id = {source["id"]: source for source in manifest["sources"]}
    if len(args.ids) < 2:
        raise SystemExit("Live batch E2E requires at least two source ids.")
    missing = [source_id for source_id in args.ids if source_id not in by_id]
    if missing:
        raise SystemExit(f"Unknown benchmark ids: {', '.join(missing)}")
    report = run_batch(args.base_url.rstrip("/"), [by_id[source_id] for source_id in args.ids], args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "batch_id": report["batch_id"], "passed": report["passed"]}, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
