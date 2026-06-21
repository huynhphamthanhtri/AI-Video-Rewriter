from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.updater_service import (
    MANIFEST_URL,
    ROOT_DIR,
    UpdaterError,
    _compare_versions_str,
    _parse_semver,
    _validate_manifest,
    compare_versions,
    get_local_version,
    launch_updater,
    get_remote_manifest,
)


class TestParseSemver:
    def test_simple(self):
        assert _parse_semver("1.0.0") == (1, 0, 0, None)

    def test_with_prerelease(self):
        assert _parse_semver("1.0.1-rc1") == (1, 0, 1, "rc1")

    def test_multi_digit(self):
        assert _parse_semver("10.2.300") == (10, 2, 300, None)


class TestCompareVersionsStr:
    def test_equal(self):
        assert _compare_versions_str("1.0.0", "1.0.0") == 0

    def test_left_older(self):
        assert _compare_versions_str("1.0.0", "1.0.1") == -1

    def test_left_newer(self):
        assert _compare_versions_str("1.0.2", "1.0.1") == 1

    def test_release_greater_than_prerelease(self):
        assert _compare_versions_str("1.0.1", "1.0.1-rc1") == 1

    def test_prerelease_less_than_release(self):
        assert _compare_versions_str("1.0.1-rc1", "1.0.1") == -1

    def test_same_prerelease(self):
        assert _compare_versions_str("1.0.1-rc1", "1.0.1-rc1") == 0

    def test_different_prerelease(self):
        assert _compare_versions_str("1.0.1-rc1", "1.0.1-rc2") == -1

    def test_major_version_difference(self):
        assert _compare_versions_str("2.0.0", "1.9.9") == 1

    def test_minor_version_difference(self):
        assert _compare_versions_str("1.1.0", "1.0.9") == 1


class TestValidateManifest:
    def test_valid(self):
        data = {"version": "1.0.1", "download_url": "https://example.com/pkg.zip", "channel": "stable", "notes": ["Fix bug"]}
        result = _validate_manifest(data)
        assert result["version"] == "1.0.1"
        assert result["download_url"] == "https://example.com/pkg.zip"
        assert result["channel"] == "stable"
        assert result["notes"] == ["Fix bug"]

    def test_minimal_valid(self):
        data = {"version": "1.0.0", "download_url": "https://example.com/pkg.zip"}
        result = _validate_manifest(data)
        assert result["channel"] == "stable"
        assert result["notes"] == []

    def test_missing_version(self):
        with pytest.raises(UpdaterError, match="version"):
            _validate_manifest({"download_url": "x"})

    def test_missing_download_url(self):
        with pytest.raises(UpdaterError, match="download_url"):
            _validate_manifest({"version": "1.0.0"})

    def test_notes_not_list(self):
        data = {"version": "1.0.0", "download_url": "url", "notes": "just a string"}
        result = _validate_manifest(data)
        assert result["notes"] == []


class TestGetLocalVersion:
    def test_found(self, monkeypatch):
        version_path = ROOT_DIR / "version.json"
        if version_path.is_file():
            result = get_local_version()
            assert "version" in result
            assert "channel" in result
            assert result["version"] != "0.0.0"
            assert result["channel"] != "unknown"

    def test_missing_fallback(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "nope"
        fake_root.mkdir()
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        result = get_local_version()
        assert result == {"version": "0.0.0", "channel": "unknown"}

    def test_invalid_json_fallback(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "bad"
        fake_root.mkdir()
        (fake_root / "version.json").write_text("not json")
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        result = get_local_version()
        assert result == {"version": "0.0.0", "channel": "unknown"}

    def test_reads_with_bom(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "with_bom"
        fake_root.mkdir()
        bom = b"\xef\xbb\xbf"
        content = bom + b'{"version": "1.0.3", "channel": "stable"}'
        (fake_root / "version.json").write_bytes(content)
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        result = get_local_version()
        assert result == {"version": "1.0.3", "channel": "stable"}

    def test_reads_without_bom(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "no_bom"
        fake_root.mkdir()
        (fake_root / "version.json").write_text('{"version": "1.0.3", "channel": "stable"}', encoding="utf-8")
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        result = get_local_version()
        assert result == {"version": "1.0.3", "channel": "stable"}


class TestCompareVersions:
    def test_update_available(self):
        local = {"version": "1.0.0", "channel": "stable"}
        remote = {"version": "1.0.1", "channel": "stable", "notes": ["Fix"], "download_url": "url"}
        result = compare_versions(local, remote)
        assert result["update_available"] is True
        assert result["local_version"] == "1.0.0"
        assert result["remote_version"] == "1.0.1"
        assert result["message"] == "Có bản cập nhật mới"

    def test_up_to_date(self):
        local = {"version": "1.0.1", "channel": "stable"}
        remote = {"version": "1.0.1", "channel": "stable", "notes": [], "download_url": "url"}
        result = compare_versions(local, remote)
        assert result["update_available"] is False
        assert result["message"] == "Bạn đang dùng bản mới nhất"

    def test_local_newer(self):
        local = {"version": "1.0.2", "channel": "stable"}
        remote = {"version": "1.0.1", "channel": "stable", "notes": [], "download_url": "url"}
        result = compare_versions(local, remote)
        assert result["update_available"] is False

    def test_prerelease_available(self):
        local = {"version": "1.0.1-rc1", "channel": "stable"}
        remote = {"version": "1.0.1", "channel": "stable", "notes": ["Final release"], "download_url": "url"}
        result = compare_versions(local, remote)
        assert result["update_available"] is True
        assert result["local_version"] == "1.0.1-rc1"
        assert result["remote_version"] == "1.0.1"

    def test_passes_notes_and_url(self):
        local = {"version": "1.0.0", "channel": "stable"}
        remote = {"version": "1.0.1", "channel": "beta", "notes": ["New feature"], "download_url": "https://dl.example.com/pkg.zip"}
        result = compare_versions(local, remote)
        assert result["notes"] == ["New feature"]
        assert result["download_url"] == "https://dl.example.com/pkg.zip"
        assert result["channel"] == "beta"


class TestGetRemoteManifest:
    def test_missing_dict_raises(self, monkeypatch):
        monkeypatch.setattr("app.services.updater_service.httpx.get", lambda *a, **kw: _mock_response(200, ["not", "a", "dict"]))
        with pytest.raises(UpdaterError, match="đúng định dạng"):
            get_remote_manifest()

    def test_http_error_raises(self, monkeypatch):
        monkeypatch.setattr("app.services.updater_service.httpx.get", lambda *a, **kw: _mock_response(404, {}))
        with pytest.raises(UpdaterError):
            get_remote_manifest()


class TestLaunchUpdater:
    def test_missing_file_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", tmp_path)
        with pytest.raises(UpdaterError, match="Không tìm thấy"):
            launch_updater()

    def test_launch_default_no_flags(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "has_bat"
        fake_root.mkdir()
        (fake_root / "update_tool.bat").write_text("")
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        popen_args = {}
        def _fake_popen(cmd, **kw):
            popen_args["cmd"] = cmd
            class FakeProc:
                def poll(self): return None
                def wait(self): return 0
            return FakeProc()
        monkeypatch.setattr("app.services.updater_service.subprocess.Popen", _fake_popen)
        result = launch_updater()
        assert result["started"] is True
        assert "Vui lòng đóng" in result["message"]
        assert "-FromUI" not in popen_args["cmd"]
        assert "-RestartAfterUpdate" not in popen_args["cmd"]

    def test_launch_from_ui(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "has_bat2"
        fake_root.mkdir()
        (fake_root / "update_tool.bat").write_text("")
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        popen_args = {}
        def _fake_popen(cmd, **kw):
            popen_args["cmd"] = cmd
            class FakeProc:
                def poll(self): return None
                def wait(self): return 0
            return FakeProc()
        monkeypatch.setattr("app.services.updater_service.subprocess.Popen", _fake_popen)
        result = launch_updater(from_ui=True, restart_after_update=True)
        assert result["started"] is True
        assert "tự đóng" in result["message"]
        assert "-FromUI" in popen_args["cmd"]
        assert "-RestartAfterUpdate" in popen_args["cmd"]

    def test_launch_from_ui_only(self, monkeypatch, tmp_path):
        fake_root = tmp_path / "has_bat3"
        fake_root.mkdir()
        (fake_root / "update_tool.bat").write_text("")
        monkeypatch.setattr("app.services.updater_service.ROOT_DIR", fake_root)
        popen_args = {}
        def _fake_popen(cmd, **kw):
            popen_args["cmd"] = cmd
            class FakeProc:
                def poll(self): return None
                def wait(self): return 0
            return FakeProc()
        monkeypatch.setattr("app.services.updater_service.subprocess.Popen", _fake_popen)
        result = launch_updater(from_ui=True, restart_after_update=False)
        assert result["started"] is True
        assert "Vui lòng đóng" in result["message"]
        assert "-FromUI" in popen_args["cmd"]
        assert "-RestartAfterUpdate" not in popen_args["cmd"]


def _mock_response(status: int, data):
    class MockResp:
        def raise_for_status(self):
            if status >= 400:
                from httpx import HTTPStatusError
                raise HTTPStatusError("err", request=None, response=self)

        def json(self):
            return data

    resp = MockResp()
    resp.status_code = status
    return resp
