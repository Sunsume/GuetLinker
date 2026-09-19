"""Tests for status-page session display and action states."""

import src.ui.status_page as status_page_module
from src.core.monitor import NetworkStatus
from src.core.network_speed import NetworkSpeed
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


def test_status_page_displays_live_download_and_upload_speed(qapp):
    page = StatusPage()

    page.update_network_speed(
        NetworkSpeed(download_bps=2.5 * 1024 * 1024, upload_bps=12.5 * 1024)
    )

    assert page._download_speed_label.text() == "↓ 下载: 2.50 MB/s"
    assert page._upload_speed_label.text() == "↑ 上传: 12.5 KB/s"


def test_status_page_copies_diagnostic_log(monkeypatch, qapp):
    page = StatusPage()
    monkeypatch.setattr(
        status_page_module,
        "read_recent_log",
        lambda: "AUTH_DIAG result=0 ret_code=1",
    )

    page.copy_diagnostic_log()

    assert qapp.clipboard().text() == "AUTH_DIAG result=0 ret_code=1"
    assert page._log_list.item(0).text().endswith("诊断日志已复制到剪贴板")
    assert page._copy_log_btn.text() == "复制诊断日志"
    assert page._open_log_btn.text() == "打开日志目录"
