from __future__ import annotations

import json
from datetime import timedelta

import pytest

import app.services.license_service as license_module
from app.core.config import settings
from app.services.license_service import LicenseError, LicenseService, RemoteLicenseUnavailable, _iso, _now_utc


HWID = "8F2A-19CD-77B1-42E9"


@pytest.fixture(autouse=True)
def remote_license_mode(monkeypatch):
    monkeypatch.setattr(settings, "sv_key_api_url", "https://sv-key.vercel.app")
    monkeypatch.setattr(settings, "sv_key_cache_ttl_hours", 24)
    monkeypatch.setattr(settings, "sv_key_grace_period_days", 2)
    monkeypatch.setattr(license_module, "get_hardware_id", lambda: HWID)


def remote_info(key: str = "TESTADMIN1") -> dict:
    return {
        "key": key,
        "status": "ACTIVE",
        "expiresAt": "2099-12-31",
        "boundDevices": 1,
        "maxDevices": 1,
        "hwid": HWID,
        "validatedAt": 1780000000000,
    }


def write_cache(path, *, key: str = "TESTADMIN1", age: timedelta = timedelta(hours=1)):
    now = _now_utc()
    record = {
        "license_key": key,
        "license_key_hint": key,
        "hardware_id": HWID,
        "remote_status": "ACTIVE",
        "expires_at": "2099-12-31",
        "bound_devices": 1,
        "max_devices": 1,
        "remote_validated_at": 1780000000000,
        "validated_at": _iso(now - age),
        "last_seen_at": _iso(now - age),
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    return record


def test_activate_remote_license_success(tmp_path, monkeypatch):
    service = LicenseService(tmp_path / "license.json")
    monkeypatch.setattr(service, "_remote_validate", lambda key, hwid: remote_info(key))

    status = service.activate("TESTADMIN1")

    assert status.licensed is True
    assert status.status == "active"
    assert status.plan == "active"
    assert status.license_key_hint == "TESTADMIN1"
    assert (tmp_path / "license.json").exists()


def test_activate_remote_key_not_found(tmp_path, monkeypatch):
    service = LicenseService(tmp_path / "license.json")

    def fail(_key, _hwid):
        raise LicenseError("License key không tồn tại.")

    monkeypatch.setattr(service, "_remote_validate", fail)
    with pytest.raises(LicenseError, match="không tồn tại"):
        service.activate("BADKEY")


def test_activate_remote_device_limit_reached(tmp_path, monkeypatch):
    service = LicenseService(tmp_path / "license.json")

    def fail(_key, _hwid):
        raise LicenseError("License đã đạt giới hạn thiết bị.")

    monkeypatch.setattr(service, "_remote_validate", fail)
    with pytest.raises(LicenseError, match="giới hạn thiết bị"):
        service.activate("TESTADMIN1")


def test_status_uses_fresh_cache_without_remote_call(tmp_path, monkeypatch):
    path = tmp_path / "license.json"
    write_cache(path, age=timedelta(hours=1))
    service = LicenseService(path)

    def should_not_call(_key, _hwid):
        raise AssertionError("remote should not be called for fresh cache")

    monkeypatch.setattr(service, "_remote_validate", should_not_call)
    status = service.status()

    assert status.licensed is True
    assert status.cache_status == "fresh"


def test_status_revalidates_stale_cache(tmp_path, monkeypatch):
    path = tmp_path / "license.json"
    write_cache(path, age=timedelta(days=2))
    service = LicenseService(path)
    calls = []

    def validate(key, hwid):
        calls.append((key, hwid))
        return remote_info(key)

    monkeypatch.setattr(service, "_remote_validate", validate)
    status = service.status()

    assert status.licensed is True
    assert status.cache_status == "fresh"
    assert calls == [("TESTADMIN1", HWID)]


def test_status_allows_offline_cache_within_2_days(tmp_path, monkeypatch):
    path = tmp_path / "license.json"
    write_cache(path, age=timedelta(hours=30))
    service = LicenseService(path)

    def unavailable(_key, _hwid):
        raise RemoteLicenseUnavailable("timeout")

    monkeypatch.setattr(service, "_remote_validate", unavailable)
    status = service.status()

    assert status.licensed is True
    assert status.cache_status == "offline"


def test_status_rejects_offline_cache_after_2_days(tmp_path, monkeypatch):
    path = tmp_path / "license.json"
    write_cache(path, age=timedelta(days=3))
    service = LicenseService(path)

    def unavailable(_key, _hwid):
        raise RemoteLicenseUnavailable("timeout")

    monkeypatch.setattr(service, "_remote_validate", unavailable)
    status = service.status()

    assert status.licensed is False
    assert status.status == "unreachable"


def test_unbind_calls_remote_and_clears_cache(tmp_path, monkeypatch):
    path = tmp_path / "license.json"
    write_cache(path)
    service = LicenseService(path)
    calls = []

    def unbind(key, hwid):
        calls.append((key, hwid))

    monkeypatch.setattr(service, "_remote_unbind", unbind)
    service.unbind()

    assert calls == [("TESTADMIN1", HWID)]
    assert not path.exists()


def test_dev_mode_when_sv_key_url_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sv_key_api_url", "")
    service = LicenseService(tmp_path / "license.json")

    status = service.status()

    assert status.licensed is True
    assert status.status == "disabled"
