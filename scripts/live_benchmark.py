from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "temp" / "benchmark" / "live_benchmark.lock"


def acquire_lock(path: Path = LOCK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            owner_pid = int(path.read_text(encoding="ascii").strip())
            os.kill(owner_pid, 0)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            return acquire_lock(path)
        raise RuntimeError(f"Another live benchmark is already running (PID {owner_pid}).")
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(str(os.getpid()))


def _request_json(url: str, *, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _searchable_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def score_payload(
    payload: dict,
    expected_keywords: list[str] | None = None,
    expected_style_keywords: list[str] | None = None,
) -> dict:
    srt = payload.get("srt") or []
    segments = payload.get("video_segments") or []
    indexes = {item.get("index") for item in srt if isinstance(item, dict)}
    valid_ranges = sum(
        1
        for item in segments
        if isinstance(item, dict)
        and item.get("subtitle_start") in indexes
        and item.get("subtitle_end") in indexes
        and item.get("subtitle_start") <= item.get("subtitle_end")
        and item.get("source_start") < item.get("source_end")
    )
    alignment_ratio = valid_ranges / len(segments) if segments else 0.0
    structural = 25 if srt and segments and payload.get("rewrite_script", {}).get("full_text") else 0
    alignment = round(35 * alignment_ratio)
    density = 10 if len(srt) >= 5 and len(segments) >= 5 else round(2 * min(len(srt), len(segments)))
    metadata = payload.get("metadata") or {}
    creative = 10 if metadata.get("video_title") and metadata.get("rewrite_style") and metadata.get("tone") else 0
    fidelity_text = _searchable_text(json.dumps(payload, ensure_ascii=False))
    fidelity_hits = [keyword for keyword in (expected_keywords or []) if _searchable_text(keyword) in fidelity_text]
    fidelity = 20 if not expected_keywords or fidelity_hits else 0
    style_text = _searchable_text(" ".join(str(metadata.get(key) or "") for key in ("rewrite_style", "tone")))
    style_hits = [keyword for keyword in (expected_style_keywords or []) if _searchable_text(keyword) in style_text]
    style_adherence = 10 if not expected_style_keywords or style_hits else 0
    return {
        "deterministic_score": structural + alignment + density + creative + fidelity,
        "source_fidelity": fidelity,
        "fidelity_hits": fidelity_hits,
        "style_adherence": style_adherence,
        "style_hits": style_hits,
        "srt_count": len(srt),
        "video_segment_count": len(segments),
        "alignment_ratio": round(alignment_ratio, 3),
    }


def run_case(base_url: str, source: dict, timeout_seconds: int, *, prompted: bool = False) -> dict:
    instruction = source.get("user_instruction") or (source.get("prompted_instruction") if prompted else None)
    request_payload = {
        "form_data": {
            "youtube_url": source["media_url"],
            "source_mode": "single",
            "rewrite_style": "Tự chọn",
            "target_language": "Tiếng Việt",
            "target_duration": source.get("target_duration", "Tự động"),
            "user_instruction": instruction or "Tự chọn phong cách phù hợp; ưu tiên mạch kể hấp dẫn, cảnh khớp lời, liền mạch và ít khoảng lặng.",
        },
        "render_options": {},
        "subtitle_mode": "none",
        "headless": True,
        "gemini_thinking_mode": "standard",
        "gemini_analysis_mode": "fast",
        "gemini_dry_run": True,
    }
    started = time.monotonic()
    submitted = None
    last_submit_error: RuntimeError | None = None
    for attempt in range(1, 4):
        try:
            submitted = _request_json(f"{base_url}/api/gemini/auto-submit", payload=request_payload, timeout=60)
            break
        except RuntimeError as exc:
            last_submit_error = exc
            detail = str(exc)
            if source.get("expected_outcome") == "reject_duration" and "video_duration_exceeds_gemini_limit" in detail:
                return {
                    "id": source["id"],
                    "category": source["category"],
                    "status": "expected_rejection",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "quality": {"duration_guard": "passed"},
                    "error": None,
                }
            if "video_duration_unknown" not in detail or attempt == 3:
                raise
            time.sleep(3 * attempt)
    if submitted is None:
        raise last_submit_error or RuntimeError("Live benchmark submit failed.")
    task_id = submitted["task_id"]
    deadline = started + timeout_seconds
    while time.monotonic() < deadline:
        status = _request_json(f"{base_url}/api/gemini/status/{task_id}", timeout=30)
        if status.get("status") in {"done", "error"}:
            break
        time.sleep(3)
    else:
        status = {"status": "timeout", "error": f"Exceeded {timeout_seconds}s"}
    result = status.get("result") or {}
    gemini_json = result.get("gemini_json") or {}
    return {
        "id": source["id"],
        "category": source["category"],
        "task_id": task_id,
        "status": status.get("status"),
        "error": status.get("error"),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "telemetry": status.get("telemetry") or {},
        "quality": score_payload(
            gemini_json,
            source.get("expected_keywords"),
            source.get("expected_style_keywords") if prompted else None,
        ) if gemini_json else {},
        "gemini_json": gemini_json,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable live Gemini benchmark cases.")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8007")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--prompted", action="store_true", help="Use each style-pair source's prompted_instruction.")
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "benchmark" / "live_results.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "benchmark" / "manifest.json").read_text(encoding="utf-8"))
    by_id = {source["id"]: source for source in manifest["sources"]}
    missing = [source_id for source_id in args.ids if source_id not in by_id]
    if missing:
        raise SystemExit(f"Unknown benchmark ids: {', '.join(missing)}")
    acquire_lock()
    try:
        results = []
        for source_id in args.ids:
            try:
                results.append(run_case(args.base_url.rstrip("/"), by_id[source_id], args.timeout, prompted=args.prompted))
            except (OSError, RuntimeError, ValueError) as exc:
                results.append({"id": source_id, "status": "error", "error": str(exc)})
        report = {"created_at": time.time(), "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "statuses": {r["id"]: r["status"] for r in results}}, ensure_ascii=False))
        accepted_statuses = {"done", "expected_rejection"}
        return 0 if all(result.get("status") in accepted_statuses for result in results) else 1
    finally:
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
