from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.live_benchmark import ROOT, _request_json
from scripts.video_quality_gate import inspect_video


SOURCES = [
    ("ggvVyV6Sx9k", "Deadly Shooting", "5 phút"),
    ("EtGM75G2lPY", "Teenager Home Invasion", "3 phút"),
]


def main() -> int:
    base_url = "http://127.0.0.1:8007"
    report_path = ROOT / "temp" / "benchmark" / "first_responders_render_smoke.json"
    results = []

    for index, (video_id, title, target_duration) in enumerate(SOURCES, start=1):
        url = f"https://www.youtube.com/watch?v={video_id}"
        started = time.monotonic()
        print(f"[{index}/{len(SOURCES)}] {video_id} {title}", flush=True)
        payload = {
            "form_data": {
                "youtube_url": url,
                "source_mode": "single",
                "rewrite_style": "Tự chọn",
                "target_language": "Tiếng Việt",
                "target_duration": target_duration,
                "user_instruction": "Tự chọn phong cách phù hợp; giữ đúng nội dung, cảnh khớp lời, liền mạch và ít khoảng lặng.",
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
            "gemini_dry_run": False,
        }
        result = {"id": video_id, "title": title, "url": url}
        try:
            submitted = _request_json(f"{base_url}/api/gemini/auto-submit", payload=payload, timeout=120)
            task_id = submitted["task_id"]
            task_deadline = time.monotonic() + 1200
            task_state = {}
            while time.monotonic() < task_deadline:
                task_state = _request_json(f"{base_url}/api/gemini/status/{task_id}", timeout=30)
                if task_state.get("status") in {"done", "error", "cancelled"}:
                    break
                time.sleep(5)
            result["task_id"] = task_id
            result["task_status"] = task_state.get("status")
            if task_state.get("status") != "done":
                result["error"] = task_state.get("error") or "Gemini task did not finish"
                results.append(result)
                continue

            job_id = (task_state.get("result") or {}).get("job_id")
            result["job_id"] = job_id
            if not job_id:
                result["error"] = "Gemini completed without render job id"
                results.append(result)
                continue

            job_deadline = time.monotonic() + 1800
            job_state = {}
            while time.monotonic() < job_deadline:
                job_state = _request_json(f"{base_url}/api/render-jobs/{job_id}", timeout=30)
                if job_state.get("status") in {"done", "error", "cancelled"}:
                    break
                time.sleep(5)
            result["render_status"] = job_state.get("status")
            render_result = job_state.get("result") or {}
            result["final_video_path"] = render_result.get("final_video_path")
            video_path = Path(result["final_video_path"]) if result["final_video_path"] else None
            result["quality"] = inspect_video(video_path, max_silence=2.5, max_trailing_silence=1.5) if video_path and video_path.exists() else {}
            result["passed"] = job_state.get("status") == "done" and result["quality"].get("passed") is True
            if not result["passed"]:
                result["error"] = job_state.get("error") or "Quality gate failed"
        except Exception as exc:
            result["passed"] = False
            result["error"] = f"{type(exc).__name__}: {exc}"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(result)
        print(json.dumps({"id": video_id, "passed": result.get("passed"), "error": result.get("error")}, ensure_ascii=True), flush=True)

    report = {"mode": "render_smoke", "results": results}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(result.get("passed") is True for result in results)
    print(json.dumps({"report": str(report_path), "passed": passed, "total": len(results)}, ensure_ascii=True))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
