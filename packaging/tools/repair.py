from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


APP_NAME = "MrTris_AUTO"


def appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / APP_NAME


def outputs_dir() -> Path:
    return Path.home() / "Videos" / "AutoReview"


def discover_backend() -> str | None:
    for port in [8000, 8001, 8002, 8003, 8004]:
        url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{url}/api/runtime/health", timeout=3) as response:
                if response.status == 200:
                    return url
        except (urllib.error.URLError, TimeoutError):
            continue
    return None


def post(url: str) -> str:
    request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def recreate_folders() -> None:
    data = appdata()
    for path in [data / "data", data / "cookies", data / "settings", data / "voices", data / "logs", data / "temp", outputs_dir()]:
        path.mkdir(parents=True, exist_ok=True)
        print(f"OK folder: {path}")


def backup_database() -> None:
    db = appdata() / "data" / "app.db"
    if not db.exists():
        print(f"No database to backup: {db}")
        return
    backup = db.with_suffix(f".bak_{time.strftime('%Y%m%d_%H%M%S')}.db")
    shutil.copy2(db, backup)
    print(f"Database backup: {backup}")


def clear_temp() -> None:
    temp = appdata() / "temp"
    if not temp.exists():
        print(f"Temp does not exist: {temp}")
        return
    shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    print(f"Cleared temp: {temp}")


def reset_settings() -> None:
    settings_dir = appdata() / "settings"
    if not settings_dir.exists():
        print(f"Settings dir does not exist: {settings_dir}")
        return
    backup_dir = appdata() / "logs" / f"settings_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for path in settings_dir.glob("*.json"):
        shutil.move(str(path), str(backup_dir / path.name))
        moved += 1
    print(f"Moved {moved} settings files to {backup_dir}")


def sync_presets() -> None:
    backend = discover_backend()
    if not backend:
        print("Backend is not running; start MrTris_AUTO first to sync presets.")
        return
    print(post(f"{backend}/api/presets/sync"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair MrTris_AUTO local data without deleting final outputs.")
    parser.add_argument("--clear-temp", action="store_true")
    parser.add_argument("--reset-settings", action="store_true")
    parser.add_argument("--sync-presets", action="store_true")
    parser.add_argument("--backup-db", action="store_true")
    args = parser.parse_args()

    recreate_folders()
    if args.backup_db:
        backup_database()
    if args.clear_temp:
        clear_temp()
    if args.reset_settings:
        reset_settings()
    if args.sync_presets:
        sync_presets()
    if not any([args.backup_db, args.clear_temp, args.reset_settings, args.sync_presets]):
        print("Basic repair completed. Use --help for optional repair actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
