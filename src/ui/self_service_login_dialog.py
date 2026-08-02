"""Modal login dialog for the independent GUET self-service account."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SelfServiceLoginDialog(QDialog):
    """Non-blocking modal dialog with an on-demand CAPTCHA row."""

    login_requested = Signal(str, str, str)
    captcha_refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("登录自助服务账户")
        self.setModal(True)
        self.setMinimumWidth(410)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(11)

        title = QLabel("自助服务账户")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        explanation = QLabel(
            "用于读取管理系统中的账户与流量信息，与校园网连接账号设置相互独立。"
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #64748b;")
        layout.addWidget(explanation)

        self._account_input = QLineEdit()
        self._account_input.setPlaceholderText("学号")
        self._account_input.setClearButtonEnabled(True)
        self._account_input.setMinimumHeight(40)
        layout.addWidget(self._account_input)

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("自助服务密码")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setMinimumHeight(40)
        layout.addWidget(self._password_input)

        self._show_password = QCheckBox("显示密码")
        self._show_password.toggled.connect(self._toggle_password)
        layout.addWidget(self._show_password)

        self._captcha_container = QWidget()
        captcha_layout = QHBoxLayout(self._captcha_container)
        captcha_layout.setContentsMargins(0, 0, 0, 0)
        captcha_layout.setSpacing(8)

        self._captcha_input = QLineEdit()
        self._captcha_input.setPlaceholderText("4 位验证码")
        self._captcha_input.setMaxLength(4)
        self._captcha_input.setMinimumHeight(38)
        captcha_layout.addWidget(self._captcha_input, 1)

        self._captcha_image = QLabel("加载中")
        self._captcha_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._captcha_image.setFixedSize(96, 38)
        self._captcha_image.setStyleSheet(
            "border: 1px solid #cbd5e1; border-radius: 4px; color: #64748b;"
        )
        captcha_layout.addWidget(self._captcha_image)

        self._captcha_refresh = QPushButton("换一张")
        self._captcha_refresh.clicked.connect(
            self.captcha_refresh_requested.emit
        )
        captcha_layout.addWidget(self._captcha_refresh)
        self._captcha_container.hide()
        layout.addWidget(self._captcha_container)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #dc2626; font-size: 13px;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        self._login_button = QPushButton("登录")
        self._login_button.setDefault(True)
        self._login_button.setMinimumWidth(100)
        self._login_button.clicked.connect(self._submit)
        buttons.addWidget(self._login_button)
        layout.addLayout(buttons)

        self._account_input.returnPressed.connect(self._submit)
        self._password_input.returnPressed.connect(self._submit)
        self._captcha_input.returnPressed.connect(self._submit)

    def open_for_login(self, account_hint: str = "") -> None:
        """Reset transient fields and open without blocking the event loop."""
        self.set_busy(False)
        self.set_error("")
        self.clear_captcha()
        self._account_input.setText(account_hint)
        self._password_input.clear()
        self._show_password.setChecked(False)
        self.open()
        if account_hint:
            self._password_input.setFocus()
        else:
            self._account_input.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._login_button.setEnabled(not busy)
        self._login_button.setText("正在登录..." if busy else "登录")
        self._account_input.setEnabled(not busy)
        self._password_input.setEnabled(not busy)
        self._captcha_input.setEnabled(not busy)
        self._captcha_refresh.setEnabled(not busy)

    def set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def show_captcha(self, image: bytes = b"", message: str = "") -> None:
        self._captcha_container.show()
        self.set_captcha_image(image)
        self.set_error(message)
        self._captcha_input.clear()
        self._captcha_input.setFocus()
        if not self.isVisible():
            self.open()

    def set_captcha_loading(self) -> None:
        self._captcha_refresh.setEnabled(False)
        self._captcha_image.setPixmap(QPixmap())
        self._captcha_image.setText("加载中")

    def set_captcha_image(self, image: bytes) -> None:
        self._captcha_refresh.setEnabled(True)
        pixmap = QPixmap()
        if image and pixmap.loadFromData(image):
            self._captcha_image.setText("")
            self._captcha_image.setPixmap(
                pixmap.scaled(
                    self._captcha_image.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._captcha_image.setPixmap(QPixmap())
            self._captcha_image.setText("点击刷新")

    def clear_captcha(self) -> None:
        self._captcha_input.clear()
        self._captcha_container.hide()

    def complete_login(self) -> None:
        self.set_busy(False)
        self.clear_captcha()
        self.set_error("")
        self._password_input.clear()
        self.accept()

    def _toggle_password(self, visible: bool) -> None:
        self._password_input.setEchoMode(
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )

    def _submit(self) -> None:
        account = self._account_input.text().strip()
        password = self._password_input.text()
        if not account or not password:
            self.set_error("请输入学号和密码")
            return
        if (
            not self._captcha_container.isHidden()
            and not self._captcha_input.text().strip()
        ):
            self.set_error("请输入验证码")
            self._captcha_input.setFocus()
            return
        self.set_error("")
        self.login_requested.emit(
            account,
            password,
            self._captcha_input.text().strip(),
        )
