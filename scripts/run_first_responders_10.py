from __future__ import annotations

import json
import argparse
import time
from pathlib import Path

from scripts.live_benchmark import ROOT, acquire_lock, run_case


SOURCES = [
    ("9ogoX9vy-Y0", "Caught Lying After Hit & Run", 2440),
    ("jpgKlQ2lX2U", "I Called the Cops! You Can't Arrest Me!", 2676),
    ("wLceRDZ7OKA", "She Said I Can Go PeePee", 2619),
    ("ktIKz5hIcC4", "Drugs, Cash and Warrants", 2663),
    ("NIAQIkAGCA8", "Cops Meet General Panties", 1733),
    ("Lmr22YXlUsk", "Home Invasion Suspect Fights Deputies", 1992),
    ("A3FPWfsZpU4", "Fraudster Got Caught", 1291),
    ("ggvVyV6Sx9k", "Deadly Shooting", 2102),
    ("kOP2zVJcKwQ", "Rollover Crash", 1618),
    ("aDnX0O34ulo", "K9 Units in Action", 1512),
    ("Bk1V8nP6Tco", "Outstanding Warrants", 1804),
    ("EtGM75G2lPY", "Teenager Home Invasion", 1756),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", help="Only run selected video IDs")
    parser.add_argument("--target-duration", default="Tự động")
    parser.add_argument("--repair-text", action="store_true")
    args = parser.parse_args()
    base_url = "http://127.0.0.1:8007"
    timeout_seconds = 900
    report_path = ROOT / "temp" / "benchmark" / "first_responders_10_dry_run.json"
    sources = [
        {
            "id": video_id,
            "title": title,
            "category": "first_responders_channel",
            "media_url": f"https://www.youtube.com/watch?v={video_id}",
                "expected_minutes": expected_seconds / 60,
                "target_duration": args.target_duration,
                "user_instruction": (
                    "ĐÂY LÀ VÒNG REPAIR: rewrite_script.full_text phải bằng chính xác phép ghép "
                    "srt[].text theo index, giữ nguyên từng ký tự và dấu câu; không viết lại, không tóm tắt, "
                    "không bỏ câu. Trước khi trả JSON hãy tự ghép SRT, so sánh với full_text và sửa cho bằng nhau. "
                    "Mọi video_segments item bắt buộc có đầy đủ segment_id, order, source_id, source_start, "
                    "source_end, subtitle_start, subtitle_end và scene_description; không được thiếu field."
                    if args.repair_text else ""
                ),
        }
        for video_id, title, expected_seconds in SOURCES
        if not args.ids or video_id in args.ids
    ]
    if not sources:
        raise SystemExit("No matching video IDs")

    acquire_lock()
    results = []
    started = time.monotonic()
    try:
        for index, source in enumerate(sources, start=1):
            print(f"[{index}/{len(sources)}] {source['id']} {source['title']}", flush=True)
            case_started = time.monotonic()
            try:
                result = run_case(base_url, source, timeout_seconds)
            except Exception as exc:
                result = {
                    "id": source["id"],
                    "category": source["category"],
                    "status": "runner_error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            result["runner_elapsed_seconds"] = round(time.monotonic() - case_started, 3)
            results.append(result)
            print(json.dumps({"id": result.get("id"), "status": result.get("status"), "error": result.get("error")}, ensure_ascii=True), flush=True)
    finally:
        from scripts.live_benchmark import LOCK_PATH

        LOCK_PATH.unlink(missing_ok=True)

    report = {
        "channel": "https://www.youtube.com/@FIRST_RESPONDERS",
        "mode": "gemini_dry_run",
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(result.get("status") == "done" for result in results)
    print(json.dumps({"report": str(report_path), "passed": passed, "total": len(results)}, ensure_ascii=True))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
