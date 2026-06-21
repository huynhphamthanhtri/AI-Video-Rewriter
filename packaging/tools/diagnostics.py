from __future__ import annotations

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


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
