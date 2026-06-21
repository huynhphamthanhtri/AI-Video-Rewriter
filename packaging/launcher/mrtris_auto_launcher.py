from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path


APP_NAME = "MrTris_AUTO"
PORT_CANDIDATES = [8000, 8001, 8002, 8003, 8004]


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir, *script_dir.parents]:
        if (candidate / "backend").exists() and (candidate / "frontend").exists():
            return candidate
    return script_dir


def local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / APP_NAME


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} | {message}\n")


def write_startup_diagnostics(root: Path, appdata: Path, port: int, env: dict[str, str]) -> None:
    path = appdata / "logs" / "startup_diagnostics.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    checks = {
        "app_root": root,
        "backend_dir": root / "backend",
        "frontend_dist": root / "frontend" / "dist",
        "python": runtime_python(root),
        "node": root / "runtime" / "node" / "node.exe",
        "yt_dlp": root / "runtime" / "yt-dlp" / "yt-dlp.exe",
        "ffmpeg": root / "runtime" / "ffmpeg" / "ffmpeg.exe",
        "ffprobe": root / "runtime" / "ffmpeg" / "ffprobe.exe",
    }
    lines = [f"app={APP_NAME}", f"port={port}"]
    for name, check_path in checks.items():
        lines.append(f"{name}={check_path} | exists={Path(check_path).exists()}")
    for key in ["MRTRIS_AUTO_APPDATA", "MRTRIS_AUTO_OUTPUTS_DIR", "MRTRIS_AUTO_TEMP_DIR", "MRTRIS_AUTO_LOGS_DIR", "FFMPEG_BINARY", "FFPROBE_BINARY", "IMAGEIO_FFMPEG_EXE", "YTDLP_BINARY", "YTDLP_JS_RUNTIMES", "YTDLP_REMOTE_COMPONENTS", "PATH"]:
        lines.append(f"env.{key}={env.get(key, '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_runtime(root: Path) -> list[str]:
    required = [
        root / "backend" / "app" / "main.py",
        root / "frontend" / "dist" / "index.html",
        root / "runtime" / "python" / "python.exe",
        root / "runtime" / "node" / "node.exe",
        root / "runtime" / "yt-dlp" / "yt-dlp.exe",
        root / "runtime" / "ffmpeg" / "ffmpeg.exe",
        root / "runtime" / "ffmpeg" / "ffprobe.exe",
    ]
    return [str(path) for path in required if not path.exists()]


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def choose_port() -> int:
    for port in PORT_CANDIDATES:
        if port_available(port):
            return port
    raise RuntimeError("Không tìm được port local trống trong dải 8000-8004.")


def runtime_python(root: Path) -> Path:
    bundled = root / "runtime" / "python" / "python.exe"
    if bundled.exists():
        return bundled
    bundled_venv = root / "runtime" / "python" / "Scripts" / "python.exe"
    if bundled_venv.exists():
        return bundled_venv
    dev = root / ".venv312" / "Scripts" / "python.exe"
    if dev.exists():
        return dev
    return Path(sys.executable)


def build_env(root: Path, port: int) -> dict[str, str]:
    appdata = local_appdata()
    outputs = Path.home() / "Videos" / "AutoReview"
    node_dir = root / "runtime" / "node"
    ffmpeg_dir = root / "runtime" / "ffmpeg"
    env = os.environ.copy()
    env.update(
        {
            "MRTRIS_AUTO_PACKAGED": "1",
            "MRTRIS_AUTO_APPDATA": str(appdata),
            "MRTRIS_AUTO_OUTPUTS_DIR": str(outputs),
            "MRTRIS_AUTO_TEMP_DIR": str(appdata / "temp"),
            "MRTRIS_AUTO_LOGS_DIR": str(appdata / "logs"),
            "SQLITE_URL": f"sqlite:///{(appdata / 'data' / 'app.db').as_posix()}",
            "FRONTEND_DIST_DIR": str(root / "frontend" / "dist"),
            "FFMPEG_BINARY": str(root / "runtime" / "ffmpeg" / "ffmpeg.exe"),
            "FFPROBE_BINARY": str(root / "runtime" / "ffmpeg" / "ffprobe.exe"),
            "IMAGEIO_FFMPEG_EXE": str(root / "runtime" / "ffmpeg" / "ffmpeg.exe"),
            "YTDLP_BINARY": str(root / "runtime" / "yt-dlp" / "yt-dlp.exe"),
            "YTDLP_JS_RUNTIMES": "node",
            "YTDLP_REMOTE_COMPONENTS": "ejs:github",
            "YTDLP_PREFER_H264": "true",
            "VIDEO_ENCODER": "auto",
            "LICENSE_ENFORCEMENT": "true",
            "MRTRIS_AUTO_PORT": str(port),
        }
    )
    path_prefixes = []
    if (ffmpeg_dir / "ffmpeg.exe").exists():
        path_prefixes.append(str(ffmpeg_dir))
    if (node_dir / "node.exe").exists():
        path_prefixes.append(str(node_dir))
    if path_prefixes:
        env["PATH"] = f"{os.pathsep.join(path_prefixes)}{os.pathsep}{env.get('PATH', '')}"
    for path in [appdata / "data", appdata / "cookies", appdata / "temp", appdata / "logs", outputs]:
        path.mkdir(parents=True, exist_ok=True)
    return env


def wait_for_health(url: str, process: subprocess.Popen, log_path: Path) -> bool:
    deadline = time.time() + 45
    while time.time() < deadline:
        if process.poll() is not None:
            log_line(log_path, f"Backend exited early with code {process.returncode}.")
            return False
        try:
            with urllib.request.urlopen(f"{url}/api/runtime/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    return False


def main() -> int:
    root = app_root()
    appdata = local_appdata()
    log_path = appdata / "logs" / "launcher.log"
    try:
        port = choose_port()
        missing = validate_runtime(root)
        env = build_env(root, port)
        write_startup_diagnostics(root, appdata, port, env)
        if missing:
            for path in missing:
                log_line(log_path, f"Missing required runtime file: {path}")
            log_line(log_path, "Runtime is incomplete. Reinstall using the latest MrTris_AUTO installer.")
            return 1
        python = runtime_python(root)
        backend_dir = root / "backend"
        stdout_path = appdata / "logs" / "backend.log"
        stderr_path = appdata / "logs" / "backend.err"
        log_line(log_path, f"Starting {APP_NAME} backend on 127.0.0.1:{port} using {python}")
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            process = subprocess.Popen(
                [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=str(backend_dir),
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
        url = f"http://127.0.0.1:{port}"
        if not wait_for_health(url, process, log_path):
            log_line(log_path, "Backend health check failed. Open backend.err for details.")
            return 1
        log_line(log_path, f"Opening browser: {url}")
        webbrowser.open(url)
        log_line(log_path, "Backend is running. Close this process to stop the local server.")
        return process.wait()
    except Exception as exc:
        log_line(log_path, f"Launcher error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
