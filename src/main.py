"""GuetLinker application entry point.

Usage:
    python -m src.main [options]
    python src/main.py [options]
"""

from __future__ import annotations

import sys
import argparse

from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.single_instance import SingleInstanceGuard


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="GuetLinker — 校园网自动连接客户端",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start minimized to system tray",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> int:
    """Application entry point."""
    args = parse_args()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("GuetLinker")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("GuetLinker")

    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        QMessageBox.information(
            None,
            "GuetLinker 已在运行",
            "检测到 GuetLinker 已经在运行，不能重复启动。\n"
            "请从任务栏或系统托盘打开现有窗口。",
        )
        return 0

    # Prevent quitting when last window is hidden (tray mode)
    app.setQuitOnLastWindowClosed(False)

    try:
        # Initialize and run the app
        from src.app import GuetLinkerApp
        guetlinker = GuetLinkerApp(app, args)

        return app.exec()
    finally:
        instance_guard.release()


if __name__ == "__main__":
    sys.exit(main())
