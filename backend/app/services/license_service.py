from __future__ import annotations

import base64
import hashlib
import json
import platform
import re
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import settings


LICENSE_PUBLIC_KEY_B64 = "Nyj3yQapaKHlkZrdoFDmyuSrAWto6DTaR4TWazyYkZI"
LICENSE_PREFIX = "MRTRIS-V1-"
DEFAULT_FEATURES = {
    "render": True,
    "youtube_download": True,
    "tts": True,
    "voice_clone": True,
    "blur": True,
}


class LicenseError(RuntimeError):
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
        }


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


class LicenseService:
    def __init__(self, license_path: Path | None = None):
        self.license_path = license_path or (settings.logs_dir.parent / "data" / "license.json")
        self.public_key = Ed25519PublicKey.from_public_bytes(_b64url_decode(LICENSE_PUBLIC_KEY_B64))

    def status(self) -> LicenseCheck:
        hardware_id = get_hardware_id()
        if not settings.license_enforcement:
            return LicenseCheck(True, "disabled", "License enforcement đang tắt trong cấu hình dev.", hardware_id, False, plan="dev", features=DEFAULT_FEATURES)
        record = self._load_record()
        if not record:
            return LicenseCheck(False, "missing", "Chưa kích hoạt license.", hardware_id, True, features={key: False for key in DEFAULT_FEATURES})
        try:
            payload = self.verify_license_key(str(record.get("license_key") or ""), hardware_id)
            self._update_last_seen(record)
            return self._check_from_payload(payload, hardware_id, record)
        except LicenseError as exc:
            return LicenseCheck(False, "invalid", str(exc), hardware_id, True, license_key_hint=record.get("license_key_hint"), features={key: False for key in DEFAULT_FEATURES})

    def activate(self, license_key: str) -> LicenseCheck:
        hardware_id = get_hardware_id()
        payload = self.verify_license_key(license_key, hardware_id)
        record = {
            "license_key": license_key.strip(),
            "license_key_hint": license_key_hint(license_key.strip()),
            "activated_at": _iso(_now_utc()),
            "last_seen_at": _iso(_now_utc()),
        }
        self.license_path.parent.mkdir(parents=True, exist_ok=True)
        self.license_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._check_from_payload(payload, hardware_id, record)

    def clear(self) -> None:
        self.license_path.unlink(missing_ok=True)

    def require_feature(self, feature: str) -> None:
        check = self.status()
        if not settings.license_enforcement:
            return
        if not check.licensed:
            raise LicenseError(check.message)
        if not (check.features or {}).get(feature, False):
            raise LicenseError(f"License không cho phép tính năng: {feature}")

    def verify_license_key(self, license_key: str, expected_hwid: str | None = None) -> dict[str, Any]:
        cleaned = license_key.strip()
        if not cleaned.startswith(LICENSE_PREFIX):
            raise LicenseError("License key không đúng định dạng.")
        body = cleaned[len(LICENSE_PREFIX):]
        try:
            payload_b64, signature_b64 = body.split(".", 1)
        except ValueError as exc:
            raise LicenseError("License key thiếu chữ ký.") from exc
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(signature_b64)
        try:
            self.public_key.verify(signature, payload_bytes)
        except InvalidSignature as exc:
            raise LicenseError("Chữ ký license không hợp lệ.") from exc
        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(payload.get("version") or 0) != 1:
            raise LicenseError("Version license không được hỗ trợ.")
        hwid = _normalize_hwid(str(payload.get("hwid") or ""))
        if expected_hwid and hwid != _normalize_hwid(expected_hwid):
            raise LicenseError("License không khớp Hardware ID của máy này.")
        plan = str(payload.get("plan") or "").lower()
        if plan not in {"trial", "monthly", "lifetime"}:
            raise LicenseError("Plan license không hợp lệ.")
        expires_at = _parse_dt(payload.get("expires_at"))
        if plan != "lifetime" and expires_at is None:
            raise LicenseError("License có thời hạn nhưng thiếu expires_at.")
        if expires_at and _now_utc() > expires_at:
            raise LicenseError("License đã hết hạn.")
        return payload

    def _check_from_payload(self, payload: dict[str, Any], hardware_id: str, record: dict[str, Any]) -> LicenseCheck:
        features = {**DEFAULT_FEATURES, **(payload.get("features") or {})}
        return LicenseCheck(
            True,
            "active",
            "License hợp lệ.",
            hardware_id,
            settings.license_enforcement,
            plan=str(payload.get("plan") or ""),
            expires_at=payload.get("expires_at"),
            customer_name=payload.get("customer_name"),
            customer_email=payload.get("customer_email"),
            license_id=payload.get("license_id"),
            features=features,
            license_key_hint=record.get("license_key_hint"),
        )

    def _load_record(self) -> dict[str, Any] | None:
        if not self.license_path.exists():
            return None
        return json.loads(self.license_path.read_text(encoding="utf-8"))

    def _update_last_seen(self, record: dict[str, Any]) -> None:
        now = _now_utc()
        last_seen = _parse_dt(record.get("last_seen_at"))
        if last_seen and now < last_seen:
            raise LicenseError("Phát hiện thời gian hệ thống không hợp lệ.")
        record["last_seen_at"] = _iso(now)
        self.license_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def encode_license_payload(payload: dict[str, Any], private_key_bytes: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = Ed25519PrivateKey.from_private_bytes(private_key_bytes).sign(payload_bytes)
    return f"{LICENSE_PREFIX}{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"
