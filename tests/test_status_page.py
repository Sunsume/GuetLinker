"""Tests for status-page session display and action states."""

from src.core.monitor import NetworkStatus
from src.core.portal import PortalPageState, PortalSession
from src.ui.status_page import StatusPage


def test_online_portal_session_displays_login_details(qapp):
    page = StatusPage()
    session = PortalSession(
        state=PortalPageState.ONLINE,
        user_id="20240001@cmcc",
        ipv4="192.0.2.10",
        ipv6="2001:db8::1",
    )

    page.update_portal_session(session)
    page.update_status(NetworkStatus.CONNECTED)

    assert page._status_label.text() == "校园网已登录"
    assert page._account_label.text() == "当前账号: 20240001"
    assert page._operator_label.text() == "接入运营商: 中国移动"
    assert page._ip_label.text() == "IPv4 地址: 192.0.2.10"
    assert page._ipv6_label.text() == "IPv6 地址: 2001:db8::1"
    assert page.connect_button.isEnabled() is False
    assert page.disconnect_button.isEnabled() is True


def test_external_connection_without_portal_session_cannot_logout(qapp):
    page = StatusPage()

    page.update_status(NetworkStatus.CONNECTED)

    assert page._status_label.text() == "已连接"
    assert page._account_label.text() == "当前账号: --"
    assert page._operator_label.text() == "接入运营商: --"
    assert page.connect_button.isEnabled() is False
    assert page.disconnect_button.isEnabled() is False


def test_reconnecting_exposes_cancel_action(qapp):
    page = StatusPage()
    page.update_status(NetworkStatus.RECONNECTING)

    page.set_login_in_progress(True)

    assert page.connect_button.text() == "取消连接"
    assert page.connect_button.isEnabled() is True
    assert page.disconnect_button.isEnabled() is False

    page.set_login_in_progress(False)
    assert page.connect_button.text() == "连接"
