from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "benchmark" / "manifest.json"
VALID_STATUSES = {"locked", "candidate", "discovery"}


def validate_manifest(path: Path) -> tuple[dict, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        return data, ["sources must be a non-empty list"]
    ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"{prefix}.id is required")
        elif source_id in ids:
            errors.append(f"{prefix}.id duplicates {source_id}")
        else:
            ids.add(source_id)
        if source.get("status") not in VALID_STATUSES:
            errors.append(f"{prefix}.status is invalid")
        if not isinstance(source.get("expected_minutes"), (int, float)) or source["expected_minutes"] <= 0:
            errors.append(f"{prefix}.expected_minutes must be positive")
        if source.get("status") == "locked" and (not source.get("media_url") or not source.get("license")):
            errors.append(f"{prefix} locked source requires media_url and license")
    if len(sources) != 18:
        errors.append(f"benchmark must contain 18 sources, found {len(sources)}")
    if sum(1 for source in sources if source.get("style_pair")) != 3:
        errors.append("benchmark must contain exactly 3 style-pair sources")
    return data, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-locked", action="store_true")
    args = parser.parse_args()
    data, errors = validate_manifest(args.manifest)
    if args.require_locked:
        unlocked = [source["id"] for source in data.get("sources", []) if source.get("status") != "locked"]
        if unlocked:
            errors.append(f"unlocked benchmark sources: {', '.join(unlocked)}")
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "source_count": len(data.get("sources", [])),
                      "locked_count": sum(source.get("status") == "locked" for source in data.get("sources", [])),
                      "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
