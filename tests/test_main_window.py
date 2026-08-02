"""UI tests for tabs, account state, and the self-service dialog."""

from PySide6.QtCore import QDate

from src.core.self_service_client import (
    AccountOverview,
    SelfServiceSession,
    TrafficSummary,
)
from src.ui.account_page import format_traffic_size
from src.ui.main_window import MainWindow


def test_main_window_starts_on_tabs_with_self_service_logged_out(qapp):
    window = MainWindow()

    assert window._tabs.currentWidget() is window.status_page
    assert window.account_page.is_authenticated is False
    assert window.account_page._account_label.text() == "学号：-"
    assert window.account_page._name_label.text() == "用户：-"
    assert window.account_page._account_status_label.text() == "状态：-"
    assert window.account_page._anomaly_label.text() == "-"
    assert window.account_page._account_action_button.text() == "登录"
    assert window.account_page._traffic_refresh.isEnabled() is False


def test_login_dialog_requires_visible_captcha_value(qapp):
    window = MainWindow()
    dialog = window.login_dialog
    submissions = []
    dialog.login_requested.connect(lambda *args: submissions.append(args))
    dialog.open_for_login("20240001")
    dialog._password_input.setText("secret")
    dialog.show_captcha()

    dialog._submit()

    assert submissions == []
    assert dialog._error_label.text() == "请输入验证码"


def test_account_page_displays_only_four_flows(qapp):
    window = MainWindow()
    page = window.account_page
    page.update_session(SelfServiceSession(account="20240001"))

    page.update_traffic(
        TrafficSummary(
            start_date="2026-07-01",
            end_date="2026-07-31",
            international_up_mb=1285.84,
            international_down_mb=9660.167,
            domestic_up_mb=15.466,
            domestic_down_mb=384.938,
        )
    )

    assert page._traffic_values["international_up"].text() == "1.26 GB"
    assert page._traffic_values["international_down"].text() == "9.43 GB"
    assert page._traffic_values["domestic_up"].text() == "15.47 MB"
    assert page._traffic_values["domestic_down"].text() == "384.94 MB"
    assert "total" not in page._traffic_values
    assert "1,285.840 MB" in page._traffic_values["international_up"].toolTip()


def test_account_page_displays_status_and_anomaly_information(qapp):
    window = MainWindow()
    page = window.account_page
    page.update_session(SelfServiceSession(account="20240001"))

    page.update_overview(
        AccountOverview(status="正常", anomaly_info="暂无异常信息")
    )

    assert page._account_status_label.text() == "状态：正常"
    assert page._anomaly_label.text() == "暂无异常信息"


def test_traffic_size_uses_readable_binary_units():
    assert format_traffic_size(2 * 1024 * 1024) == "2 TB"
    assert format_traffic_size(1536) == "1.5 GB"
    assert format_traffic_size(12.5) == "12.5 MB"
    assert format_traffic_size(0.5) == "512 KB"
    assert format_traffic_size(0) == "0 KB"


def test_account_page_rejects_date_range_over_sixty_days(qapp):
    window = MainWindow()
    page = window.account_page
    page.update_session(SelfServiceSession(account="20240001"))
    requests = []
    page.traffic_requested.connect(lambda *args: requests.append(args))
    page._start_date.setDate(QDate(2026, 1, 1))
    page._end_date.setMaximumDate(QDate(2026, 12, 31))
    page._end_date.setDate(QDate(2026, 4, 1))

    page._request_traffic()

    assert requests == []
    assert "60 天" in page._traffic_state.text()
