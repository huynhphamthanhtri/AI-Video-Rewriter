from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app.services.license_service as license_module
from app.core.config import settings
from app.services.license_service import LicenseError, LicenseService, encode_license_payload, _b64url_encode


@pytest.fixture
def test_private_key(monkeypatch) -> bytes:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setattr(license_module, "LICENSE_PUBLIC_KEY_B64", _b64url_encode(public_key))
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def make_key(private_key: bytes, hwid: str, plan: str = "monthly", expires_delta: timedelta | None = timedelta(days=30)) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "version": 1,
        "license_id": "LIC-TEST",
        "customer_name": "Tester",
        "customer_email": "test@example.com",
        "hwid": hwid,
        "plan": plan,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": None if expires_delta is None else (now + expires_delta).isoformat().replace("+00:00", "Z"),
        "features": {"render": True, "youtube_download": True, "tts": True, "voice_clone": True, "blur": True},
    }
    return encode_license_payload(payload, private_key)


def test_license_service_accepts_valid_monthly_key(tmp_path, monkeypatch, test_private_key):
    monkeypatch.setattr(settings, "license_enforcement", True)
    monkeypatch.setattr(license_module, "get_hardware_id", lambda: "8F2A-19CD-77B1-42E9")
    service = LicenseService(tmp_path / "license.json")
    status = service.activate(make_key(test_private_key, "8F2A-19CD-77B1-42E9"))
    assert status.licensed is True
    assert status.plan == "monthly"
    assert status.customer_name == "Tester"


def test_license_service_rejects_wrong_hwid(tmp_path, monkeypatch, test_private_key):
    monkeypatch.setattr(settings, "license_enforcement", True)
    service = LicenseService(tmp_path / "license.json")
    with pytest.raises(LicenseError, match="Hardware ID"):
        service.verify_license_key(make_key(test_private_key, "8F2A-19CD-77B1-42E9"), "0000-0000-0000-0000")


def test_license_service_rejects_expired_key(tmp_path, monkeypatch, test_private_key):
    monkeypatch.setattr(settings, "license_enforcement", True)
    service = LicenseService(tmp_path / "license.json")
    with pytest.raises(LicenseError, match="hết hạn"):
        service.verify_license_key(make_key(test_private_key, "8F2A-19CD-77B1-42E9", expires_delta=timedelta(days=-1)), "8F2A-19CD-77B1-42E9")


def test_license_service_rejects_tampered_key(tmp_path, monkeypatch, test_private_key):
    monkeypatch.setattr(settings, "license_enforcement", True)
    service = LicenseService(tmp_path / "license.json")
    key = make_key(test_private_key, "8F2A-19CD-77B1-42E9")
    prefix, signature = key.rsplit(".", 1)
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = f"{prefix}.{tampered_signature}"
    with pytest.raises(LicenseError, match="Chữ ký"):
        service.verify_license_key(tampered, "8F2A-19CD-77B1-42E9")
