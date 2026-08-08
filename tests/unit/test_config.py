import pytest

from lib.config import get_satellite_settings


def _patch_config(monkeypatch, cfg):
    monkeypatch.setattr("lib.config._cfg", cfg)


def test_satellite_settings_userpass(monkeypatch):
    _patch_config(
        monkeypatch,
        {
            "satellite": {
                "url": "https://sat.example.com",
                "username": "tpa",
                "password": "secret",
                "verify_ssl": False,
            }
        },
    )
    s = get_satellite_settings()
    assert s["url"] == "https://sat.example.com"
    assert s["username"] == "tpa"
    assert s["password"] == "secret"
    assert s["api_token"] is None
    assert s["verify_ssl"] is False
    assert s["max_workers"] == 16


def test_satellite_settings_token_and_defaults(monkeypatch):
    _patch_config(monkeypatch, {"satellite": {"url": "https://sat.example.com", "token": "abc"}})
    s = get_satellite_settings()
    assert s["api_token"] == "abc"
    assert s["username"] is None
    assert s["verify_ssl"] is True
    assert s["timeout"] == 30
    assert s["per_page"] == 100


def test_satellite_settings_missing_section(monkeypatch):
    _patch_config(monkeypatch, {"database": {"url": "x"}})
    with pytest.raises(KeyError):
        get_satellite_settings()


def test_satellite_settings_missing_url(monkeypatch):
    _patch_config(monkeypatch, {"satellite": {"username": "tpa"}})
    with pytest.raises(KeyError):
        get_satellite_settings()
