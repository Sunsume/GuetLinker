"""GuetLinker status page.

Displays current network status, IP address, last check time,
and provides manual connect/disconnect buttons.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QFrame, QSizePolicy,
)

from src.core.monitor import NetworkStatus
from src.core.portal import PortalSession

logger = logging.getLogger("guetlinker.ui.status")


class StatusPage(QWidget):
    """Network status display page."""

    # Status indicator colors
    _STATUS_COLORS = {
        NetworkStatus.CONNECTED: "#4CAF50",     # Green
        NetworkStatus.DISCONNECTED: "#F44336",  # Red
        NetworkStatus.RECONNECTING: "#FF9800",  # Orange
        NetworkStatus.UNKNOWN: "#9E9E9E",       # Gray
    }

    _STATUS_LABELS = {
        NetworkStatus.CONNECTED: "已连接",
        NetworkStatus.DISCONNECTED: "已断网",
        NetworkStatus.RECONNECTING: "重连中...",
        NetworkStatus.UNKNOWN: "未知",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_status = NetworkStatus.UNKNOWN
        self._portal_session_online = False
        self._login_in_progress = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Status indicator ──────────────────────────────────────
        status_layout = QHBoxLayout()

        self._indicator = QLabel()
        self._indicator.setFixedSize(24, 24)
        self._indicator.setStyleSheet(
            "background-color: #9E9E9E; border-radius: 12px;"
        )
        status_layout.addWidget(self._indicator)

        self._status_label = QLabel("未知")
        self._status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()

        layout.addLayout(status_layout)

        # ── Info section ──────────────────────────────────────────
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(8)

        self._account_label = QLabel("当前账号: --")
        self._account_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self._account_label)

        self._operator_label = QLabel("接入运营商: --")
        self._operator_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self._operator_label)

        self._ip_label = QLabel("IPv4 地址: --")
        self._ip_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self._ip_label)

        self._ipv6_label = QLabel("IPv6 地址: --")
        self._ipv6_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self._ipv6_label)

        self._last_check_label = QLabel("上次检测: --")
        self._last_check_label.setStyleSheet("font-size: 14px; color: #666;")
        info_layout.addWidget(self._last_check_label)

        layout.addWidget(info_frame)

        # ── Action buttons ────────────────────────────────────────
        btn_layout = QHBoxLayout()

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setMinimumHeight(40)
        self._connect_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        btn_layout.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.setMinimumHeight(40)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.setStyleSheet(
            "QPushButton { background-color: #F44336; color: white; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #da190b; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        btn_layout.addWidget(self._disconnect_btn)

        layout.addLayout(btn_layout)

        # ── Recent logs ───────────────────────────────────────────
        log_label = QLabel("最近日志")
        log_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 8px;")
        layout.addWidget(log_label)

        self._log_list = QListWidget()
        self._log_list.setMaximumHeight(200)
        self._log_list.setStyleSheet(
            "QListWidget { border: 1px solid #ddd; border-radius: 4px; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }"
        )
        layout.addWidget(self._log_list)

        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────

    @property
    def connect_button(self) -> QPushButton:
        return self._connect_btn

    @property
    def disconnect_button(self) -> QPushButton:
        return self._disconnect_btn

    @Slot(object)
    def update_status(self, status: NetworkStatus) -> None:
        """Update the status indicator and label."""
        color = self._STATUS_COLORS.get(status, "#9E9E9E")
        label = self._STATUS_LABELS.get(status, "未知")
        if status == NetworkStatus.CONNECTED and self._portal_session_online:
            label = "校园网已登录"

        self._indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 12px;"
        )
        self._status_label.setText(label)
        self._current_status = status

        self._update_action_buttons()

        # Update last check time
        self.update_last_check()

    @Slot(str)
    def update_ip(self, ip: str) -> None:
        """Update the IP address display."""
        self._ip_label.setText(f"IPv4 地址: {ip or '--'}")

    @Slot(object)
    def update_portal_session(self, session: PortalSession) -> None:
        """Display public account and IP details from the portal online page."""
        self._portal_session_online = session.is_online
        self._account_label.setText(f"当前账号: {session.account_id or '--'}")
        self._operator_label.setText(
            f"接入运营商: {session.operator_name or '--'}"
        )
        self._ip_label.setText(f"IPv4 地址: {session.ipv4 or '--'}")
        self._ipv6_label.setText(f"IPv6 地址: {session.ipv6 or '--'}")
        if self._current_status == NetworkStatus.CONNECTED:
            self._status_label.setText(
                "校园网已登录" if session.is_online else "已连接"
            )
        self._update_action_buttons()

    @Slot()
    def update_last_check(self) -> None:
        """Show completion time for the 500 ms real-time status probe."""
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._last_check_label.setText(f"上次检测: {now}")

    def set_login_in_progress(self, in_progress: bool) -> None:
        """Switch the connect action between login and cancellation."""
        self._login_in_progress = in_progress
        self._connect_btn.setText("取消连接" if in_progress else "连接")
        self._update_action_buttons()

    @Slot(str)
    def add_log(self, message: str) -> None:
        """Add a log entry to the recent log list."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_list.insertItem(0, f"[{timestamp}] {message}")

        # Keep only last 10 entries
        while self._log_list.count() > 10:
            self._log_list.takeItem(self._log_list.count() - 1)

    def _update_action_buttons(self) -> None:
        """Keep actions consistent with connectivity and portal-session state."""
        can_connect = self._login_in_progress or self._current_status in {
            NetworkStatus.DISCONNECTED,
            NetworkStatus.UNKNOWN,
        }
        can_disconnect = (
            not self._login_in_progress
            and
            self._current_status == NetworkStatus.CONNECTED
            and self._portal_session_online
        )
        self._connect_btn.setEnabled(can_connect)
        self._disconnect_btn.setEnabled(can_disconnect)
