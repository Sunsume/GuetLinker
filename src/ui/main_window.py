"""GuetLinker main window with an always-available tabbed interface."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from src import __app_name__, __version__
from src.ui.account_page import AccountPage
from src.ui.self_service_login_dialog import SelfServiceLoginDialog
from src.ui.status_page import StatusPage
from src.ui.settings_page import SettingsPage
from src.ui.about_page import AboutPage

logger = logging.getLogger("guetlinker.ui.main_window")


class MainWindow(QMainWindow):
    """GuetLinker main application window.

    Network controls are always available. Self-service authentication is an
    optional account-tab dialog. Closing minimizes to system tray.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Closing the main window must never end the background monitor. This
        # complements QApplication.setQuitOnLastWindowClosed(False) and is
        # especially important for the menu-bar app lifecycle on macOS.
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setMinimumSize(460, 560)
        self.resize(540, 660)

        self._tabs = QTabWidget(self)
        self.setCentralWidget(self._tabs)

        self._status_page = StatusPage(self)
        self._settings_page = SettingsPage(parent=self)
        self._account_page = AccountPage(self)
        self._about_page = AboutPage(self)

        self._tabs.addTab(self._status_page, "状态")
        self._tabs.addTab(self._settings_page, "连接与设置")
        self._tabs.addTab(self._account_page, "账户")
        self._tabs.addTab(self._about_page, "关于")
        self._login_dialog = SelfServiceLoginDialog(self)

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

    # ── Public accessors ──────────────────────────────────────────

    @property
    def login_dialog(self) -> SelfServiceLoginDialog:
        return self._login_dialog

    @property
    def status_page(self) -> StatusPage:
        return self._status_page

    @property
    def settings_page(self) -> SettingsPage:
        return self._settings_page

    @property
    def account_page(self) -> AccountPage:
        return self._account_page

    @property
    def about_page(self) -> AboutPage:
        return self._about_page

    @property
    def status_bar(self) -> QStatusBar:
        return self._status_bar

    # ── Window behaviour ──────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        """Hide the window while keeping background monitoring alive."""
        event.ignore()
        self.hide()
        logger.debug("Window hidden; GuetLinker continues in the system tray")

    def show_and_activate(self) -> None:
        """Show the window and bring it to the front."""
        self.show()
        self.activateWindow()
        self.raise_()
