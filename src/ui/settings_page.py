"""GuetLinker settings page.

Allows users to configure campus-network credentials, operator, and
application behaviour. These credentials are independent from self-service.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QComboBox, QLabel, QLineEdit,
    QRadioButton, QButtonGroup, QCheckBox,
    QPushButton, QGroupBox, QMessageBox,
)

from src.core.config import Config
from src.core.auth_client import AuthClient, ISPInfo
from src.ui.input_method_hint import InputMethodHint

logger = logging.getLogger("guetlinker.ui.settings")


class SettingsPage(QWidget):
    """Application settings page."""

    settings_saved = Signal()

    def __init__(
        self,
        config: Config | None = None,
        auth_client: AuthClient | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._auth_client = auth_client
        self._setup_ui()
        if self._config:
            self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Campus network connection ─────────────────────────────
        connection_group = QGroupBox("校园网连接")
        connection_layout = QFormLayout()
        connection_layout.setSpacing(10)

        self._user_id_input = QLineEdit()
        self._user_id_input.setPlaceholderText("请输入校园网学号")
        self._user_id_input.setClearButtonEnabled(True)
        connection_layout.addRow("学号:", self._user_id_input)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("请输入校园网密码")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow("密码:", self._password_input)
        self._password_input_hint = InputMethodHint(self._password_input)
        connection_layout.addRow("", self._password_input_hint)

        self._isp_combo = QComboBox()
        self._isp_combo.setPlaceholderText("请先获取运营商列表")
        self._isp_combo.setMinimumWidth(200)

        isp_layout = QHBoxLayout()
        isp_layout.addWidget(self._isp_combo)
        self._refresh_isp_btn = QPushButton("刷新")
        self._refresh_isp_btn.setFixedWidth(60)
        self._refresh_isp_btn.setToolTip("从登录页获取运营商列表")
        isp_layout.addWidget(self._refresh_isp_btn)
        connection_layout.addRow("运营商:", isp_layout)

        connection_help = QLabel(
            "这里的凭据只用于连接校园网，与“账户”页的自助服务登录相互独立。"
            "运营商列表会在启动时自动更新并保留历史选择。"
        )
        connection_help.setWordWrap(True)
        connection_help.setStyleSheet("color: #64748b;")
        connection_layout.addRow("", connection_help)

        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)

        # ── Notification settings ─────────────────────────────────
        notif_group = QGroupBox("通知设置")
        notif_layout = QVBoxLayout()
        notif_layout.setSpacing(8)

        self._notif_group = QButtonGroup(self)
        self._silent_radio = QRadioButton("静默（不通知）")
        self._tray_radio = QRadioButton("通知栏气泡")
        self._tray_radio.setChecked(True)

        self._notif_group.addButton(self._silent_radio, 0)
        self._notif_group.addButton(self._tray_radio, 1)

        notif_layout.addWidget(self._silent_radio)
        notif_layout.addWidget(self._tray_radio)

        notif_group.setLayout(notif_layout)
        layout.addWidget(notif_group)

        # ── System settings ───────────────────────────────────────
        system_group = QGroupBox("系统设置")
        system_layout = QVBoxLayout()
        system_layout.setSpacing(8)

        self._auto_reconnect_check = QCheckBox("断网后自动重连")
        self._auto_reconnect_check.setToolTip(
            "检测到校园网掉线后，使用上方校园网账号和已选运营商自动连接"
        )
        self._auto_start_check = QCheckBox("开机自动启动")
        self._start_minimized_check = QCheckBox("启动时最小化到托盘")

        system_layout.addWidget(self._auto_reconnect_check)
        system_layout.addWidget(self._auto_start_check)
        system_layout.addWidget(self._start_minimized_check)

        system_group.setLayout(system_layout)
        layout.addWidget(system_group)

        # ── Save button ───────────────────────────────────────────
        self._save_btn = QPushButton("保存设置")
        self._save_btn.setMinimumHeight(40)
        self._save_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1976D2; }"
        )
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)

        self._save_state_label = QLabel()
        self._save_state_label.setStyleSheet("color: #16a34a;")
        self._save_state_label.hide()
        layout.addWidget(self._save_state_label)

        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────

    @property
    def refresh_isp_button(self) -> QPushButton:
        return self._refresh_isp_btn

    def set_isp_options(
        self,
        options: list[ISPInfo],
        *,
        persist: bool = True,
        notify_missing: bool = False,
    ) -> bool:
        """Replace ISP options while preserving and validating selection.

        Returns True when the saved selection disappeared from a successful
        dynamic refresh.
        """
        if not options:
            return False

        current_value = self._isp_combo.currentData()
        saved_value = self._config.isp if self._config else ""
        selected_value = current_value or saved_value
        previous_labels = {
            self._isp_combo.itemData(index): self._isp_combo.itemText(index)
            for index in range(self._isp_combo.count())
        }

        self._isp_combo.clear()
        for opt in options:
            self._isp_combo.addItem(opt.label, opt.value)

        selected_index = self._isp_combo.findData(selected_value)
        if selected_index >= 0:
            self._isp_combo.setCurrentIndex(selected_index)
        else:
            saved_index = self._isp_combo.findData(saved_value)
            self._isp_combo.setCurrentIndex(saved_index)

        if self._config and persist:
            self._config.isp_options_cache = [
                {
                    "value": option.value,
                    "label": option.label,
                    "suffix": option.suffix,
                }
                for option in options
            ]
            self._config.sync()

        selection_missing = bool(saved_value and self._isp_combo.findData(saved_value) < 0)
        if self._config and selection_missing and notify_missing:
            old_label = previous_labels.get(saved_value, saved_value)
            self._config.isp = ""
            self._config.sync()
            QMessageBox.warning(
                self,
                "运营商已不可用",
                f"你之前选择的运营商“{old_label}”已不在最新列表中。\n"
                "请重新选择运营商并保存设置。",
            )
        return selection_missing

    def set_isp_refreshing(self, refreshing: bool) -> None:
        """Show non-blocking refresh progress and prevent duplicate requests."""
        self._refresh_isp_btn.setEnabled(not refreshing)
        self._refresh_isp_btn.setText("获取中" if refreshing else "刷新")

    def _load_settings(self) -> None:
        """Load settings from Config into UI controls."""
        if not self._config:
            return

        self._user_id_input.setText(self._config.user_id)
        self._password_input.setText(self._config.password)
        self._auto_reconnect_check.setChecked(self._config.auto_reconnect)

        if self._isp_combo.count() == 0:
            cached_options = [
                ISPInfo(
                    value=item["value"],
                    label=item["label"],
                    suffix=item.get("suffix", ""),
                )
                for item in self._config.isp_options_cache
            ]
            if cached_options:
                self.set_isp_options(
                    cached_options,
                    persist=False,
                    notify_missing=False,
                )

        # Notification method
        method = self._config.notification_method
        if method == "silent":
            self._silent_radio.setChecked(True)
        else:
            self._tray_radio.setChecked(True)

        self._auto_start_check.setChecked(self._config.auto_start)
        self._start_minimized_check.setChecked(self._config.start_minimized)

    def _on_save(self) -> None:
        """Save current UI settings to Config."""
        if not self._config:
            return

        user_id = self._user_id_input.text().strip()
        password = self._password_input.text()
        selected_isp = self._isp_combo.currentData()
        if not user_id or not password or not selected_isp:
            QMessageBox.warning(
                self,
                "提示",
                "请填写校园网学号、密码并选择运营商后再保存。",
            )
            return

        self._config.user_id = user_id
        self._config.password = password
        self._config.auto_reconnect = self._auto_reconnect_check.isChecked()
        self._config.isp = selected_isp

        # Notification method
        checked = self._notif_group.checkedId()
        method_map = {0: "silent", 1: "tray"}
        self._config.notification_method = method_map.get(checked, "tray")

        # System settings
        self._config.auto_start = self._auto_start_check.isChecked()
        self._config.start_minimized = self._start_minimized_check.isChecked()

        self._config.sync()

        logger.info("Settings saved")
        self.settings_saved.emit()
        self._save_state_label.setText("设置已保存")
        self._save_state_label.show()
