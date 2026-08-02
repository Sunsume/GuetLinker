"""GuetLinker application controller.

Initializes and wires together all core modules and UI components.
Manages the application lifecycle and signal connections.
"""

from __future__ import annotations

import logging
import argparse

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QObject, QTimer, Slot

from src.core.config import Config
from src.core.logger import setup_logger
from src.core.auth_client import AuthClient
from src.core.self_service_client import (
    AccountOverview,
    SelfServiceClient,
    SelfServiceLoginResult,
    SelfServiceSession,
    TrafficSummary,
)
from src.core.monitor import NetworkMonitor, NetworkStatus
from src.core.portal import PortalSession
from src.core.autostart import AutoStartManager
from src.ui.main_window import MainWindow
from src.ui.tray_icon import TrayIcon

logger = logging.getLogger("guetlinker.app")
LOGIN_RETRY_DELAY_MS = 1500
BACKGROUND_CHECK_INTERVAL_SECONDS = 30


class GuetLinkerApp(QObject):
    """Top-level application controller.

    Initializes all modules and connects signals between them:
        Monitor → AuthClient → UI
    """

    def __init__(self, qt_app: QApplication, args: argparse.Namespace) -> None:
        super().__init__()
        self._qt_app = qt_app
        self._args = args
        self._auto_reconnect_paused = False
        self._login_retry_pending = False
        self._portal_was_online = False
        self._management_authenticated = False

        # ── Core modules ──────────────────────────────────────────
        self._config = Config()
        self._logger = setup_logger(
            logging.DEBUG if args.debug else logging.INFO
        )

        self._auth_client = AuthClient(
            portal_url=self._config.portal_url,
        )
        self._self_service_client = SelfServiceClient()
        self._monitor = NetworkMonitor(
            portal_url=self._config.portal_url,
            check_interval=BACKGROUND_CHECK_INTERVAL_SECONDS,
        )

        # ── UI ────────────────────────────────────────────────────
        self._window = MainWindow()
        self._tray = TrayIcon(self)
        self._tray.show()

        # ── Wire everything up ────────────────────────────────────
        self._connect_signals()

        # ── Apply settings ────────────────────────────────────────
        self._apply_config()

        # ── Show or hide ──────────────────────────────────────────
        if args.minimized:
            logger.info("Starting minimized to tray")
        else:
            self._window.show()

        # ── Start monitoring ──────────────────────────────────────
        # Online detection does not require locally stored credentials. Always
        # start monitoring so sessions created in a browser are reflected in UI.
        self._monitor.start()
        self._window.status_page.add_log("网络监控已启动")
        self._start_isp_refresh(startup=True)

    # ── Signal connections ────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Connect all signals between modules."""

        # Monitor → UI
        self._monitor.status_changed.connect(self._on_status_changed)
        self._monitor.portal_session_changed.connect(
            self._on_portal_session_changed
        )
        self._monitor.check_completed.connect(
            self._window.status_page.update_last_check
        )

        # Monitor → Auth (auto-reconnect)
        self._monitor.reconnect_requested.connect(self._on_reconnect_requested)

        # Auth → UI
        self._auth_client.login_success.connect(self._on_login_success)
        self._auth_client.login_failed.connect(self._on_login_failed)
        self._auth_client.login_started.connect(self._on_login_started)
        self._auth_client.login_cancelled.connect(self._on_login_cancelled)
        self._auth_client.isp_options_loaded.connect(
            self._on_isp_options_loaded
        )
        self._auth_client.isp_options_failed.connect(
            self._on_isp_options_failed
        )

        # Self-service authentication → account-page dialog
        self._self_service_client.login_started.connect(
            lambda: self._window.login_dialog.set_busy(True)
        )
        self._self_service_client.login_succeeded.connect(
            self._on_management_login_success
        )
        self._self_service_client.login_failed.connect(
            self._on_management_login_failed
        )
        self._self_service_client.captcha_required.connect(
            self._on_management_captcha_required
        )
        self._self_service_client.captcha_loaded.connect(
            self._on_management_captcha_loaded
        )
        self._self_service_client.captcha_failed.connect(
            self._on_management_captcha_failed
        )
        self._self_service_client.account_overview_loaded.connect(
            self._on_account_overview_loaded
        )
        self._self_service_client.account_overview_failed.connect(
            self._on_account_overview_failed
        )
        self._self_service_client.traffic_loaded.connect(
            self._on_traffic_loaded
        )
        self._self_service_client.traffic_failed.connect(
            self._on_traffic_failed
        )

        # UI → Actions
        self._window.status_page.connect_button.clicked.connect(self._on_manual_connect)
        self._window.status_page.disconnect_button.clicked.connect(self._on_manual_disconnect)
        self._window.login_dialog.login_requested.connect(
            self._on_management_login_requested
        )
        self._window.login_dialog.captcha_refresh_requested.connect(
            self._on_management_captcha_refresh
        )
        self._window.account_page.switch_account_requested.connect(
            self._on_switch_account
        )
        self._window.account_page.traffic_requested.connect(
            self._on_traffic_requested
        )

        # Settings page
        settings = self._window.settings_page
        settings.settings_saved.connect(self._on_settings_saved)
        settings.refresh_isp_button.clicked.connect(self._on_refresh_isp)

        # Tray actions
        self._tray.show_action.triggered.connect(self._window.show_and_activate)
        self._tray.check_action.triggered.connect(self._monitor.request_check)
        self._tray.connect_action.triggered.connect(self._on_manual_connect)
        self._tray.disconnect_action.triggered.connect(self._on_manual_disconnect)
        self._tray.quit_action.triggered.connect(self._quit)

        # Window close → tray (handled by MainWindow.closeEvent)

    # ── Slot handlers ─────────────────────────────────────────────

    @Slot(object)
    def _on_status_changed(self, status: NetworkStatus) -> None:
        """Handle network status change."""
        self._window.status_page.update_status(status)
        self._tray.update_status(status)

        if status == NetworkStatus.CONNECTED:
            self._window.status_page.add_log("网络已连接")
        elif status == NetworkStatus.DISCONNECTED:
            if self._auto_reconnect_paused:
                self._window.status_page.add_log("校园网已主动断开")
            elif not self._config.auto_reconnect:
                self._window.status_page.add_log(
                    "检测到断网（自动重连未开启）"
                )
                self._show_notification("GuetLinker", "检测到校园网断线")
            else:
                self._window.status_page.add_log("检测到断网")
                self._show_notification("GuetLinker", "检测到断网，正在尝试重连...")
        elif status == NetworkStatus.RECONNECTING:
            self._window.status_page.add_log("正在重连...")
        elif status == NetworkStatus.UNKNOWN:
            self._window.status_page.add_log("网络状态未知")

    @Slot(object)
    def _on_portal_session_changed(self, session: PortalSession) -> None:
        """Show public session details exposed by the current portal page."""
        was_online = self._portal_was_online
        self._portal_was_online = session.is_online
        self._window.status_page.update_portal_session(session)
        self._tray.update_portal_session(session)
        if session.is_online:
            # A new browser-side login is an explicit resume signal.
            self._auto_reconnect_paused = False
            if not was_online and self._monitor.status != NetworkStatus.RECONNECTING:
                account = f"（{session.account_id}）" if session.account_id else ""
                self._window.status_page.add_log(
                    f"检测到校园网已登录{account}"
                )

    @Slot()
    def _on_reconnect_requested(self) -> None:
        """Start one automatic login attempt for a disconnected portal."""
        if self._auto_reconnect_paused or not self._config.auto_reconnect:
            return
        if not self._config.is_account_configured():
            return
        if not self._monitor.begin_reconnect():
            return
        logger.info("Auto-reconnecting...")
        self._window.status_page.add_log("自动重连中...")
        self._do_login()

    @Slot()
    def _on_login_started(self) -> None:
        """Expose cancellation while the background login task is running."""
        self._window.status_page.set_login_in_progress(True)
        self._tray.set_login_in_progress(True)

    @Slot(object)
    def _on_login_success(self, session: PortalSession) -> None:
        """Handle successful login."""
        self._login_retry_pending = False
        self._window.status_page.set_login_in_progress(False)
        self._tray.set_login_in_progress(False)
        self._monitor.finish_reconnect()
        self._monitor.accept_verified_session(session)
        self._window.status_page.add_log("登录成功 ✓")
        self._monitor.request_check()
        self._show_notification("GuetLinker", "校园网登录成功")

    @Slot(str)
    def _on_login_failed(self, message: str) -> None:
        """Handle failed login."""
        self._window.status_page.set_login_in_progress(False)
        self._tray.set_login_in_progress(False)
        self._monitor.cancel_reconnect()
        if self._schedule_login_retry():
            logger.info("Login round incomplete; retry scheduled: %s", message)
            return
        self._window.status_page.add_log(f"登录未成功: {message}")
        self._show_notification("GuetLinker", f"登录未成功: {message}")

    @Slot()
    def _on_login_cancelled(self) -> None:
        """Restore controls immediately after a cancelled login."""
        self._login_retry_pending = False
        self._window.status_page.set_login_in_progress(False)
        self._tray.set_login_in_progress(False)
        self._monitor.cancel_reconnect()
        self._window.status_page.add_log("登录已取消")

    @Slot()
    def _on_manual_connect(self) -> None:
        """Handle manual connect button."""
        if self._auth_client.is_login_in_progress:
            if self._auth_client.cancel_login():
                self._window.status_page.add_log("正在取消登录...")
            return

        if not self._config.is_account_configured():
            self._window.status_page.add_log(
                "请先在连接与设置页填写校园网账号、密码并选择运营商"
            )
            return
        if not self._monitor.begin_reconnect():
            self._window.status_page.add_log("已有连接请求正在进行")
            return

        self._auto_reconnect_paused = False
        self._window.status_page.add_log("手动连接...")
        if not self._monitor.is_running:
            self._monitor.start()
        self._do_login()

    @Slot()
    def _on_manual_disconnect(self) -> None:
        """Confirm and log out the current portal session."""
        choice = QMessageBox.question(
            self._window,
            "确认断开",
            "确定要断开当前校园网连接吗？\n断开后将暂停自动重连。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        self._window.status_page.add_log("正在注销校园网会话...")
        self._monitor.invalidate_pending_probe()
        result = self._auth_client.logout(self._monitor.portal_session)
        if not result.success:
            self._window.status_page.add_log(f"断开失败: {result.message}")
            self._show_notification("GuetLinker", f"断开失败: {result.message}")
            return

        self._monitor.finish_reconnect()
        self._auto_reconnect_paused = True
        self._monitor.mark_disconnected()
        self._window.status_page.add_log(
            "校园网已断开；状态监测继续运行，自动重连已暂停"
        )
        self._show_notification("GuetLinker", "校园网已断开")

    @Slot()
    def _on_settings_saved(self) -> None:
        """Handle settings saved — apply new config and begin monitoring."""
        self._apply_config()
        if self._config.auto_reconnect:
            self._auto_reconnect_paused = False
            self._monitor.request_check()
        if self._config.is_account_configured() and not self._monitor.is_running:
            self._monitor.start()
            self._window.status_page.add_log("监控已启动")

    @Slot(str, str, str)
    def _on_management_login_requested(
        self,
        account: str,
        password: str,
        captcha: str,
    ) -> None:
        """Start one management-site login without blocking or retrying."""
        if not self._self_service_client.start_login(
            account,
            password,
            captcha,
        ):
            self._window.login_dialog.set_error("登录任务正在进行，请稍候")

    @Slot(object)
    def _on_management_login_success(
        self,
        session: SelfServiceSession,
    ) -> None:
        """Update only the management account; network credentials stay separate."""
        self._window.login_dialog.complete_login()
        self._management_authenticated = True
        self._window.account_page.update_session(session)
        self._window.status_bar.showMessage(
            f"自助服务已登录：{session.account}",
            5000,
        )
        self._window.status_page.add_log("自助服务登录成功")
        self._load_account_overview()

    @Slot(str)
    def _on_management_login_failed(self, message: str) -> None:
        self._window.login_dialog.set_busy(False)
        self._window.login_dialog.set_error(message)

    @Slot(object)
    def _on_management_captcha_required(
        self,
        result: SelfServiceLoginResult,
    ) -> None:
        """Reveal the CAPTCHA only when the server requires it."""
        self._window.login_dialog.set_busy(False)
        self._window.login_dialog.show_captcha(
            result.captcha_image,
            result.message,
        )

    @Slot()
    def _on_management_captcha_refresh(self) -> None:
        self._window.login_dialog.set_captcha_loading()
        if not self._self_service_client.refresh_captcha_async():
            self._window.login_dialog.set_captcha_image(b"")
            self._window.login_dialog.set_error("验证码正在加载，请稍候")

    @Slot(bytes)
    def _on_management_captcha_loaded(self, image: bytes) -> None:
        self._window.login_dialog.set_captcha_image(image)

    @Slot(str)
    def _on_management_captcha_failed(self, message: str) -> None:
        self._window.login_dialog.set_captcha_image(b"")
        self._window.login_dialog.set_error(message)

    def _load_account_overview(self) -> None:
        """Load overview first, then traffic, on the single session worker."""
        if not self._management_authenticated:
            return
        self._window.account_page.set_overview_loading()
        if not self._self_service_client.fetch_account_overview_async():
            self._window.account_page.set_overview_error(
                "另一个自助服务请求正在进行，请稍后再试"
            )

    @Slot(object)
    def _on_account_overview_loaded(self, overview: AccountOverview) -> None:
        self._window.account_page.update_overview(overview)
        self._on_traffic_requested(
            *self._window.account_page.current_traffic_range
        )

    @Slot(str)
    def _on_account_overview_failed(self, message: str) -> None:
        if self._expire_management_session_if_needed(message):
            return
        self._window.account_page.set_overview_error(message)
        self._on_traffic_requested(
            *self._window.account_page.current_traffic_range
        )

    @Slot(str, str)
    def _on_traffic_requested(self, start_date: str, end_date: str) -> None:
        """Load the selected range using the authenticated management cookie."""
        if not self._management_authenticated:
            self._window.account_page.clear_session()
            return
        self._window.account_page.set_traffic_loading(True)
        if not self._self_service_client.fetch_traffic_async(
            start_date,
            end_date,
        ):
            self._window.account_page.set_traffic_error(
                "另一个自助服务请求正在进行，请稍后再试"
            )

    @Slot(object)
    def _on_traffic_loaded(self, summary: TrafficSummary) -> None:
        self._window.account_page.update_traffic(summary)

    @Slot(str)
    def _on_traffic_failed(self, message: str) -> None:
        if self._expire_management_session_if_needed(message):
            return
        self._window.account_page.set_traffic_error(message)

    def _expire_management_session_if_needed(self, message: str) -> bool:
        if "登录已过期" not in message:
            return False
        self._management_authenticated = False
        self._self_service_client.reset_session()
        self._window.account_page.clear_session(message)
        return True

    @Slot()
    def _on_switch_account(self) -> None:
        """Open self-service login; switching discards only its local cookie."""
        if self._self_service_client.is_busy:
            self._window.status_bar.showMessage(
                "自助服务请求正在进行，请稍后再试",
                3000,
            )
            return
        if self._management_authenticated:
            self._management_authenticated = False
            self._self_service_client.reset_session()
            self._window.account_page.clear_session()
        self._window.login_dialog.open_for_login(self._config.user_id)

    @Slot()
    def _on_refresh_isp(self) -> None:
        """Handle non-blocking ISP refresh button."""
        self._start_isp_refresh(startup=False)

    @Slot(object)
    def _on_isp_options_loaded(self, options) -> None:
        """Persist a successful dynamic list and validate saved selection."""
        self._window.settings_page.set_isp_refreshing(False)
        self._window.settings_page.set_isp_options(
            options,
            persist=True,
            notify_missing=True,
        )
        self._window.status_page.add_log(f"获取到 {len(options)} 个运营商")

    @Slot(str)
    def _on_isp_options_failed(self, message: str) -> None:
        """Retain cached options when a dynamic refresh fails."""
        self._window.settings_page.set_isp_refreshing(False)
        self._window.status_page.add_log(
            f"运营商列表更新失败，已保留历史列表: {message}"
        )

    # ── Private helpers ───────────────────────────────────────────

    def _do_login(self) -> None:
        """Start login with stored credentials outside the UI thread."""
        # Ignore a portal probe that started before this authentication attempt;
        # its old login-page result must not overwrite a successful login.
        self._monitor.invalidate_pending_probe()
        started = self._auth_client.start_login(
            user_id=self._config.user_id,
            password=self._config.password,
            isp_value=self._config.isp,
        )
        if not started:
            self._monitor.cancel_reconnect()
            self._window.status_page.add_log("登录任务未启动")

    def _start_isp_refresh(self, startup: bool) -> None:
        """Start one background ISP refresh, including once at startup."""
        started = self._auth_client.refresh_isp_options_async()
        if not started:
            if not startup:
                self._window.status_page.add_log("运营商列表正在更新")
            return
        self._window.settings_page.set_isp_refreshing(True)
        self._window.status_page.add_log(
            "启动时更新运营商列表..."
            if startup
            else "正在获取运营商列表..."
        )

    def _schedule_login_retry(self) -> bool:
        """Retry authentication promptly instead of waiting up to 30 seconds."""
        if (
            self._login_retry_pending
            or self._auto_reconnect_paused
            or not self._config.auto_reconnect
            or self._monitor.status != NetworkStatus.DISCONNECTED
        ):
            return False
        self._login_retry_pending = True
        self._window.status_page.add_log(
            "网关尚未就绪，1.5 秒后继续连接"
        )
        QTimer.singleShot(LOGIN_RETRY_DELAY_MS, self._retry_login_after_failure)
        return True

    def _retry_login_after_failure(self) -> None:
        """Start a delayed retry only if the portal still needs authentication."""
        self._login_retry_pending = False
        if (
            self._auto_reconnect_paused
            or self._auth_client.is_login_in_progress
            or self._monitor.status != NetworkStatus.DISCONNECTED
        ):
            return
        self._on_reconnect_requested()

    def _apply_config(self) -> None:
        """Apply current config to all modules."""
        # The 500 ms session poll and 30 s external fallback are internal
        # implementation details, intentionally no longer user-configurable.
        self._monitor.set_interval(BACKGROUND_CHECK_INTERVAL_SECONDS)
        self._tray.update_status(self._monitor.status)

        # Sync auto-start with registry
        if self._config.auto_start:
            AutoStartManager.enable()
        else:
            AutoStartManager.disable()

        # Pass config to settings page for loading
        self._window.settings_page._config = self._config
        self._window.settings_page._auth_client = self._auth_client
        self._window.settings_page._load_settings()

    def _show_notification(self, title: str, message: str) -> None:
        """Show notification based on user preference."""
        self._tray.show_notification(
            title, message, self._config.notification_method
        )

    def _quit(self) -> None:
        """Clean up and quit the application."""
        logger.info("Shutting down GuetLinker")
        self._monitor.close()
        self._auth_client.close()
        self._self_service_client.close()
        self._qt_app.quit()
