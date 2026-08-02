"""GuetLinker auto-start manager for Windows.

Manages the application's auto-start behaviour via the Windows
registry (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("guetlinker.autostart")

# Registry path for auto-start entries
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "GuetLinker"


class AutoStartManager:
    """Manage Windows auto-start via registry."""

    @staticmethod
    def is_enabled() -> bool:
        """Check if auto-start is currently enabled."""
        if sys.platform != "win32":
            logger.warning("Auto-start is only supported on Windows")
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
                try:
                    winreg.QueryValueEx(key, _APP_NAME)
                    return True
                except FileNotFoundError:
                    return False
        except OSError as e:
            logger.error("Failed to check auto-start status: %s", e)
            return False

    @staticmethod
    def enable() -> bool:
        """Enable auto-start on Windows boot.

        Returns:
            True if successfully enabled, False otherwise.
        """
        if sys.platform != "win32":
            logger.warning("Auto-start is only supported on Windows")
            return False

        command = AutoStartManager._get_start_command()
        if not command:
            logger.error("Cannot determine executable path for auto-start")
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, command)
            logger.info("Auto-start enabled: %s", command)
            return True
        except OSError as e:
            logger.error("Failed to enable auto-start: %s", e)
            return False

    @staticmethod
    def disable() -> bool:
        """Disable auto-start on Windows boot.

        Returns:
            True if successfully disabled, False otherwise.
        """
        if sys.platform != "win32":
            logger.warning("Auto-start is only supported on Windows")
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                    logger.info("Auto-start disabled")
                    return True
                except FileNotFoundError:
                    logger.info("Auto-start was not enabled")
                    return True
        except OSError as e:
            logger.error("Failed to disable auto-start: %s", e)
            return False

    @staticmethod
    def _get_start_command() -> str:
        """Build a quoted command that works for bundled and source launches."""
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --minimized'

        script_path = Path(__file__).resolve().parents[1] / "main.py"
        return f'"{sys.executable}" "{script_path}" --minimized'
