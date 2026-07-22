from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from scripts.live_benchmark import score_payload


ROOT = Path(__file__).resolve().parents[1]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def qualify(auto_results: list[dict], prompted_results: list[dict], manifest: dict) -> dict:
    sources = {source["id"]: source for source in manifest["sources"]}
    latest_auto = {result["id"]: result for result in auto_results}
    auto_rows: list[dict] = []
    for source_id, source in sources.items():
        result = latest_auto.get(source_id)
        if result is None:
            auto_rows.append({"id": source_id, "passed": False, "reason": "missing_result"})
            continue
        status = result.get("status")
        if source.get("expected_outcome") == "reject_duration":
            passed = status == "expected_rejection"
            auto_rows.append({"id": source_id, "status": status, "passed": passed, "reason": "duration_guard"})
            continue
        payload = result.get("gemini_json") or {}
        quality = score_payload(payload, source.get("expected_keywords")) if payload else {}
        elapsed = float(result.get("elapsed_seconds") or 0)
        sla_p90_seconds = max(12.0, 7.0 + 0.90 * float(source.get("expected_minutes") or 0)) * 60.0
        passed = (
            status == "done"
            and quality.get("deterministic_score", 0) >= manifest["quality_thresholds"]["total_score"]
            and quality.get("source_fidelity", 0) >= manifest["quality_thresholds"]["source_fidelity"]
            and quality.get("alignment_ratio", 0) * 35 >= manifest["quality_thresholds"]["scene_voice_alignment"]
            and elapsed <= sla_p90_seconds
        )
        auto_rows.append({
            "id": source_id,
            "status": status,
            "passed": passed,
            "elapsed_seconds": elapsed,
            "sla_p90_seconds": round(sla_p90_seconds, 3),
            "quality": quality,
        })

    latest_prompted = {result["id"]: result for result in prompted_results}
    prompted_rows: list[dict] = []
    for source in manifest["sources"]:
        if not source.get("style_pair"):
            continue
        result = latest_prompted.get(source["id"])
        payload = (result or {}).get("gemini_json") or {}
        quality = score_payload(payload, source.get("expected_keywords"), source.get("expected_style_keywords")) if payload else {}
        passed = (
            (result or {}).get("status") == "done"
            and quality.get("deterministic_score", 0) >= manifest["quality_thresholds"]["total_score"]
            and quality.get("source_fidelity", 0) >= manifest["quality_thresholds"]["source_fidelity"]
            and quality.get("style_adherence", 0) >= manifest["quality_thresholds"]["style_adherence_when_prompted"]
        )
        prompted_rows.append({"id": source["id"], "passed": passed, "quality": quality})

    renderable = [row for row in auto_rows if row.get("reason") != "duration_guard"]
    elapsed_values = [row["elapsed_seconds"] for row in renderable if row.get("status") == "done"]
    auto_passed = sum(bool(row.get("passed")) for row in auto_rows)
    prompted_passed = sum(bool(row.get("passed")) for row in prompted_rows)
    return {
        "schema_version": 1,
        "passed": auto_passed == len(auto_rows) and prompted_passed == len(prompted_rows),
        "summary": {
            "auto_passed": auto_passed,
            "auto_total": len(auto_rows),
            "renderable_pass_rate": round(sum(bool(row.get("passed")) for row in renderable) / max(1, len(renderable)), 4),
            "prompted_style_passed": prompted_passed,
            "prompted_style_total": len(prompted_rows),
            "median_seconds": round(statistics.median(elapsed_values), 3) if elapsed_values else 0,
            "p90_seconds": round(_percentile(elapsed_values, 0.90), 3),
        },
        "auto_results": auto_rows,
        "prompted_style_results": prompted_rows,
    }


def _load_results(paths: list[Path]) -> list[dict]:
    results: list[dict] = []
    for path in paths:
        results.extend(json.loads(path.read_text(encoding="utf-8")).get("results") or [])
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the authoritative benchmark qualification report.")
    parser.add_argument("--auto-files", nargs="+", type=Path, required=True)
    parser.add_argument("--prompted-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "benchmark" / "qualification.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "benchmark" / "manifest.json").read_text(encoding="utf-8"))
    report = qualify(_load_results(args.auto_files), _load_results([args.prompted_file]), manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "passed": report["passed"], **report["summary"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
