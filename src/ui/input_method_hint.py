"""A small, non-blocking input-method reminder for password editors."""

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QLineEdit

from src.core.input_method import is_chinese_input_active


class InputMethodHint(QLabel):
    def __init__(self, editor: QLineEdit) -> None:
        super().__init__("⚠ 当前为中文输入法，建议切换到英文后输入密码", editor.parentWidget())
        self._editor = editor
        self.setWordWrap(True)
        self.setStyleSheet("color: #b45309; font-size: 12px;")
        self.setAccessibleName("密码输入法提示")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)
        editor.installEventFilter(self)
        method = QGuiApplication.inputMethod()
        if method:
            method.localeChanged.connect(self.refresh)

    def eventFilter(self, watched, event):
        if watched is self._editor:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.Show):
                if self._editor.hasFocus():
                    self._timer.start()
                    QTimer.singleShot(0, self.refresh)
            elif event.type() in (QEvent.Type.FocusOut, QEvent.Type.Hide):
                self._timer.stop()
                self.hide()
            elif event.type() == QEvent.Type.KeyRelease:
                self.refresh()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        focused = self._editor.hasFocus() and self._editor.isVisible()
        self.setVisible(focused and is_chinese_input_active())
