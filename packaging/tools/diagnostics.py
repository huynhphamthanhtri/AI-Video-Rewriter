from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
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


def read_tail(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return f"Missing: {path}\n"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:]) + "\n"


def run_check(command: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return f"$ {' '.join(command)}\nexit={result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}\n"
    except Exception as exc:
        return f"$ {' '.join(command)}\nERROR: {exc}\n"


def fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def discover_backend() -> str | None:
    env_port = os.environ.get("MRTRIS_AUTO_PORT")
    ports = [int(env_port)] if env_port and env_port.isdigit() else []
    ports.extend([8000, 8001, 8002, 8003, 8004])
    for port in dict.fromkeys(ports):
        url = f"http://127.0.0.1:{port}"
        if fetch_json(f"{url}/api/runtime/health"):
            return url
    return None


def playwright_check(runtime: Path) -> str:
    pw_dir = runtime / "playwright-browsers"
    if not pw_dir.exists():
        return "MISSING: no playwright-browsers directory"
    chromium_dirs = [d for d in pw_dir.iterdir() if d.is_dir() and "chromium" in d.name]
    if not chromium_dirs:
        return "MISSING: no chromium browser found in playwright-browsers"
    details = "; ".join(f"{d.name}" for d in sorted(chromium_dirs))
    return f"OK: {len(chromium_dirs)} chromium version(s): {details}"


def tts_check(runtime: Path) -> str:
    python_exe = runtime / "python" / "python.exe"
    if not python_exe.exists():
        return "MISSING: python.exe not found"
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import edge_tts; print('import_ok')"],
            capture_output=True, text=True, timeout=30,
        )
        if "import_ok" in result.stdout:
            return "OK: edge_tts import successful"
        return f"FAIL: {result.stderr[:200]}"
    except Exception as exc:
        return f"ERROR: {exc}"


def quick_diagnostics() -> int:
    root = app_root()
    data = appdata()
    runtime = root / "runtime"
    issues = []

    print("=== MrTris_AUTO Quick Diagnostics ===\n")

    # Runtime files
    required = [
        ("Python", runtime / "python" / "python.exe"),
        ("Node", runtime / "node" / "node.exe"),
        ("FFmpeg", runtime / "ffmpeg" / "ffmpeg.exe"),
        ("FFprobe", runtime / "ffmpeg" / "ffprobe.exe"),
        ("yt-dlp", runtime / "yt-dlp" / "yt-dlp.exe"),
        ("Backend", root / "backend" / "app" / "main.py"),
        ("Frontend", root / "frontend" / "dist" / "index.html"),
    ]
    for name, path in required:
        status = "OK" if path.exists() else "MISSING"
        if status == "MISSING":
            issues.append(f"  [{status}] {name}: {path}")
        print(f"  [{status}] {name}")

    # Playwright browsers
    pw_status = playwright_check(runtime)
    if "MISSING" in pw_status:
        issues.append(f"  [{pw_status}] Playwright browsers")
    print(f"  [{pw_status}] Playwright browsers")

    # TTS
    tts_status = tts_check(runtime)
    if "MISSING" in tts_status or "FAIL" in tts_status:
        issues.append(f"  [{tts_status}] TTS (edge_tts)")
    print(f"  [{tts_status}] TTS (edge_tts)")

    # Backend
    backend_url = discover_backend()
    if backend_url:
        health = fetch_json(f"{backend_url}/api/runtime/health")
        node_ok = health.get("node_status", {}).get("available", False) if health else False
        ffmpeg_ok = health.get("ffmpeg_version_status", {}).get("available", False) if health else False
        tts_api = health.get("tts_status", {}).get("status", "unknown") if health else "unknown"
        print(f"  [OK] Backend running at {backend_url}")
        print(f"  [{'OK' if node_ok else 'FAIL'}] Node (backend check)")
        print(f"  [{'OK' if ffmpeg_ok else 'FAIL'}] FFmpeg (backend check)")
        print(f"  [{'OK' if tts_api == 'ready' else 'WARN'}] TTS (backend status: {tts_api})")
    else:
        issues.append("  Backend not running")
        print("  [STOPPED] Backend")

    print()
    if issues:
        print(f"Found {len(issues)} issue(s):")
        for issue in issues:
            print(f"  {issue}")
        return 1
    print("All checks passed.")
    return 0


def full_diagnostics() -> int:
    root = app_root()
    data = appdata()
    logs = data / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = logs / f"diagnostics_{stamp}.zip"
    runtime = root / "runtime"
    backend_url = discover_backend()

    files: dict[str, str] = {
        "system.txt": "\n".join(
            [
                f"app={APP_NAME}",
                f"root={root}",
                f"appdata={data}",
                f"python={sys.executable}",
                f"platform={platform.platform()}",
                f"machine={platform.machine()}",
                f"processor={platform.processor()}",
                f"backend_url={backend_url or 'not_running'}",
            ]
        )
        + "\n",
        "ffmpeg_check.txt": run_check([str(runtime / "ffmpeg" / "ffmpeg.exe"), "-version"]),
        "ffprobe_check.txt": run_check([str(runtime / "ffmpeg" / "ffprobe.exe"), "-version"]),
        "node_check.txt": run_check([str(runtime / "node" / "node.exe"), "--version"]),
        "yt_dlp_module_check.txt": run_check([str(runtime / "python" / "python.exe"), "-m", "yt_dlp", "--version"]),
        "yt_dlp_module_runtime_check.txt": run_check([str(runtime / "python" / "python.exe"), "-m", "yt_dlp", "--js-runtimes", "node", "--remote-components", "ejs:github", "--version"]),
        "yt_dlp_exe_check.txt": run_check([str(runtime / "yt-dlp" / "yt-dlp.exe"), "--version"]),
        "yt_dlp_exe_runtime_check.txt": run_check([str(runtime / "yt-dlp" / "yt-dlp.exe"), "--js-runtimes", "node", "--remote-components", "ejs:github", "--version"]),
        "playwright_check.txt": playwright_check(runtime),
        "tts_check.txt": tts_check(runtime),
        "launcher.log": read_tail(logs / "launcher.log"),
        "backend.log": read_tail(logs / "backend.log"),
        "backend.err": read_tail(logs / "backend.err"),
        "startup_diagnostics.txt": read_tail(logs / "startup_diagnostics.txt"),
        "download.log": read_tail(logs / "download.log"),
        "error.log": read_tail(logs / "error.log"),
        "ytdlp.log": read_tail(logs / "ytdlp.log"),
        "ytdlp_last_command.txt": read_tail(logs / "ytdlp_last_command.txt"),
        "ytdlp_preflight.log": read_tail(logs / "ytdlp_preflight.log"),
        "ytdlp_stdout.log": read_tail(logs / "ytdlp_stdout.log"),
        "ytdlp_stderr.log": read_tail(logs / "ytdlp_stderr.log"),
    }
    if backend_url:
        health = fetch_json(f"{backend_url}/api/runtime/health")
        preset_sync = fetch_json(f"{backend_url}/api/presets/sync-status")
        tts_status = fetch_json(f"{backend_url}/api/tts/status")
        files["runtime_health.json"] = json.dumps(health, ensure_ascii=False, indent=2)
        files["preset_sync.json"] = json.dumps(preset_sync, ensure_ascii=False, indent=2)
        files["tts_status.json"] = json.dumps(tts_status, ensure_ascii=False, indent=2)
    else:
        files["runtime_health.json"] = json.dumps({"status": "backend_not_running"}, indent=2)

    settings_path = data / "settings" / "render_preferences.json"
    if settings_path.exists():
        files["settings_snapshot.json"] = settings_path.read_text(encoding="utf-8", errors="replace")

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    print(out_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Diagnostics Tool")
    parser.add_argument("--quick", action="store_true", help="Quick check (console output, no zip)")
    args = parser.parse_args()

    if args.quick:
        return quick_diagnostics()
    return full_diagnostics()


if __name__ == "__main__":
    raise SystemExit(main())
