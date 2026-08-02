"""Authenticated self-service account overview."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.self_service_client import (
    AccountOverview,
    SelfServiceSession,
    TrafficSummary,
)


def format_traffic_size(megabytes: float) -> str:
    """Format an MB value with the most readable binary traffic unit."""
    value_mb = max(0.0, float(megabytes))
    if value_mb >= 1024 * 1024:
        value, unit = value_mb / (1024 * 1024), "TB"
    elif value_mb >= 1024:
        value, unit = value_mb / 1024, "GB"
    elif value_mb >= 1:
        value, unit = value_mb, "MB"
    else:
        value, unit = value_mb * 1024, "KB"
    number = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{number} {unit}"


class AccountPage(QScrollArea):
    """Shows the management-session boundary before more fields are integrated."""

    switch_account_requested = Signal()
    traffic_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._authenticated = False
        self._setup_ui()
        self.clear_session()

    def _setup_ui(self) -> None:
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget(self)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("自助服务账户")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(10)

        self._state_label = QLabel("● 未登录")
        card_layout.addWidget(self._state_label)

        self._account_label = QLabel("学号：--")
        card_layout.addWidget(self._account_label)

        self._name_label = QLabel("用户：--")
        card_layout.addWidget(self._name_label)

        self._account_status_label = QLabel("状态：-")
        card_layout.addWidget(self._account_status_label)

        anomaly_title = QLabel("近期/历史账号异常信息")
        anomaly_title.setStyleSheet("font-weight: 600; margin-top: 4px;")
        card_layout.addWidget(anomaly_title)

        self._anomaly_label = QLabel("-")
        self._anomaly_label.setWordWrap(True)
        self._anomaly_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._anomaly_label.setStyleSheet(
            "color: #475569; background: #f8fafc; border: 1px solid #e2e8f0; "
            "border-radius: 6px; padding: 8px;"
        )
        card_layout.addWidget(self._anomaly_label)

        explanation = QLabel(
            "管理系统与校园网网关是两套独立会话。这里登录成功不代表网络已经"
            "连接；网络在线状态仍以状态页的实时检测为准。"
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #64748b;")
        card_layout.addWidget(explanation)
        layout.addWidget(card)

        traffic_card = QFrame()
        traffic_card.setFrameShape(QFrame.Shape.StyledPanel)
        traffic_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        traffic_layout = QVBoxLayout(traffic_card)
        traffic_layout.setContentsMargins(20, 18, 20, 18)
        traffic_layout.setSpacing(12)

        traffic_title = QLabel("上网流量")
        traffic_title.setStyleSheet("font-size: 16px; font-weight: 650;")
        traffic_layout.addWidget(traffic_title)

        date_form = QGridLayout()
        date_form.setHorizontalSpacing(8)
        date_form.setVerticalSpacing(8)
        date_form.addWidget(QLabel("开始日期"), 0, 0)
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        date_form.addWidget(self._start_date, 0, 1)
        date_form.addWidget(QLabel("结束日期"), 1, 0)
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        date_form.addWidget(self._end_date, 1, 1)
        self._traffic_refresh = QPushButton("查询")
        self._traffic_refresh.clicked.connect(self._request_traffic)
        self._traffic_refresh.setMinimumWidth(66)
        date_form.addWidget(self._traffic_refresh, 0, 2, 2, 1)
        date_form.setColumnStretch(1, 1)
        traffic_layout.addLayout(date_form)

        today = QDate.currentDate()
        first_day = QDate(today.year(), today.month(), 1)
        self._start_date.setMaximumDate(today)
        self._end_date.setMaximumDate(today)
        self._start_date.setDate(first_day)
        self._end_date.setDate(today)

        metrics = QGridLayout()
        metrics.setSpacing(8)
        metrics.setColumnStretch(0, 1)
        metrics.setColumnStretch(1, 1)
        self._traffic_values: dict[str, QLabel] = {}
        items = (
            ("international_up", "国际上行"),
            ("international_down", "国际下行"),
            ("domestic_up", "国内上行"),
            ("domestic_down", "国内下行"),
        )
        for index, (key, title_text) in enumerate(items):
            metric = QFrame()
            metric.setMinimumWidth(0)
            metric.setMinimumHeight(78)
            metric.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            metric.setStyleSheet(
                "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; "
                "border-radius: 7px; }"
            )
            metric_layout = QVBoxLayout(metric)
            metric_layout.setContentsMargins(12, 10, 12, 10)
            name = QLabel(title_text)
            name.setMinimumWidth(0)
            name.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            name.setStyleSheet("border: none; color: #64748b;")
            name.setMinimumHeight(18)
            value = QLabel("--")
            value.setMinimumWidth(0)
            value.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            value.setMinimumHeight(26)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            value.setStyleSheet(
                "border: none; color: #0f172a; font-size: 16px; "
                "font-weight: 650;"
            )
            metric_layout.addWidget(name)
            metric_layout.addWidget(value)
            self._traffic_values[key] = value
            metrics.addWidget(metric, index // 2, index % 2)
        traffic_layout.addLayout(metrics)

        self._traffic_state = QLabel("默认查询本月第一天至今天")
        self._traffic_state.setWordWrap(True)
        self._traffic_state.setStyleSheet("color: #64748b; font-size: 12px;")
        traffic_layout.addWidget(self._traffic_state)
        layout.addWidget(traffic_card)

        self._account_action_button = QPushButton("登录")
        self._account_action_button.setMinimumHeight(38)
        self._account_action_button.clicked.connect(
            self.switch_account_requested.emit
        )
        layout.addWidget(self._account_action_button)
        layout.addStretch()

    def update_session(self, session: SelfServiceSession) -> None:
        self._authenticated = True
        self._state_label.setText("● 已登录管理系统")
        self._state_label.setStyleSheet(
            "color: #16a34a; font-size: 15px; font-weight: 600;"
        )
        self._account_label.setText(f"学号：{session.account}")
        self._name_label.setText(f"用户：{session.display_name or session.account}")
        self.set_overview_loading()
        self._account_action_button.setText("切换账号")
        self._start_date.setEnabled(True)
        self._end_date.setEnabled(True)
        self._traffic_refresh.setEnabled(True)
        for value in self._traffic_values.values():
            value.setText("--")
        self._traffic_state.setStyleSheet("color: #64748b; font-size: 12px;")
        self._traffic_state.setText("默认查询本月第一天至今天")

    def clear_session(self, message: str = "登录自助服务后显示上网流量") -> None:
        self._authenticated = False
        self._state_label.setText("● 未登录")
        self._state_label.setStyleSheet(
            "color: #94a3b8; font-size: 15px; font-weight: 600;"
        )
        self._account_label.setText("学号：-")
        self._name_label.setText("用户：-")
        self._account_status_label.setText("状态：-")
        self._account_status_label.setStyleSheet("")
        self._anomaly_label.setText("-")
        self._account_action_button.setText("登录")
        self._start_date.setEnabled(False)
        self._end_date.setEnabled(False)
        self._traffic_refresh.setEnabled(False)
        self._traffic_refresh.setText("查询")
        for value in self._traffic_values.values():
            value.setText("-")
        self._traffic_state.setStyleSheet("color: #64748b; font-size: 12px;")
        self._traffic_state.setText(message)

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def current_traffic_range(self) -> tuple[str, str]:
        return (
            self._start_date.date().toString("yyyy-MM-dd"),
            self._end_date.date().toString("yyyy-MM-dd"),
        )

    def set_traffic_loading(self, loading: bool) -> None:
        self._traffic_refresh.setEnabled(self._authenticated and not loading)
        self._traffic_refresh.setText("查询中" if loading else "查询")
        self._start_date.setEnabled(self._authenticated and not loading)
        self._end_date.setEnabled(self._authenticated and not loading)
        if loading:
            self._traffic_state.setStyleSheet(
                "color: #64748b; font-size: 12px;"
            )
            self._traffic_state.setText("正在读取上网记录汇总...")

    def set_overview_loading(self) -> None:
        self._account_status_label.setText("状态：加载中...")
        self._account_status_label.setStyleSheet("color: #64748b;")
        self._anomaly_label.setText("加载中...")

    def update_overview(self, overview: AccountOverview) -> None:
        self._account_status_label.setText(f"状态：{overview.status}")
        status_color = "#16a34a" if overview.status == "正常" else "#d97706"
        self._account_status_label.setStyleSheet(
            f"color: {status_color}; font-weight: 600;"
        )
        self._anomaly_label.setText(
            overview.anomaly_info or "暂无异常信息"
        )

    def set_overview_error(self, message: str) -> None:
        self._account_status_label.setText("状态：加载失败")
        self._account_status_label.setStyleSheet("color: #dc2626;")
        self._anomaly_label.setText(message)

    def update_traffic(self, summary: TrafficSummary) -> None:
        values = {
            "international_up": summary.international_up_mb,
            "international_down": summary.international_down_mb,
            "domestic_up": summary.domestic_up_mb,
            "domestic_down": summary.domestic_down_mb,
        }
        for key, value in values.items():
            label = self._traffic_values[key]
            label.setText(format_traffic_size(value))
            label.setToolTip(f"原始值：{value:,.3f} MB")
        self.set_traffic_loading(False)
        self._traffic_state.setStyleSheet("color: #16a34a; font-size: 12px;")
        self._traffic_state.setText(
            f"已更新：{summary.start_date} 至 {summary.end_date}"
        )

    def set_traffic_error(self, message: str) -> None:
        self.set_traffic_loading(False)
        self._traffic_state.setStyleSheet("color: #dc2626; font-size: 12px;")
        self._traffic_state.setText(message)

    def _request_traffic(self) -> None:
        if not self._authenticated:
            return
        start = self._start_date.date()
        end = self._end_date.date()
        if start > end:
            self.set_traffic_error("开始日期不能晚于结束日期")
            return
        if start.daysTo(end) > 60:
            self.set_traffic_error("查询时间范围不能超过 60 天")
            return
        self.traffic_requested.emit(*self.current_traffic_range)
