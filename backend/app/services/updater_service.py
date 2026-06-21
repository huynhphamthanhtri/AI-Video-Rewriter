from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import httpx

from app.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

# Mirrors scripts/update_tool.ps1. Keep in sync.
MANIFEST_URL = "https://raw.githubusercontent.com/huynhphamthanhtri/MrTris_AUTO_UPDATES/main/manifest.json"


class UpdaterError(Exception):
    pass


def _parse_semver(v: str) -> tuple[int, int, int, str | None]:
    parts = v.split("-", 1)
    major, minor, patch = (int(x) for x in parts[0].split("."))
    prerelease = parts[1] if len(parts) > 1 else None
    return (major, minor, patch, prerelease)


def _compare_versions_str(left: str, right: str) -> int:
    l_major, l_minor, l_patch, l_pre = _parse_semver(left)
    r_major, r_minor, r_patch, r_pre = _parse_semver(right)

    if (l_major, l_minor, l_patch) < (r_major, r_minor, r_patch):
        return -1
    if (l_major, l_minor, l_patch) > (r_major, r_minor, r_patch):
        return 1

    if l_pre == r_pre:
        return 0
    if l_pre is None and r_pre is not None:
        return 1
    if l_pre is not None and r_pre is None:
        return -1
    return -1 if l_pre < r_pre else 1


def get_local_version() -> dict:
    version_path = ROOT_DIR / "version.json"
    if not version_path.is_file():
        logger.warning("version.json not found at %s, using fallback", version_path)
        return {"version": "0.0.0", "channel": "unknown"}
    try:
        data = json.loads(version_path.read_text(encoding="utf-8-sig"))
        version = str(data.get("version", "0.0.0"))
        channel = str(data.get("channel", "unknown"))
        return {"version": version, "channel": channel}
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Failed to read version.json: %s", exc)
        return {"version": "0.0.0", "channel": "unknown"}


def _validate_manifest(data: dict) -> dict:
    required = {"version", "download_url"}
    missing = required - set(data.keys())
    if missing:
        raise UpdaterError(f"Thiếu trường bắt buộc trong manifest: {', '.join(sorted(missing))}")
    version = str(data["version"])
    download_url = str(data["download_url"])
    channel = str(data.get("channel", "stable"))
    notes = data.get("notes", [])
    if not isinstance(notes, list):
        notes = []
    return {
        "version": version,
        "download_url": download_url,
        "channel": channel,
        "notes": notes,
    }


def get_remote_manifest() -> dict:
    try:
        resp = httpx.get(MANIFEST_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise UpdaterError(f"Không thể truy cập máy chủ cập nhật (HTTP {exc.response.status_code}).") from exc
    except httpx.TimeoutException as exc:
        raise UpdaterError("Máy chủ cập nhật không phản hồi (timeout).") from exc
    except httpx.RequestError as exc:
        raise UpdaterError(f"Lỗi mạng khi kiểm tra cập nhật: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UpdaterError("Dữ liệu cập nhật không hợp lệ (lỗi JSON).") from exc
    if not isinstance(data, dict):
        raise UpdaterError("Dữ liệu cập nhật không đúng định dạng.")

    return _validate_manifest(data)


def compare_versions(local: dict, remote: dict) -> dict:
    local_version = local.get("version", "0.0.0")
    remote_version = remote.get("version", "0.0.0")
    local_channel = local.get("channel", "unknown")
    remote_channel = remote.get("channel", remote_channel := remote.get("channel", "stable"))

    cmp = _compare_versions_str(local_version, remote_version)
    update_available = cmp < 0

    notes = remote.get("notes", [])
    download_url = remote.get("download_url", "")

    if update_available:
        message = "Có bản cập nhật mới"
    else:
        message = "Bạn đang dùng bản mới nhất"

    return {
        "local_version": local_version,
        "remote_version": remote_version,
        "channel": remote_channel,
        "update_available": update_available,
        "notes": notes,
        "download_url": download_url,
        "message": message,
    }


def launch_updater(from_ui: bool = False, restart_after_update: bool = False) -> dict:
    updater_path = ROOT_DIR / "update_tool.bat"
    if not updater_path.is_file():
        raise UpdaterError("Không tìm thấy trình cập nhật (update_tool.bat).")

    cmd = [str(updater_path)]
    if from_ui:
        cmd.append("-FromUI")
    if restart_after_update:
        cmd.append("-RestartAfterUpdate")

    try:
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)

        subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            creationflags=creation_flags,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Launched updater: %s with flags from_ui=%s restart=%s", updater_path, from_ui, restart_after_update)
    except OSError as exc:
        raise UpdaterError(f"Không thể mở trình cập nhật: {exc}") from exc

    if from_ui and restart_after_update:
        msg = "Trình cập nhật đã mở. Ứng dụng sẽ tự đóng, cập nhật và khởi động lại."
    else:
        msg = "Trình cập nhật đã được mở. Vui lòng đóng MrTris_AUTO trong khi cập nhật."

    return {
        "started": True,
        "message": msg,
    }
