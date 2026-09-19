"""GuetLinker system tray icon.

Provides a system tray icon with context menu for quick access
to common actions.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QGuiApplication
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from src.core.monitor import NetworkStatus
from src.core.network_speed import NetworkSpeed, format_bytes_per_second
from src.core.portal import PortalSession

logger = logging.getLogger("guetlinker.ui.tray")


class QtTrayIcon(QSystemTrayIcon):
    """System tray icon with context menu.

    Signals from parent (QSystemTrayIcon):
        activated: Emitted when the tray icon is clicked.
        messageClicked: Emitted when a balloon message is clicked.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._status = NetworkStatus.UNKNOWN
        self._portal_session_online = False
        self._login_in_progress = False
        self._speed = NetworkSpeed()
        self._setup_menu()
        self._setup_connections()

        # Set initial icon
        self._update_icon(NetworkStatus.UNKNOWN)

    def _setup_menu(self) -> None:
        """Create the context menu."""
        self._menu = QMenu()

        self._show_action = QAction("显示主窗口", self)
        self._menu.addAction(self._show_action)

        self._menu.addSeparator()

        self._check_action = QAction("立即检测", self)
        self._menu.addAction(self._check_action)

        self._connect_action = QAction("连接", self)
        self._menu.addAction(self._connect_action)

        self._disconnect_action = QAction("断开", self)
        self._disconnect_action.setEnabled(False)
        self._menu.addAction(self._disconnect_action)

        self._menu.addSeparator()

        self._quit_action = QAction("退出", self)
        self._menu.addAction(self._quit_action)

        self.setContextMenu(self._menu)

    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation (double-click shows window)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_action.trigger()

    # ── Public API ────────────────────────────────────────────────

    @property
    def show_action(self) -> QAction:
        return self._show_action

    @property
    def check_action(self) -> QAction:
        return self._check_action

    @property
    def connect_action(self) -> QAction:
        return self._connect_action

    @property
    def disconnect_action(self) -> QAction:
        return self._disconnect_action

    @property
    def quit_action(self) -> QAction:
        return self._quit_action

    def update_status(self, status: NetworkStatus) -> None:
        """Update the tray icon and tooltip based on network status."""
        self._status = status
        self._update_icon(status)

        status_text = {
            NetworkStatus.CONNECTED: "已连接",
            NetworkStatus.DISCONNECTED: "已断网",
            NetworkStatus.RECONNECTING: "重连中...",
            NetworkStatus.UNKNOWN: "未知",
        }.get(status, "未知")
        if status == NetworkStatus.CONNECTED and self._portal_session_online:
            status_text = "校园网已登录"

        self.setToolTip(f"GuetLinker — {status_text}")
        self._update_action_states()

    def update_portal_session(self, session: PortalSession) -> None:
        """Enable portal actions only when an authenticated session is known."""
        self._portal_session_online = session.is_online
        if self._status == NetworkStatus.CONNECTED:
            self.setToolTip(
                "GuetLinker — 校园网已登录"
                if session.is_online
                else "GuetLinker — 已连接"
            )
        self._update_action_states()

    def update_network_speed(self, speed: NetworkSpeed) -> None:
        """Expose live speed in the tooltip on non-macOS platforms."""
        self._speed = speed
        base_tooltip = self.toolTip().split(" · ↓", 1)[0]
        self.setToolTip(
            f"{base_tooltip} · ↓ {format_bytes_per_second(speed.download_bps)}"
            f" · ↑ {format_bytes_per_second(speed.upload_bps)}"
        )

    def set_login_in_progress(self, in_progress: bool) -> None:
        """Switch the tray connect action to a cancellation action."""
        self._login_in_progress = in_progress
        self._connect_action.setText("取消连接" if in_progress else "连接")
        self._update_action_states()

    def show_notification(
        self,
        title: str,
        message: str,
        method: str = "tray",
    ) -> None:
        """Show a notification to the user.

        Args:
            title: Notification title.
            message: Notification body.
            method: ``tray`` for a system-tray bubble or ``silent``.
        """
        if method == "silent":
            return

        if self.supportsMessages():
            self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
        else:
            # Never fall back to a blocking popup.
            logger.info("Notification: %s — %s", title, message)

    def _update_icon(self, status: NetworkStatus) -> None:
        """Update the tray icon based on status.

        Uses system standard pixmaps since we don't have custom icons yet.
        """
        # Use the application window icon when one has been supplied.
        app_icon = QGuiApplication.windowIcon()
        if not app_icon.isNull():
            self.setIcon(app_icon)
            return

        from PySide6.QtGui import QColor, QPainter, QPixmap

        color_map = {
            NetworkStatus.CONNECTED: QColor("#4CAF50"),
            NetworkStatus.DISCONNECTED: QColor("#F44336"),
            NetworkStatus.RECONNECTING: QColor("#FF9800"),
            NetworkStatus.UNKNOWN: QColor("#9E9E9E"),
        }
        pixmap = QPixmap(QSize(32, 32))
        pixmap.fill(Qt.GlobalColor.transparent)
        with QPainter(pixmap) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(color_map.get(status, QColor("#9E9E9E")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, 28, 28)
        self.setIcon(QIcon(pixmap))

    def _update_action_states(self) -> None:
        self._connect_action.setEnabled(
            self._login_in_progress
            or self._status in {
                NetworkStatus.DISCONNECTED,
                NetworkStatus.UNKNOWN,
            }
        )
        self._disconnect_action.setEnabled(
            not self._login_in_progress
            and
            self._status == NetworkStatus.CONNECTED
            and self._portal_session_online
        )


if sys.platform == "darwin":
    from src.ui.macos_tray_icon import MacOSTrayIcon as TrayIcon
else:
    TrayIcon = QtTrayIcon
