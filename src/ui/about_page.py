"""GuetLinker about page and public project entry point."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src import __app_name__, __version__

PROJECT_URL = "https://github.com/Sunsume/GuetLinker"

# GitHub's official favicon is embedded so the About page never needs a
# network request just to render its project link.
GITHUB_ICON_SVG = b"""<svg width="32" height="32" viewBox="0 0 32 32"
fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M16 0C7.16 0 0 7.16 0 16C0
23.08 4.58 29.06 10.94 31.18C11.74 31.32 12.04 30.84 12.04 30.42C12.04
30.04 12.02 28.78 12.02 27.44C8 28.18 6.96 26.46 6.64 25.56C6.46 25.1
5.68 23.68 5 23.3C4.44 23 3.64 22.26 4.98 22.24C6.24 22.22 7.14 23.4
7.44 23.88C8.88 26.3 11.18 25.62 12.1 25.2C12.24 24.16 12.66 23.46
13.12 23.06C9.56 22.66 5.84 21.28 5.84 15.16C5.84 13.42 6.46 11.98
7.48 10.86C7.32 10.46 6.76 8.82 7.64 6.62C7.64 6.62 8.98 6.2 12.04
8.26C13.32 7.9 14.68 7.72 16.04 7.72C17.4 7.72 18.76 7.9 20.04
8.26C23.1 6.18 24.44 6.62 24.44 6.62C25.32 8.82 24.76 10.46 24.6
10.86C25.62 11.98 26.24 13.4 26.24 15.16C26.24 21.3 22.5 22.66
18.94 23.06C19.52 23.56 20.02 24.52 20.02 26.02C20.02 28.16 20 29.88
20 30.42C20 30.84 20.3 31.34 21.1 31.18C27.42 29.06 32 23.06 32
16C32 7.16 24.84 0 16 0V0Z" fill="#24292E"/>
</svg>"""


def github_icon() -> QIcon:
    """Create the embedded GitHub mark as a Qt icon."""
    pixmap = QPixmap()
    pixmap.loadFromData(GITHUB_ICON_SVG, "SVG")
    return QIcon(pixmap)


class AboutPage(QWidget):
    """Show application identity and a browser link to the source project."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.addStretch()

        name_label = QLabel(__app_name__)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #2563eb;"
        )
        layout.addWidget(name_label)

        version_label = QLabel(f"v{__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 14px; color: #64748b;")
        layout.addWidget(version_label)

        description = QLabel("桂电校园网连接与自助服务客户端")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setStyleSheet(
            "font-size: 14px; color: #334155; margin: 8px 0 4px 0;"
        )
        layout.addWidget(description)

        features = QLabel("实时状态检测 · 可选自动重连 · 系统托盘")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        features.setStyleSheet("font-size: 13px; color: #64748b;")
        layout.addWidget(features)

        self._project_button = QPushButton("访问我们的项目")
        self._project_button.setFlat(True)
        self._project_button.setIcon(github_icon())
        self._project_button.setIconSize(QSize(24, 24))
        self._project_button.setMinimumHeight(36)
        self._project_button.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self._project_button.setToolTip(PROJECT_URL)
        self._project_button.setStyleSheet(
            "QPushButton { background: transparent; color: #24292f; "
            "border: none; padding: 6px 10px; font-size: 14px; "
            "font-weight: 600; } "
            "QPushButton:hover { color: #2563eb; text-decoration: underline; } "
            "QPushButton:pressed { color: #1d4ed8; }"
        )
        self._project_button.clicked.connect(self._open_project_page)
        layout.addWidget(
            self._project_button,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        license_label = QLabel("MIT License · 非官方开源项目")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.setStyleSheet(
            "font-size: 12px; color: #94a3b8; margin-top: 8px;"
        )
        layout.addWidget(license_label)
        layout.addStretch()

    def _open_project_page(self) -> None:
        QDesktopServices.openUrl(QUrl(PROJECT_URL))
