"""Tests for cached and dynamically refreshed ISP settings."""

import subprocess
import sys
from types import SimpleNamespace

import httpx
from PySide6.QtWidgets import QMessageBox

from src.app import GuetLinkerApp
from src.core import config as config_module
from src.core.auth_client import AuthClient, ISPInfo
from src.ui.settings_page import SettingsPage


class FakeConfig:
    def __init__(self):
        self.user_id = "20240001"
        self.password = "secret"
        self.isp = "5"
        self.isp_options_cache = [
            {"value": "1", "label": "校园网", "suffix": ""},
            {"value": "5", "label": "中国广电", "suffix": "@glgd"},
        ]
        self.check_interval = 30
        self.auto_reconnect = False
        self.notification_method = "tray"
        self.auto_start = False
        self.start_minimized = False
        self.synced = 0

    def sync(self):
        self.synced += 1


def test_cached_isp_list_and_selection_are_visible_immediately(qapp):
    config = FakeConfig()

    page = SettingsPage(config=config)

    assert page._isp_combo.count() == 2
    assert page._isp_combo.currentData() == "5"
    assert page._isp_combo.currentText() == "中国广电"
    assert page._auto_reconnect_check.isChecked() is False
    assert not hasattr(page, "_popup_radio")
    assert not hasattr(page, "_interval_slider")
    assert page._user_id_input.text() == "20240001"
    assert page._password_input.text() == "secret"


def test_dynamic_refresh_preserves_saved_selection_and_updates_cache(qapp):
    config = FakeConfig()
    page = SettingsPage(config=config)
    latest = [
        ISPInfo("1", "校园网", ""),
        ISPInfo("2", "中国移动", "@cmcc"),
        ISPInfo("5", "中国广电", "@glgd"),
    ]

    missing = page.set_isp_options(
        latest,
        persist=True,
        notify_missing=True,
    )

    assert missing is False
    assert page._isp_combo.currentData() == "5"
    assert config.isp == "5"
    assert config.isp_options_cache == [
        {"value": "1", "label": "校园网", "suffix": ""},
        {"value": "2", "label": "中国移动", "suffix": "@cmcc"},
        {"value": "5", "label": "中国广电", "suffix": "@glgd"},
    ]


def test_missing_saved_isp_warns_and_requires_new_selection(
    qapp,
    monkeypatch,
):
    config = FakeConfig()
    page = SettingsPage(config=config)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )

    missing = page.set_isp_options(
        [
            ISPInfo("1", "校园网", ""),
            ISPInfo("2", "中国移动", "@cmcc"),
        ],
        persist=True,
        notify_missing=True,
    )

    assert missing is True
    assert config.isp == ""
    assert page._isp_combo.currentIndex() == -1
    assert len(warnings) == 1
    assert "中国广电" in warnings[0]


def test_save_persists_auto_reconnect_and_tray_only_notification(
    qapp,
    monkeypatch,
):
    config = FakeConfig()
    page = SettingsPage(config=config)
    page._auto_reconnect_check.setChecked(True)
    page._tray_radio.setChecked(True)
    page._user_id_input.setText("20249999")
    page._password_input.setText("new-secret")
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

    page._on_save()

    assert config.auto_reconnect is True
    assert config.notification_method == "tray"
    assert config.user_id == "20249999"
    assert config.password == "new-secret"


def test_changed_password_survives_save_restart_and_login(qapp, tmp_path, monkeypatch):
    """Use real encrypted settings and capture HTTP without contacting a gateway."""
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.ini")
    monkeypatch.setattr(config_module, "LOG_DIR", tmp_path / "logs")
    config = config_module.Config()
    config.user_id = "20240001"
    config.password = "old-test-password"
    config.isp = "5"
    config.isp_options_cache = [
        {"value": "5", "label": "中国广电", "suffix": "@glgd"},
    ]
    config.sync()

    page = SettingsPage(config=config)
    page._password_input.setText("päss!")
    saved = []
    page.settings_saved.connect(lambda: saved.append(True))
    page._save_btn.click()

    assert saved == [True]
    assert config.password == "päss!"
    assert "päss!" not in (tmp_path / "config.ini").read_text()

    # Another process cannot see QSettings' shared in-memory cache.
    reader = subprocess.run(
        [
            sys.executable, "-c",
            "from pathlib import Path\n"
            "import sys\n"
            "from src.core import config as module\n"
            "module.CONFIG_DIR = Path(sys.argv[1])\n"
            "module.CONFIG_FILE = module.CONFIG_DIR / 'config.ini'\n"
            "module.LOG_DIR = module.CONFIG_DIR / 'logs'\n"
            "sys.stdout.write(module.Config().password)\n",
            str(tmp_path),
        ],
        capture_output=True, text=True, check=True, timeout=10,
    )
    assert reader.stdout == "päss!"

    requests = []
    auth = AuthClient()

    def capture(request):
        requests.append(request)
        return httpx.Response(200, text='dr1003({"result":1})')

    def start_login(user_id, password, isp_value):
        with httpx.Client(transport=httpx.MockTransport(capture)) as mock:
            auth._request_wireless_login(
                mock, auth._account_with_isp_suffix(user_id, isp_value), password, {}
            )
        return True

    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    controller._config = config_module.Config()
    controller._auth_client = SimpleNamespace(start_login=start_login)
    controller._monitor = SimpleNamespace(invalidate_pending_probe=lambda: None)
    try:
        controller._do_login()
        assert len(requests) == 1
        assert requests[0].url.params["user_account"] == ",0,20240001@glgd"
        assert requests[0].url.params["user_password"] == "cORzcyE="
    finally:
        auth.close()
