"""Asynchronous client for the GUET self-service management system.

The self-service site is separate from the Dr.COM network portal.  It uses a
session-bound HTML form, MD5s the password in browser JavaScript, and may ask
for a CAPTCHA after failed attempts.  This module mirrors that single-submit
flow without ever blocking the Qt UI thread.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from PySide6.QtCore import QObject, Signal, Slot

logger = logging.getLogger("guetlinker.self_service")

SELF_SERVICE_URL = "https://nicdrcom.guet.edu.cn/Self/"


@dataclass(frozen=True)
class SelfServiceLoginPage:
    """Current session-bound login form state."""

    action_url: str
    checkcode: str
    captcha_required: bool
    error_message: str = ""


@dataclass(frozen=True)
class SelfServiceSession:
    """Authenticated management-session information safe to expose to UI."""

    account: str
    display_name: str = ""
    landing_url: str = ""


@dataclass(frozen=True)
class SelfServiceLoginResult:
    """Result of exactly one user-requested authentication submission."""

    success: bool
    message: str = ""
    captcha_required: bool = False
    captcha_image: bytes = b""
    session: SelfServiceSession | None = None


@dataclass(frozen=True)
class AccountOverview:
    """Non-sensitive account facts exposed by the management pages."""

    status: str
    anomaly_info: str


@dataclass(frozen=True)
class TrafficSummary:
    """Traffic totals returned by ``bill/getUserOnlineLog`` in MB."""

    start_date: str
    end_date: str
    international_up_mb: float
    international_down_mb: float
    domestic_up_mb: float
    domestic_down_mb: float


class SelfServiceClient(QObject):
    """GUET self-service authentication client.

    A login click maps to at most one POST.  In particular, credential errors
    are never retried automatically because repeated failures can trigger a
    CAPTCHA or server-side lockout.
    """

    login_started = Signal()
    login_succeeded = Signal(object)  # SelfServiceSession
    login_failed = Signal(str)
    captcha_required = Signal(object)  # SelfServiceLoginResult
    captcha_loaded = Signal(bytes)
    captcha_failed = Signal(str)
    account_overview_loaded = Signal(object)  # AccountOverview
    account_overview_failed = Signal(str)
    traffic_loaded = Signal(object)  # TrafficSummary
    traffic_failed = Signal(str)
    _login_finished = Signal(object)
    _captcha_finished = Signal(object)
    _account_overview_finished = Signal(object)
    _traffic_finished = Signal(object)

    def __init__(
        self,
        base_url: str = SELF_SERVICE_URL,
        *,
        timeout: float = 8.0,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self._owns_client = client is None
        self._client = client or self._make_client()
        self._pending_page: SelfServiceLoginPage | None = None
        self._pending_account = ""
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="guetlinker-self-service",
        )
        self._future: Future | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._login_finished.connect(self._on_login_finished)
        self._captcha_finished.connect(self._on_captcha_finished)
        self._account_overview_finished.connect(
            self._on_account_overview_finished
        )
        self._traffic_finished.connect(self._on_traffic_finished)

    def _make_client(self) -> httpx.Client:
        return httpx.Client(
            verify=False,
            follow_redirects=True,
            trust_env=False,
            timeout=self.timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
                "Cache-Control": "no-cache",
            },
        )

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._future is not None

    def start_login(self, account: str, password: str, captcha: str = "") -> bool:
        """Submit one asynchronous login operation."""
        with self._lock:
            if self._closed or self._future is not None:
                return False
            future = self._executor.submit(
                self.login,
                account.strip(),
                password,
                captcha.strip(),
            )
            self._future = future
        future.add_done_callback(self._forward_login_result)
        self.login_started.emit()
        return True

    def login(
        self,
        account: str,
        password: str,
        captcha: str = "",
    ) -> SelfServiceLoginResult:
        """Synchronously perform one login submission for protocol tests."""
        if not account or not password:
            return SelfServiceLoginResult(False, "请输入学号和密码")

        try:
            page = self._pending_page
            if page is None or self._pending_account != account:
                page = self._fetch_login_page()
                self._pending_page = page
                self._pending_account = account

            if page.captcha_required and not captcha:
                return self._captcha_result(page, "请输入验证码")

            payload = {
                # These are deliberate honeypot fields on the real page.
                "foo": "",
                "bar": "",
                "checkcode": page.checkcode,
                "account": account,
                "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
                "code": captcha,
                "submit": "",
            }
            response = self._client.post(page.action_url, data=payload)
            response.raise_for_status()

            if self._is_authenticated_response(response):
                self._pending_page = None
                self._pending_account = ""
                session = SelfServiceSession(
                    account=account,
                    display_name=self._parse_display_name(response.text, account),
                    landing_url=str(response.url),
                )
                logger.info("Self-service login succeeded for account %s", account)
                return SelfServiceLoginResult(
                    True,
                    "自助服务登录成功",
                    session=session,
                )

            page = self.parse_login_page(response.text, str(response.url))
            self._pending_page = page
            self._pending_account = account
            message = page.error_message or "账号、密码或验证码不正确"
            if page.captcha_required:
                return self._captcha_result(page, message)
            return SelfServiceLoginResult(False, message)
        except httpx.TimeoutException:
            return SelfServiceLoginResult(False, "自助服务系统响应超时，请稍后重试")
        except httpx.HTTPError as exc:
            logger.warning("Self-service login request failed: %s", exc)
            return SelfServiceLoginResult(False, "无法连接校园网自助服务系统")
        except ValueError as exc:
            logger.warning("Unable to parse self-service login page: %s", exc)
            return SelfServiceLoginResult(False, str(exc))

    def refresh_captcha_async(self) -> bool:
        """Refresh the current session's CAPTCHA without submitting credentials."""
        with self._lock:
            if self._closed or self._future is not None:
                return False
            future = self._executor.submit(self._fetch_captcha)
            self._future = future
        future.add_done_callback(self._forward_captcha_result)
        return True

    def fetch_traffic_async(self, start_date: str, end_date: str) -> bool:
        """Load one date range using the authenticated management session."""
        with self._lock:
            if self._closed or self._future is not None:
                return False
            future = self._executor.submit(
                self.fetch_traffic,
                start_date,
                end_date,
            )
            self._future = future
        future.add_done_callback(self._forward_traffic_result)
        return True

    def fetch_account_overview_async(self) -> bool:
        """Load account status and anomaly notes with the current cookie."""
        with self._lock:
            if self._closed or self._future is not None:
                return False
            future = self._executor.submit(self.fetch_account_overview)
            self._future = future
        future.add_done_callback(self._forward_account_overview_result)
        return True

    def fetch_account_overview(self) -> AccountOverview:
        """Read only the status and wiring-data fields from management HTML."""
        dashboard = self._client.get(urljoin(self.base_url, "dashboard"))
        dashboard.raise_for_status()
        self._raise_if_login_expired(dashboard)

        person_list = self._client.get(
            urljoin(self.base_url, "setting/personList")
        )
        person_list.raise_for_status()
        self._raise_if_login_expired(person_list)

        return AccountOverview(
            status=self.parse_account_status(dashboard.text),
            anomaly_info=self.parse_anomaly_info(person_list.text),
        )

    def fetch_traffic(self, start_date: str, end_date: str) -> TrafficSummary:
        """Synchronously query the summary for tests and background execution."""
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError as exc:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from exc
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        if (end - start).days > 60:
            raise ValueError("查询时间范围不能超过 60 天")

        response = self._client.get(
            urljoin(self.base_url, "bill/getUserOnlineLog"),
            params={
                "pageSize": "10",
                "pageNumber": "1",
                "sortName": "loginTime",
                "sortOrder": "DESC",
                "startTime": start_date,
                "endTime": end_date,
            },
        )
        response.raise_for_status()
        self._raise_if_login_expired(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("上网记录接口返回了无法识别的数据") from exc
        if not isinstance(payload, dict):
            raise ValueError("上网记录中没有流量汇总数据")
        summary = payload.get("summary")
        if summary is None and not payload.get("rows") and not payload.get("total"):
            summary = {}
        if not isinstance(summary, dict):
            raise ValueError("上网记录中没有流量汇总数据")
        return TrafficSummary(
            start_date=start_date,
            end_date=end_date,
            international_up_mb=self._summary_number(summary, "INTERNETUPFLOW"),
            international_down_mb=self._summary_number(
                summary,
                "INTERNETDOWNFLOW",
            ),
            domestic_up_mb=self._summary_number(summary, "CHINANETUPFLOW"),
            domestic_down_mb=self._summary_number(summary, "CHINANETDOWNFLOW"),
        )

    @staticmethod
    def _raise_if_login_expired(response: httpx.Response) -> None:
        if "/login" in urlsplit(str(response.url)).path.lower():
            raise ValueError("自助服务登录已过期，请切换账号后重新登录")

    @staticmethod
    def parse_account_status(html: str) -> str:
        """Extract the visible status row without reading embedded user JSON."""
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select(".row"):
            label = row.find("label")
            if label is None:
                continue
            key = re.sub(r"[\s　:：]", "", label.get_text(" ", strip=True))
            if key != "状态":
                continue
            value = row.select_one("span.label") or row.find("span")
            text = value.get_text(" ", strip=True) if value else ""
            if text:
                return text
        raise ValueError("账户状态页面格式已变化")

    @staticmethod
    def parse_anomaly_info(html: str) -> str:
        """Extract only personList's wiring-data field."""
        soup = BeautifulSoup(html, "html.parser")
        field = soup.select_one('input[name="userCompany"]')
        if field is None:
            raise ValueError("账号异常信息页面格式已变化")
        value = str(field.get("value") or "").strip()
        if not value or value.upper() == "N/A":
            return "暂无异常信息"
        return value

    @staticmethod
    def _summary_number(summary: dict, key: str) -> float:
        value = summary.get(key, 0)
        try:
            return float(value or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"流量字段 {key} 格式无效") from exc

    def reset_session(self) -> None:
        """Forget local management authentication when switching accounts."""
        with self._lock:
            if self._future is not None:
                return
            old_client = self._client
            if self._owns_client:
                self._client = self._make_client()
            self._pending_page = None
            self._pending_account = ""
        if self._owns_client:
            old_client.close()

    def _fetch_login_page(self) -> SelfServiceLoginPage:
        response = self._client.get(urljoin(self.base_url, "login/"))
        response.raise_for_status()
        return self.parse_login_page(response.text, str(response.url))

    def _captcha_result(
        self,
        page: SelfServiceLoginPage,
        message: str,
    ) -> SelfServiceLoginResult:
        try:
            image = self._fetch_captcha()
        except httpx.HTTPError as exc:
            logger.warning("CAPTCHA image request failed: %s", exc)
            image = b""
            message = f"{message}；验证码图片加载失败，请刷新"
        return SelfServiceLoginResult(
            False,
            message,
            captcha_required=True,
            captcha_image=image,
        )

    def _fetch_captcha(self) -> bytes:
        response = self._client.get(
            urljoin(self.base_url, "login/randomCode"),
            params={"t": f"{time.time():.6f}"},
        )
        response.raise_for_status()
        return response.content

    @staticmethod
    def parse_login_page(html: str, page_url: str) -> SelfServiceLoginPage:
        """Parse the session URL, anti-bot field, error, and CAPTCHA state."""
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if form is None:
            raise ValueError("自助服务登录页格式已变化")

        action = str(form.get("action") or "").strip()
        action_url = urljoin(page_url, action)
        checkcode_input = form.find("input", attrs={"name": "checkcode"})
        checkcode = (
            str(checkcode_input.get("value") or "").strip()
            if checkcode_input
            else ""
        )

        random_div = soup.select_one("#randomDiv")
        classes = set(random_div.get("class", [])) if random_div else set()
        captcha_required = bool(random_div and "hide" not in classes)
        error_message = SelfServiceClient._parse_error_message(soup, html)
        if "验证码" in error_message:
            captcha_required = True

        return SelfServiceLoginPage(
            action_url=action_url,
            checkcode=checkcode,
            captcha_required=captcha_required,
            error_message=error_message,
        )

    @staticmethod
    def _parse_error_message(soup: BeautifulSoup, html: str) -> str:
        error_box = soup.select_one("#errorTip")
        if error_box:
            direct = error_box.get_text(" ", strip=True)
            if direct:
                return direct

        # The current site injects the server error through: })('message');
        # Restrict the search to the error-tip script so another IIFE cannot be
        # mistaken for the authentication error.
        message = ""
        for script in soup.find_all("script"):
            script_text = script.get_text("\n")
            if "#errorTip" not in script_text:
                continue
            matches = list(
                re.finditer(
                    r"\}\)\(\s*(['\"])(?P<message>.*?)\1\s*\)\s*;",
                    script_text,
                    flags=re.DOTALL,
                )
            )
            if matches:
                message = unescape(matches[-1].group("message")).strip()
                break
        if not message:
            return ""
        return (
            message.replace(r"\'", "'")
            .replace(r"\"", '"')
            .replace(r"\n", " ")
        )

    @staticmethod
    def _is_authenticated_response(response: httpx.Response) -> bool:
        path = urlsplit(str(response.url)).path.lower().rstrip("/")
        soup = BeautifulSoup(response.text, "html.parser")
        login_form = soup.find(
            "form",
            action=re.compile(r"/login/verify", re.IGNORECASE),
        )
        return response.is_success and "/login" not in path and login_form is None

    @staticmethod
    def _parse_display_name(html: str, account: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for selector in (
            ".user-name",
            ".username",
            "#userName",
            ".navbar-text",
            "[data-user-name]",
        ):
            element = soup.select_one(selector)
            if not element:
                continue
            value = element.get_text(" ", strip=True)
            if value and value != account and len(value) <= 40:
                return value

        text = soup.get_text(" ", strip=True)
        match = re.search(r"欢迎(?:您|回来)?[，,:：\s]+([^\s，,]{1,20})", text)
        return match.group(1) if match else ""

    def _forward_login_result(
        self,
        future: Future[SelfServiceLoginResult],
    ) -> None:
        try:
            result = future.result()
        except Exception as exc:
            logger.exception("Self-service background login failed")
            result = SelfServiceLoginResult(False, f"登录任务异常: {exc}")
        self._finish_future(future)
        if not self._closed:
            self._login_finished.emit(result)

    def _forward_captcha_result(self, future: Future[bytes]) -> None:
        try:
            payload: object = future.result()
        except Exception as exc:
            logger.warning("CAPTCHA refresh failed: %s", exc)
            payload = exc
        self._finish_future(future)
        if not self._closed:
            self._captcha_finished.emit(payload)

    def _forward_traffic_result(self, future: Future[TrafficSummary]) -> None:
        try:
            payload: object = future.result()
        except Exception as exc:
            logger.warning("Traffic summary request failed: %s", exc)
            payload = exc
        self._finish_future(future)
        if not self._closed:
            self._traffic_finished.emit(payload)

    def _forward_account_overview_result(
        self,
        future: Future[AccountOverview],
    ) -> None:
        try:
            payload: object = future.result()
        except Exception as exc:
            logger.warning("Account overview request failed: %s", exc)
            payload = exc
        self._finish_future(future)
        if not self._closed:
            self._account_overview_finished.emit(payload)

    def _finish_future(self, future: Future) -> None:
        with self._lock:
            if self._future is future:
                self._future = None

    @Slot(object)
    def _on_login_finished(self, result: SelfServiceLoginResult) -> None:
        if result.success and result.session:
            self.login_succeeded.emit(result.session)
        elif result.captcha_required:
            self.captcha_required.emit(result)
        else:
            self.login_failed.emit(result.message)

    @Slot(object)
    def _on_captcha_finished(self, payload: object) -> None:
        if isinstance(payload, bytes):
            self.captcha_loaded.emit(payload)
        else:
            self.captcha_failed.emit("验证码图片加载失败，请重试")

    @Slot(object)
    def _on_traffic_finished(self, payload: object) -> None:
        if isinstance(payload, TrafficSummary):
            self.traffic_loaded.emit(payload)
        elif isinstance(payload, ValueError):
            self.traffic_failed.emit(str(payload))
        else:
            self.traffic_failed.emit("上网记录加载失败，请稍后重试")

    @Slot(object)
    def _on_account_overview_finished(self, payload: object) -> None:
        if isinstance(payload, AccountOverview):
            self.account_overview_loaded.emit(payload)
        elif isinstance(payload, ValueError):
            self.account_overview_failed.emit(str(payload))
        else:
            self.account_overview_failed.emit(
                "账户状态与异常信息加载失败，请稍后重试"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._owns_client:
            self._client.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
