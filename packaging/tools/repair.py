from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


APP_NAME = "MrTris_AUTO"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir, *script_dir.parents]:
        if (candidate / "backend").exists() and (candidate / "frontend").exists():
            return candidate
    return script_dir


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


def repair_playwright_browsers(root: Path) -> None:
    """Re-install Playwright chromium into the runtime's bundled Python."""
    python_exe = root / "runtime" / "python" / "python.exe"
    if not python_exe.exists():
        print("Cannot repair Playwright: python.exe not found in runtime.")
        return
    print("Re-installing Playwright Chromium...")
    result = subprocess.run(
        [str(python_exe), "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"FAILED to install Chromium:\n{result.stderr[:500]}")
    else:
        print("OK: Playwright Chromium installed.")

    # Copy newly installed browsers into runtime/playwright-browsers
    ms_playwright = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ms-playwright"
    browsers_dst = root / "runtime" / "playwright-browsers"
    browsers_dst.mkdir(parents=True, exist_ok=True)
    if ms_playwright.exists():
        for d in ms_playwright.iterdir():
            if d.is_dir() and ("chromium" in d.name or "ffmpeg" in d.name or "winldd" in d.name):
                dst = browsers_dst / d.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(d, dst)
                print(f"  Copied {d.name}")
    print("Playwright browsers repair complete.")


def repair_tts(root: Path) -> None:
    """Re-install Edge TTS dependencies."""
    python_exe = root / "runtime" / "python" / "python.exe"
    if not python_exe.exists():
        print("Cannot repair TTS: python.exe not found in runtime.")
        return
    req_tts = root / "backend" / "requirements.txt"
    print("Re-installing TTS dependencies...")
    result = subprocess.run(
        [str(python_exe), "-m", "pip", "install", "-r", str(req_tts)],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"FAILED to install TTS deps:\n{result.stderr[:500]}")
    else:
        print("OK: TTS dependencies installed.")
    # Verify
    verify = subprocess.run(
        [str(python_exe), "-c", "import edge_tts; print('OK')"],
        capture_output=True, text=True, timeout=120,
    )
    if verify.returncode != 0:
        print(f"Edge TTS import failed: {verify.stderr[:300]}")
    else:
        print("OK: Edge TTS import successful.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair MrTris_AUTO local data without deleting final outputs.")
    parser.add_argument("--clear-temp", action="store_true", help="Clear temp data")
    parser.add_argument("--reset-settings", action="store_true", help="Reset settings to defaults")
    parser.add_argument("--sync-presets", action="store_true", help="Sync built-in presets")
    parser.add_argument("--backup-db", action="store_true", help="Backup database")
    parser.add_argument("--repair-playwright", action="store_true", help="Re-install Playwright Chromium browser")
    parser.add_argument("--repair-tts", action="store_true", help="Re-install Edge TTS dependencies")
    parser.add_argument("--all", action="store_true", help="Run all repair actions")
    args = parser.parse_args()

    root = app_root()
    recreate_folders()

    if args.all:
        args.backup_db = True
        args.clear_temp = True
        args.reset_settings = True
        args.sync_presets = True
        args.repair_playwright = True
        args.repair_tts = True

    if args.backup_db:
        backup_database()
    if args.clear_temp:
        clear_temp()
    if args.reset_settings:
        reset_settings()
    if args.sync_presets:
        sync_presets()
    if args.repair_playwright:
        repair_playwright_browsers(root)
    if args.repair_tts:
        repair_tts(root)
    if not any([args.backup_db, args.clear_temp, args.reset_settings, args.sync_presets, args.repair_playwright, args.repair_tts]):
        print("Basic repair completed. Use --help for optional repair actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
