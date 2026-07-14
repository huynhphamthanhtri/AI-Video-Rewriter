from __future__ import annotations

import hashlib
import json
import platform
import re
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


DEFAULT_FEATURES = {
    "render": True,
    "youtube_download": True,
    "tts": True,
    "voice_clone": True,
    "blur": True,
}


class LicenseError(RuntimeError):
    pass


class RemoteLicenseUnavailable(LicenseError):
    pass


@dataclass(frozen=True)
class LicenseCheck:
    licensed: bool
    status: str
    message: str
    hardware_id: str
    enforcement: bool
    plan: str | None = None
    expires_at: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    license_id: str | None = None
    features: dict[str, bool] | None = None
    license_key_hint: str | None = None
    cache_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "licensed": self.licensed,
            "status": self.status,
            "message": self.message,
            "hardware_id": self.hardware_id,
            "enforcement": self.enforcement,
            "plan": self.plan,
            "expires_at": self.expires_at,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "license_id": self.license_id,
            "features": self.features or DEFAULT_FEATURES,
            "license_key_hint": self.license_key_hint,
            "cache_status": self.cache_status,
        }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None


def _machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def _normalize_hwid(value: str) -> str:
    raw = re.sub(r"[^A-Fa-f0-9]", "", value).upper()
    if len(raw) >= 16:
        raw = raw[:16]
    return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))


def get_hardware_id() -> str:
    parts = [
        _machine_guid(),
        platform.node(),
        socket.gethostname(),
        str(uuid.getnode()),
    ]
    digest = hashlib.sha256("|".join(part.strip().lower() for part in parts if part).encode("utf-8")).hexdigest().upper()
    return _normalize_hwid(digest)


def license_key_hint(license_key: str) -> str:
    if len(license_key) <= 24:
        return license_key
    return f"{license_key[:16]}...{license_key[-8:]}"


def _reason_message(reason: str) -> str:
    messages = {
        "MISSING_LICENSE_KEY": "Thiếu license key.",
        "MISSING_HWID": "Thiếu Hardware ID.",
        "KEY_NOT_FOUND": "License key không tồn tại.",
        "STATUS_BLOCKED": "License đã bị khóa hoặc không còn hoạt động.",
        "EXPIRED": "License đã hết hạn.",
        "DEVICE_LIMIT_REACHED": "License đã đạt giới hạn thiết bị.",
        "SHEET_READ_FAILED": "Không đọc được dữ liệu license từ server.",
        "SHEET_UPDATE_FAILED": "Không cập nhật được thiết bị trên server license.",
        "SHEET_CONFIG_MISSING": "Server license chưa được cấu hình.",
        "SHEET_AUTH_FAILED": "Server license xác thực Google Sheet thất bại.",
        "DEVICE_NOT_BOUND": "Thiết bị này chưa được liên kết với license.",
        "UNKNOWN_ERROR": "Server license trả lỗi không xác định.",
    }
    return messages.get(reason, reason or "License không hợp lệ.")


class LicenseService:
    def __init__(self, license_path: Path | None = None):
        self.license_path = license_path or (settings.logs_dir.parent / "data" / "license.json")

    def status(self) -> LicenseCheck:
        hardware_id = get_hardware_id()
        if not settings.sv_key_api_url:
            return LicenseCheck(True, "disabled", "SV_KEY_API_URL chưa cấu hình; license enforcement đang tắt trong dev mode.", hardware_id, False, plan="dev", features=DEFAULT_FEATURES)

        record = self._load_record()
        if not record:
            return LicenseCheck(False, "missing", "Chưa kích hoạt license.", hardware_id, True, features={key: False for key in DEFAULT_FEATURES})
        if str(record.get("hardware_id") or "") != hardware_id:
            return LicenseCheck(False, "invalid", "License cache không khớp Hardware ID của máy này.", hardware_id, True, license_key_hint=record.get("license_key_hint"), features={key: False for key in DEFAULT_FEATURES})
        expiry = _parse_dt(record.get("expires_at"))
        if expiry and _now_utc() > expiry:
            self.clear()
            return LicenseCheck(False, "invalid", "License đã hết hạn.", hardware_id, True, license_key_hint=record.get("license_key_hint"), features={key: False for key in DEFAULT_FEATURES})

        if self._cache_age(record) <= timedelta(hours=settings.sv_key_cache_ttl_hours):
            self._touch_record(record)
            return self._check_from_record(record, hardware_id, "fresh")

        license_key = str(record.get("license_key") or "")
        try:
            data = self._remote_validate(license_key, hardware_id)
            new_record = self._record_from_remote(license_key, hardware_id, data)
            self._save_record(new_record)
            return self._check_from_record(new_record, hardware_id, "fresh")
        except RemoteLicenseUnavailable as exc:
            if self._cache_age(record) <= timedelta(days=settings.sv_key_grace_period_days):
                record["last_seen_at"] = _iso(_now_utc())
                self._save_record(record)
                return self._check_from_record(record, hardware_id, "offline", f"Không kết nối được server license; đang dùng cache offline tối đa {settings.sv_key_grace_period_days} ngày. Chi tiết: {exc}")
            return LicenseCheck(False, "unreachable", f"Không kết nối được server license và cache đã quá hạn {settings.sv_key_grace_period_days} ngày.", hardware_id, True, license_key_hint=record.get("license_key_hint"), features={key: False for key in DEFAULT_FEATURES}, cache_status="stale")
        except LicenseError as exc:
            self.clear()
            return LicenseCheck(False, "invalid", str(exc), hardware_id, True, license_key_hint=record.get("license_key_hint"), features={key: False for key in DEFAULT_FEATURES})

    def activate(self, license_key: str) -> LicenseCheck:
        if not settings.sv_key_api_url:
            raise LicenseError("SV_KEY_API_URL chưa được cấu hình.")
        cleaned = license_key.strip()
        if not cleaned:
            raise LicenseError("Thiếu license key.")
        hardware_id = get_hardware_id()
        data = self._remote_validate(cleaned, hardware_id)
        record = self._record_from_remote(cleaned, hardware_id, data)
        self._save_record(record)
        return self._check_from_record(record, hardware_id, "fresh")

    def unbind(self, license_key: str | None = None) -> None:
        if not settings.sv_key_api_url:
            raise LicenseError("SV_KEY_API_URL chưa được cấu hình.")
        record = self._load_record() or {}
        cleaned = (license_key or str(record.get("license_key") or "")).strip()
        if not cleaned:
            raise LicenseError("Không tìm thấy license key để unbind.")
        hardware_id = get_hardware_id()
        self._remote_unbind(cleaned, hardware_id)
        self.clear()

    def clear(self) -> None:
        self.license_path.unlink(missing_ok=True)

    def require_feature(self, feature: str) -> None:
        if not settings.sv_key_api_url:
            return
        check = self.status()
        if not check.licensed:
            raise LicenseError(check.message)
        if not (check.features or {}).get(feature, False):
            raise LicenseError(f"License không cho phép tính năng: {feature}")

    def _remote_validate(self, license_key: str, hardware_id: str) -> dict[str, Any]:
        data = self._post_remote("/api/license/validate", {"licenseKey": license_key, "hwid": hardware_id})
        if not data.get("valid"):
            raise LicenseError(_reason_message(str(data.get("reason") or "")))
        license_info = data.get("license")
        if not isinstance(license_info, dict):
            raise LicenseError("Server license trả dữ liệu không hợp lệ.")
        return license_info

    def _remote_unbind(self, license_key: str, hardware_id: str) -> None:
        data = self._post_remote("/api/license/unbind", {"licenseKey": license_key, "hwid": hardware_id})
        if not data.get("success"):
            raise LicenseError(_reason_message(str(data.get("reason") or "")))

    def _post_remote(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{settings.sv_key_api_url.rstrip('/')}{path}"
        try:
            response = httpx.post(url, json=payload, timeout=10.0)
        except httpx.HTTPError as exc:
            raise RemoteLicenseUnavailable(str(exc)) from exc
        if response.status_code != 200:
            raise RemoteLicenseUnavailable(f"HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RemoteLicenseUnavailable("Response không phải JSON") from exc
        if not isinstance(data, dict):
            raise RemoteLicenseUnavailable("Response JSON không hợp lệ")
        return data

    def _record_from_remote(self, license_key: str, hardware_id: str, license_info: dict[str, Any]) -> dict[str, Any]:
        now = _iso(_now_utc())
        return {
            "license_key": license_key,
            "license_key_hint": license_key_hint(license_key),
            "hardware_id": hardware_id,
            "remote_status": str(license_info.get("status") or ""),
            "expires_at": str(license_info.get("expiresAt") or ""),
            "bound_devices": int(license_info.get("boundDevices") or 0),
            "max_devices": int(license_info.get("maxDevices") or 1),
            "remote_validated_at": license_info.get("validatedAt"),
            "validated_at": now,
            "last_seen_at": now,
        }

    def _check_from_record(self, record: dict[str, Any], hardware_id: str, cache_status: str, message: str | None = None) -> LicenseCheck:
        status = str(record.get("remote_status") or "ACTIVE").lower()
        return LicenseCheck(
            True,
            "active",
            message or "License hợp lệ.",
            hardware_id,
            True,
            plan=status,
            expires_at=record.get("expires_at"),
            features=DEFAULT_FEATURES,
            license_key_hint=record.get("license_key_hint"),
            cache_status=cache_status,
        )

    def _load_record(self) -> dict[str, Any] | None:
        if not self.license_path.exists():
            return None
        return json.loads(self.license_path.read_text(encoding="utf-8"))

    def _save_record(self, record: dict[str, Any]) -> None:
        self.license_path.parent.mkdir(parents=True, exist_ok=True)
        self.license_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _touch_record(self, record: dict[str, Any]) -> None:
        record["last_seen_at"] = _iso(_now_utc())
        self._save_record(record)

    def _cache_age(self, record: dict[str, Any]) -> timedelta:
        validated_at = _parse_dt(record.get("validated_at")) or datetime.fromtimestamp(0, timezone.utc)
        return _now_utc() - validated_at
