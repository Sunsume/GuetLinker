"""GuetLinker about page.

Displays application information.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
)

from src import __app_name__, __version__


class AboutPage(QWidget):
    """Application about page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # App name
        name_label = QLabel(__app_name__)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #2196F3;"
        )
        layout.addWidget(name_label)

        # Version
        version_label = QLabel(f"v{__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(version_label)

        # Description
        desc_label = QLabel("校园网自动连接客户端")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px; color: #333; margin-top: 12px;")
        layout.addWidget(desc_label)

        desc2 = QLabel("自动检测断网并重连 · 开机自启 · 系统托盘")
        desc2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc2.setStyleSheet("font-size: 13px; color: #666;")
        layout.addWidget(desc2)

        # License
        license_label = QLabel("MIT License")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.setStyleSheet("font-size: 12px; color: #999; margin-top: 20px;")
        layout.addWidget(license_label)

        layout.addStretch()
