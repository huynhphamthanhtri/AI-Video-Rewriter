from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def collect_render_plans(search_roots: list[Path], *, minimum_seconds: float = 1.0) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*render_plan*.json"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            timing = payload.get("diagnostics", {}).get("timing", {})
            total = timing.get("total_seconds")
            if not isinstance(total, (int, float)):
                continue
            if float(total) < minimum_seconds:
                continue
            plans.append({
                "path": str(resolved),
                "total_seconds": float(total),
                "steps": timing.get("steps", []),
                "video_encoder": payload.get("video_encoder", {}),
                "segment_count": len(payload.get("video_segments", [])),
                "srt_count": len(payload.get("srt", [])),
            })
    return plans


def build_report(plans: list[dict[str, Any]]) -> dict[str, Any]:
    totals = sorted(item["total_seconds"] for item in plans)
    step_totals: dict[str, float] = {}
    for plan in plans:
        for step in plan.get("steps", []):
            name = step.get("name")
            duration = step.get("duration_seconds")
            if isinstance(name, str) and isinstance(duration, (int, float)):
                step_totals[name] = step_totals.get(name, 0.0) + float(duration)
    slowest = sorted(step_totals.items(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(plans),
        "render_seconds": {
            "minimum": min(totals) if totals else None,
            "median": statistics.median(totals) if totals else None,
            "maximum": max(totals) if totals else None,
        },
        "aggregate_slowest_steps": [
            {"name": name, "duration_seconds": round(duration, 3)} for name, duration in slowest
        ],
        "samples": plans,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-root", action="append", type=Path)
    parser.add_argument("--output", type=Path, default=root / "temp" / "benchmark" / "baseline_report.json")
    args = parser.parse_args()
    search_roots = args.search_root or [root / "temp", root / "outputs"]
    report = build_report(collect_render_plans(search_roots))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "sample_count": report["sample_count"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
