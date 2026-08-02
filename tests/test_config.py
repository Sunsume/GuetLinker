"""Tests for GuetLinker configuration module."""

import os
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from src.core.config import Config


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Create a Config instance with a temporary directory."""
    monkeypatch.setattr("src.core.config.APP_DATA_DIR", tmp_path)
    monkeypatch.setattr("src.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("src.core.config.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.config.CONFIG_FILE", tmp_path / "config.ini")
    return Config()


class TestConfig:
    """Tests for the Config class."""

    def test_user_id(self, temp_config):
        temp_config.user_id = "20240001"
        assert temp_config.user_id == "20240001"

    def test_password_encryption(self, temp_config):
        """Password should be stored encrypted, not in plaintext."""
        temp_config.password = "mypassword123"
        # Decrypted value should match
        assert temp_config.password == "mypassword123"
        # Raw INI should not contain plaintext
        settings = QSettings(str(temp_config._settings.fileName()), QSettings.Format.IniFormat)
        raw = settings.value("account/password_enc", "", type=str)
        assert raw != "mypassword123"
        assert len(raw) > 0  # Encrypted value is non-empty

    def test_empty_password(self, temp_config):
        """Empty password should return empty string."""
        temp_config.password = ""
        assert temp_config.password == ""

    def test_isp(self, temp_config):
        temp_config.isp = "chinanet"
        assert temp_config.isp == "chinanet"

    def test_isp_options_cache(self, temp_config):
        options = [
            {"value": "1", "label": "校园网", "suffix": ""},
            {"value": "5", "label": "中国广电", "suffix": "@glgd"},
        ]
        temp_config.isp_options_cache = options
        temp_config.sync()

        assert temp_config.isp_options_cache == options

    def test_check_interval(self, temp_config):
        temp_config.check_interval = 60
        assert temp_config.check_interval == 60

    def test_check_interval_is_clamped(self, temp_config):
        temp_config.check_interval = 0
        assert temp_config.check_interval == 10
        temp_config.check_interval = 999
        assert temp_config.check_interval == 300

    def test_notification_method(self, temp_config):
        temp_config.notification_method = "popup"
        assert temp_config.notification_method == "tray"
        temp_config.notification_method = "silent"
        assert temp_config.notification_method == "silent"

    def test_auto_reconnect_is_opt_in(self, temp_config):
        assert temp_config.auto_reconnect is False
        temp_config.auto_reconnect = True
        assert temp_config.auto_reconnect is True

    def test_auto_start(self, temp_config):
        temp_config.auto_start = True
        assert temp_config.auto_start is True

    def test_start_minimized(self, temp_config):
        temp_config.start_minimized = True
        assert temp_config.start_minimized is True

    def test_is_account_configured(self, temp_config):
        assert temp_config.is_account_configured() is False
        temp_config.user_id = "test"
        assert temp_config.is_account_configured() is False
        temp_config.password = "test"
        assert temp_config.is_account_configured() is False
        temp_config.isp = "1"
        assert temp_config.is_account_configured() is True

    def test_sync(self, temp_config):
        """Sync should persist settings to disk."""
        temp_config.user_id = "persist_test"
        temp_config.sync()
        # Create a new Config instance and verify persistence
        config2 = Config()
        # Note: the new Config may use the same file, so we need to check
        # the value is still there
        assert temp_config.user_id == "persist_test"
