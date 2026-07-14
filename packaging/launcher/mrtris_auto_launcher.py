from __future__ import annotations

import os
import signal
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
BACKEND_STOP_TIMEOUT = 10


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


def write_startup_diagnostics(root: Path, appdata: Path, port: int, env: dict[str, str], desktop_mode: str, pw_browsers: Path | None = None, tts_model_ok: bool = False) -> None:
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
    if pw_browsers is not None:
        checks["playwright_browsers"] = pw_browsers
    lines = [f"app={APP_NAME}", f"port={port}", f"desktop_mode={desktop_mode}", f"tts_model_ok={tts_model_ok}"]
    for name, check_path in checks.items():
        lines.append(f"{name}={check_path} | exists={Path(check_path).exists()}")
    for key in ["MRTRIS_AUTO_APPDATA", "MRTRIS_AUTO_OUTPUTS_DIR", "MRTRIS_AUTO_TEMP_DIR", "MRTRIS_AUTO_LOGS_DIR", "FFMPEG_BINARY", "FFPROBE_BINARY", "IMAGEIO_FFMPEG_EXE", "YTDLP_BINARY", "YTDLP_JS_RUNTIMES", "YTDLP_REMOTE_COMPONENTS", "PLAYWRIGHT_BROWSERS_PATH", "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "PATH"]:
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


def _capture_port_usage() -> str:
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [l for l in result.stdout.splitlines() if "LISTENING" in l and ":800" in l]
        return "\n".join(lines) if lines else "(no processes on ports 8000-8004)"
    except Exception:
        return "(could not capture port usage)"


def choose_port() -> int:
    for port in PORT_CANDIDATES:
        if port_available(port):
            return port
    usage = _capture_port_usage()
    raise RuntimeError(f"Không tìm được port local trống trong dải 8000-8004.\nPort usage:\n{usage}")


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


def build_env(root: Path, port: int, dev_mode: bool = False) -> dict[str, str]:
    appdata = local_appdata()
    outputs = Path.home() / "Videos" / "AutoReview"
    node_dir = root / "runtime" / "node"
    ffmpeg_dir = root / "runtime" / "ffmpeg"
    bundled_ffmpeg = ffmpeg_dir / "ffmpeg.exe"
    bundled_ffprobe = ffmpeg_dir / "ffprobe.exe"
    pkg = "1" if not dev_mode else "0"
    dev_appdata = root / "dev_data"
    env = os.environ.copy()

    # Detect bundled Playwright browsers
    pw_browsers = root / "runtime" / "playwright-browsers"
    resolved_pw_browsers = str(pw_browsers) if pw_browsers.exists() else ""

    # Bundled HuggingFace cache (read-only from installer)
    bundled_hf = root / "runtime" / "python" / "Lib" / "site-packages" / "huggingface_cache"
    # Writable cache under LOCALAPPDATA (user-writable)
    writable_hf = appdata / "huggingface"
    writable_hub = writable_hf / "hub"
    # First-run copy: bundle → writable appdata
    if not writable_hub.exists() and bundled_hf.exists():
        try:
            import shutil
            writable_hub.mkdir(parents=True, exist_ok=True)
            for item in bundled_hf.iterdir():
                dest = writable_hub / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
        except Exception:
            pass
    writable_hub.mkdir(parents=True, exist_ok=True)
    resolved_hf_home = str(writable_hf)

    env.update(
        {
            "MRTRIS_AUTO_PACKAGED": pkg,
            "MRTRIS_AUTO_APPDATA": str(appdata) if not dev_mode else str(dev_appdata),
            "MRTRIS_AUTO_OUTPUTS_DIR": str(outputs) if not dev_mode else str(root / "outputs"),
            "MRTRIS_AUTO_TEMP_DIR": str(appdata / "temp") if not dev_mode else str(root / "temp"),
            "MRTRIS_AUTO_LOGS_DIR": str(appdata / "logs") if not dev_mode else str(root / "logs"),
            "SQLITE_URL": f"sqlite:///{(appdata / 'data' / 'app.db').as_posix()}" if not dev_mode else f"sqlite:///{(root / 'backend' / 'app.db').as_posix()}",
            "FRONTEND_DIST_DIR": str(root / "frontend" / "dist"),
            "FFMPEG_BINARY": str(bundled_ffmpeg) if bundled_ffmpeg.exists() else "ffmpeg",
            "FFPROBE_BINARY": str(bundled_ffprobe) if bundled_ffprobe.exists() else "ffprobe",
            "IMAGEIO_FFMPEG_EXE": str(bundled_ffmpeg) if bundled_ffmpeg.exists() else "ffmpeg",
            "YTDLP_BINARY": str(root / "runtime" / "yt-dlp" / "yt-dlp.exe"),
            "YTDLP_JS_RUNTIMES": "node",
            "YTDLP_REMOTE_COMPONENTS": "ejs:github",
            "YTDLP_PREFER_H264": "true",
            "VIDEO_ENCODER": "auto",
            "SV_KEY_API_URL": "https://sv-key-mrtris.vercel.app",
            "SV_KEY_CACHE_TTL_HOURS": "24",
            "SV_KEY_GRACE_PERIOD_DAYS": "2",
            "MRTRIS_AUTO_PORT": str(port),
            "PLAYWRIGHT_BROWSERS_PATH": resolved_pw_browsers,
            "HF_HOME": resolved_hf_home,
            "HF_HUB_CACHE": str(writable_hub),
            "TRANSFORMERS_CACHE": str(writable_hub),
        }
    )
    path_prefixes = []
    if bundled_ffmpeg.exists():
        path_prefixes.append(str(ffmpeg_dir))
    if (node_dir / "node.exe").exists():
        path_prefixes.append(str(node_dir))
    if path_prefixes:
        env["PATH"] = f"{os.pathsep.join(path_prefixes)}{os.pathsep}{env.get('PATH', '')}"
    for path in [appdata / "data", appdata / "cookies", appdata / "temp", appdata / "logs", outputs, writable_hub]:
        path.mkdir(parents=True, exist_ok=True)
    return env


def _kill_process_tree(pid: int, log_path: Path) -> None:
    """Kill a process and all its children on Windows using taskkill."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, timeout=10,
        )
        log_line(log_path, f"Killed process tree for PID {pid}.")
    except subprocess.TimeoutExpired:
        log_line(log_path, f"taskkill timed out for PID {pid}, using fallback.")
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            pass
    except Exception as exc:
        log_line(log_path, f"taskkill failed for PID {pid}: {exc}")
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            pass


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


def stop_backend(process: subprocess.Popen, log_path: Path) -> None:
    if process.poll() is not None:
        log_line(log_path, "Backend already exited.")
        return
    try:
        log_line(log_path, "Stopping backend...")
        process.terminate()
        try:
            process.wait(timeout=BACKEND_STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            log_line(log_path, "Backend did not exit in time, using process-tree kill.")
            _kill_process_tree(process.pid, log_path)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        log_line(log_path, "Backend stopped.")
    except Exception as exc:
        log_line(log_path, f"Error stopping backend: {exc}")
        _kill_process_tree(process.pid, log_path)


class DesktopApi:
    def choose_output_folder(self) -> str | None:
        try:
            import webview
            result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
            return result[0] if result else None
        except Exception:
            return None


def open_desktop_window(url: str, process: subprocess.Popen, log_path: Path) -> bool:
    """Try to open a PyWebView desktop window. Returns True on success."""
    try:
        import webview  # type: ignore[import-untyped]
        api = DesktopApi()
        window = webview.create_window(
            APP_NAME,
            url,
            width=1400,
            height=900,
            min_size=(1100, 720),
            js_api=api,
        )
        webview.start()
        stop_backend(process, log_path)
        return True
    except ImportError:
        log_line(log_path, "pywebview not available, falling back to browser.")
        return False
    except Exception as exc:
        log_line(log_path, f"pywebview error: {exc}, falling back to browser.")
        return False


def main() -> int:
    dev_mode = "--dev" in sys.argv
    root = app_root()
    appdata = local_appdata()
    log_path = appdata / "logs" / "launcher.log"
    desktop_mode = "browser"
    pw_browsers: Path | None = None
    tts_model_ok = False
    port = PORT_CANDIDATES[0]
    env: dict[str, str] = {}
    process: subprocess.Popen | None = None
    try:
        port = choose_port()
        missing = [] if dev_mode else validate_runtime(root)
        env = build_env(root, port, dev_mode=dev_mode)

        # Pre-startup checks
        pw_browsers = root / "runtime" / "playwright-browsers"
        if pw_browsers.exists():
            log_line(log_path, f"Playwright browsers found at {pw_browsers}")
        else:
            log_line(log_path, "No bundled Playwright browsers. Chromium will download on first Gemini launch.")

        bundled_hf = root / "runtime" / "python" / "Lib" / "site-packages" / "huggingface_cache"
        writable_hub = appdata / "huggingface" / "hub"
        if writable_hub.exists() and any(writable_hub.iterdir()):
            log_line(log_path, f"TTS model cache ready at {writable_hub}")
        elif bundled_hf.exists():
            log_line(log_path, f"Bundled TTS cache found at {bundled_hf}, will copy on first use.")
        else:
            log_line(log_path, "No TTS model cache found. Models will download on first TTS request.")
        log_line(log_path, "HF_HOME=" + env.get("HF_HOME", "not_set"))

        # Write environment diagnostics early so tests can inspect them
        try:
            write_startup_diagnostics(root, appdata, port, env, desktop_mode, pw_browsers, tts_model_ok)
        except Exception:
            pass

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

        # Pre-flight import check to catch startup errors early
        log_line(log_path, "Pre-flight: verifying app module can be imported...")
        import_check = subprocess.run(
            [str(python), "-c",
             f"import sys; sys.path.insert(0, r'{backend_dir}'); "
             f"from app.main import app; print('IMPORT_OK')"],
            capture_output=True, text=True, timeout=30,
            env=env,
        )
        if import_check.returncode != 0:
            stderr_tail = import_check.stderr[:1000]
            log_line(log_path, f"Pre-flight import FAILED (rc={import_check.returncode}): {stderr_tail}")
            return 1
        log_line(log_path, "Pre-flight import OK")

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

        if open_desktop_window(url, process, log_path):
            desktop_mode = "desktop"
            log_line(log_path, "Desktop window closed. Exiting.")
            return 0

        desktop_mode = "browser_fallback"
        log_line(log_path, f"Opening browser fallback: {url}")
        webbrowser.open(url)
        log_line(log_path, "Backend is running in browser fallback mode. Close this process to stop.")
        while process.poll() is None:
            time.sleep(5)
        log_line(log_path, f"Backend exited with code {process.returncode}.")
        return process.returncode
    except Exception as exc:
        log_line(log_path, f"Launcher error: {exc}")
        crash_path = appdata / "logs" / "crash.log"
        try:
            import traceback
            crash_path.write_text(
                f"MrTris_AUTO crash report\nport={port}\nroot={root}\nappdata={appdata}\n\n{traceback.format_exc()}\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        return 1
    finally:
        if process is not None and process.poll() is None:
            stop_backend(process, log_path)
        write_startup_diagnostics(root, appdata, port, env, desktop_mode, pw_browsers, tts_model_ok)


if __name__ == "__main__":
    raise SystemExit(main())
