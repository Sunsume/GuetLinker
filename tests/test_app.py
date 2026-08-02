"""Controller tests for user-confirmed manual logout."""

from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from src.app import GuetLinkerApp
from src.core.auth_client import LogoutResult
from src.core.monitor import NetworkStatus
from src.core.portal import PortalPageState, PortalSession
from src.core.self_service_client import AccountOverview, SelfServiceSession


class FakeMonitor:
    def __init__(self):
        self.portal_session = PortalSession(state=PortalPageState.ONLINE)
        self.calls = []

    def finish_reconnect(self):
        self.calls.append("finish")

    def invalidate_pending_probe(self):
        self.calls.append("invalidate_probe")

    def stop(self):
        self.calls.append("stop")

    def mark_disconnected(self):
        self.calls.append("mark_disconnected")


def _controller(logout):
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    logs = []
    controller._window = SimpleNamespace(
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._monitor = FakeMonitor()
    controller._auth_client = SimpleNamespace(logout=logout)
    controller._show_notification = lambda *_: None
    return controller, logs


def test_disconnect_confirmation_cancel_sends_no_logout(monkeypatch):
    def unexpected_logout(_):
        raise AssertionError("cancel must not send a logout request")

    controller, logs = _controller(unexpected_logout)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    controller._on_manual_disconnect()

    assert logs == []
    assert controller._monitor.calls == []


def test_confirmed_disconnect_uses_logout_result(monkeypatch):
    logout_sessions = []

    def logout(session):
        logout_sessions.append(session)
        return LogoutResult(True, "校园网已断开")

    controller, logs = _controller(logout)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    controller._on_manual_disconnect()

    assert len(logout_sessions) == 1
    assert controller._monitor.calls == [
        "invalidate_probe",
        "finish",
        "mark_disconnected",
    ]
    assert logs == [
        "正在注销校园网会话...",
        "校园网已断开；状态监测继续运行，自动重连已暂停",
    ]


def test_connect_action_cancels_active_login():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    logs = []
    cancelled = []
    controller._window = SimpleNamespace(
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._auth_client = SimpleNamespace(
        is_login_in_progress=True,
        cancel_login=lambda: cancelled.append(True) or True,
    )

    controller._on_manual_connect()

    assert cancelled == [True]
    assert logs == ["正在取消登录..."]


def test_manual_network_connect_does_not_require_self_service_login():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    controller._management_authenticated = False
    controller._auto_reconnect_paused = True
    logs = []
    login_calls = []
    controller._window = SimpleNamespace(
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._auth_client = SimpleNamespace(is_login_in_progress=False)
    controller._config = SimpleNamespace(is_account_configured=lambda: True)
    controller._monitor = SimpleNamespace(
        begin_reconnect=lambda: True,
        is_running=True,
    )
    controller._do_login = lambda: login_calls.append(True)

    controller._on_manual_connect()

    assert login_calls == [True]
    assert logs == ["手动连接..."]
    assert controller._auto_reconnect_paused is False


def test_startup_requests_async_isp_refresh():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    refresh_calls = []
    refreshing_states = []
    logs = []
    controller._window = SimpleNamespace(
        settings_page=SimpleNamespace(
            set_isp_refreshing=refreshing_states.append,
        ),
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._auth_client = SimpleNamespace(
        refresh_isp_options_async=lambda: refresh_calls.append(True) or True,
    )

    controller._start_isp_refresh(startup=True)

    assert refresh_calls == [True]
    assert refreshing_states == [True]
    assert logs == ["启动时更新运营商列表..."]


def test_failed_login_schedules_prompt_retry(monkeypatch):
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    controller._login_retry_pending = False
    controller._auto_reconnect_paused = False
    logs = []
    callbacks = []
    retries = []
    controller._window = SimpleNamespace(
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._auth_client = SimpleNamespace(is_login_in_progress=False)
    controller._config = SimpleNamespace(auto_reconnect=True)
    controller._monitor = SimpleNamespace(status=NetworkStatus.DISCONNECTED)
    controller._on_reconnect_requested = lambda: retries.append(True)
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        lambda delay, callback: callbacks.append((delay, callback)),
    )

    scheduled = controller._schedule_login_retry()

    assert scheduled is True
    assert controller._login_retry_pending is True
    assert logs == ["网关尚未就绪，1.5 秒后继续连接"]
    assert callbacks[0][0] == 1500

    callbacks[0][1]()

    assert retries == [True]


def test_automatic_reconnect_is_ignored_when_disabled():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    controller._auto_reconnect_paused = False
    controller._config = SimpleNamespace(
        auto_reconnect=False,
        is_account_configured=lambda: True,
    )
    controller._monitor = SimpleNamespace(
        begin_reconnect=lambda: (_ for _ in ()).throw(
            AssertionError("disabled auto reconnect must not start")
        ),
    )

    controller._on_reconnect_requested()


def test_management_login_does_not_overwrite_network_credentials():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    completed = []
    account_sessions = []
    logs = []
    overview_requests = []
    config = SimpleNamespace(user_id="network-id", password="network-password")
    controller._config = config
    controller._management_authenticated = False
    controller._window = SimpleNamespace(
        login_dialog=SimpleNamespace(
            complete_login=lambda: completed.append(True),
        ),
        account_page=SimpleNamespace(
            update_session=account_sessions.append,
        ),
        status_bar=SimpleNamespace(showMessage=lambda *args: None),
        status_page=SimpleNamespace(add_log=logs.append),
    )
    controller._load_account_overview = lambda: overview_requests.append(True)
    session = SelfServiceSession(account="management-id")

    controller._on_management_login_success(session)

    assert completed == [True]
    assert account_sessions == [session]
    assert controller._management_authenticated is True
    assert config.user_id == "network-id"
    assert config.password == "network-password"
    assert overview_requests == [True]


def test_account_overview_completion_starts_default_traffic_query():
    controller = GuetLinkerApp.__new__(GuetLinkerApp)
    displayed = []
    traffic_requests = []
    controller._window = SimpleNamespace(
        account_page=SimpleNamespace(
            update_overview=displayed.append,
            current_traffic_range=("2026-08-01", "2026-08-02"),
        )
    )
    controller._on_traffic_requested = (
        lambda *args: traffic_requests.append(args)
    )
    overview = AccountOverview("正常", "暂无异常信息")

    controller._on_account_overview_loaded(overview)

    assert displayed == [overview]
    assert traffic_requests == [("2026-08-01", "2026-08-02")]
