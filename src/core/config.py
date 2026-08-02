"""GuetLinker configuration management.

Uses QSettings with INI format for cross-platform storage.
Passwords are encrypted with Fernet symmetric encryption.
"""

import os
import base64
import hashlib
import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from cryptography.fernet import Fernet

logger = logging.getLogger("guetlinker.config")

MIN_CHECK_INTERVAL = 10
MAX_CHECK_INTERVAL = 300

# Platform-specific app data directory
if os.name == "nt":
    APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "GuetLinker"
else:
    APP_DATA_DIR = Path.home() / ".guetlinker"

CONFIG_DIR = APP_DATA_DIR
CONFIG_FILE = CONFIG_DIR / "config.ini"
LOG_DIR = APP_DATA_DIR / "logs"


class Config:
    """Application configuration manager with encrypted password storage."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            CONFIG_DIR.chmod(0o700)
            LOG_DIR.chmod(0o700)

        self._settings = QSettings(
            str(CONFIG_FILE), QSettings.Format.IniFormat
        )
        self._fernet = self._get_fernet()

    # ── Account settings ──────────────────────────────────────────

    @property
    def user_id(self) -> str:
        return self._settings.value("account/user_id", "", type=str)

    @user_id.setter
    def user_id(self, value: str) -> None:
        self._settings.setValue("account/user_id", value)

    @property
    def password(self) -> str:
        """Get decrypted password."""
        encrypted = self._settings.value("account/password_enc", "", type=str)
        if not encrypted:
            return ""
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            logger.warning("Failed to decrypt password, returning empty")
            return ""

    @password.setter
    def password(self, value: str) -> None:
        """Set and encrypt password."""
        if not value:
            self._settings.setValue("account/password_enc", "")
            return
        encrypted = self._fernet.encrypt(value.encode()).decode()
        self._settings.setValue("account/password_enc", encrypted)

    @property
    def isp(self) -> str:
        return self._settings.value("account/isp", "", type=str)

    @isp.setter
    def isp(self, value: str) -> None:
        self._settings.setValue("account/isp", value)

    @property
    def isp_options_cache(self) -> list[dict[str, str]]:
        """Last successfully fetched ISP list for immediate startup display."""
        raw = self._settings.value("account/isp_options_cache", "", type=str)
        if not raw:
            return []
        try:
            options = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid ISP options cache, ignoring")
            return []
        if not isinstance(options, list):
            return []
        return [
            {
                "value": str(item.get("value", "")),
                "label": str(item.get("label", "")),
                "suffix": str(item.get("suffix", "")),
            }
            for item in options
            if isinstance(item, dict)
            and item.get("value")
            and item.get("label")
        ]

    @isp_options_cache.setter
    def isp_options_cache(self, options: list[dict[str, str]]) -> None:
        self._settings.setValue(
            "account/isp_options_cache",
            json.dumps(options, ensure_ascii=False),
        )

    # ── Network settings ──────────────────────────────────────────

    @property
    def check_interval(self) -> int:
        """Network check interval in seconds, clamped to the supported range."""
        value = self._settings.value("network/check_interval", 30, type=int)
        return max(MIN_CHECK_INTERVAL, min(MAX_CHECK_INTERVAL, value))

    @check_interval.setter
    def check_interval(self, value: int) -> None:
        self._settings.setValue(
            "network/check_interval",
            max(MIN_CHECK_INTERVAL, min(MAX_CHECK_INTERVAL, value)),
        )

    @property
    def portal_url(self) -> str:
        return self._settings.value("network/portal_url", "http://10.0.1.5/", type=str)

    @portal_url.setter
    def portal_url(self, value: str) -> None:
        self._settings.setValue("network/portal_url", value)

    @property
    def auto_reconnect(self) -> bool:
        """Whether detected campus-network outages trigger automatic login."""
        return self._settings.value("network/auto_reconnect", False, type=bool)

    @auto_reconnect.setter
    def auto_reconnect(self, value: bool) -> None:
        self._settings.setValue("network/auto_reconnect", value)

    # ── Notification settings ─────────────────────────────────────

    @property
    def notification_method(self) -> str:
        """Notification method: ``silent`` or system-tray bubble."""
        value = self._settings.value("notification/method", "tray", type=str)
        # Migrate the removed popup option without losing notifications.
        return value if value in {"silent", "tray"} else "tray"

    @notification_method.setter
    def notification_method(self, value: str) -> None:
        self._settings.setValue(
            "notification/method",
            value if value in {"silent", "tray"} else "tray",
        )

    # ── System settings ───────────────────────────────────────────

    @property
    def auto_start(self) -> bool:
        return self._settings.value("system/auto_start", False, type=bool)

    @auto_start.setter
    def auto_start(self, value: bool) -> None:
        self._settings.setValue("system/auto_start", value)

    @property
    def start_minimized(self) -> bool:
        return self._settings.value("system/start_minimized", False, type=bool)

    @start_minimized.setter
    def start_minimized(self, value: bool) -> None:
        self._settings.setValue("system/start_minimized", value)

    # ── Helpers ───────────────────────────────────────────────────

    def _get_fernet(self) -> Fernet:
        """Get or create a Fernet key bound to this machine."""
        key_str = self._settings.value("encryption/key", "", type=str)
        if key_str:
            try:
                return Fernet(key_str.encode())
            except Exception:
                logger.warning("Invalid stored Fernet key, regenerating")

        # Generate machine-bound key from hostname + username
        machine_id = f"{os.environ.get('COMPUTERNAME', os.environ.get('HOSTNAME', 'unknown'))}:{os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))}"
        key = base64.urlsafe_b64encode(
            hashlib.sha256(machine_id.encode()).digest()
        )
        fernet = Fernet(key)
        self._settings.setValue("encryption/key", key.decode())
        return fernet

    def sync(self) -> None:
        """Force write settings to disk."""
        self._settings.sync()
        if os.name != "nt" and CONFIG_FILE.exists():
            CONFIG_FILE.chmod(0o600)

    def is_account_configured(self) -> bool:
        """Check if account credentials are set."""
        return bool(self.user_id and self.password and self.isp)
