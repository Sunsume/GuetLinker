"""GuetLinker authentication client.

Dynamically parses the campus network portal login page and submits
credentials via HTTP POST. Supports self-signed certificates and
multiple fallback parsing strategies.
"""

from __future__ import annotations

import base64
import json
import re
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Optional
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from PySide6.QtCore import QObject, Signal, Slot

from src.core.network_addresses import find_local_ipv6
from src.core.portal import PortalPageState, PortalSession, parse_portal_page

logger = logging.getLogger("guetlinker.auth")


# ── Data classes ──────────────────────────────────────────────────


@dataclass
class ISPInfo:
    """An ISP option from the login page."""

    value: str
    label: str
    suffix: str = ""


@dataclass
class ParsedForm:
    """Parsed login form structure."""

    action_url: str = ""
    method: str = "POST"
    username_field: str = ""
    password_field: str = ""
    isp_field: str = ""
    isp_options: list[ISPInfo] = field(default_factory=list)
    default_isp_value: str = ""
    hidden_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class LoginResult:
    """Result of a login attempt."""

    success: bool
    message: str = ""
    response_text: str = ""
    cancelled: bool = False
    portal_session: PortalSession | None = None


@dataclass
class LogoutResult:
    """Result of a portal logout attempt."""

    success: bool
    message: str = ""


# ── Common field name patterns for fallback ───────────────────────

USERNAME_PATTERNS = [
    "username", "user_id", "DDDDD", "account", "userid",
    "stuId", "studentId", "login_name", "UserName",
]

PASSWORD_PATTERNS = [
    "password", "upass", "pwd", "userPassword", "PassWord",
    "login_password", "Password",
]

ISP_PATTERNS = [
    "ISP_select", "service", "operator", "isp", "ISP",
    "netType", "network_type", "serviceType",
]

SUCCESS_KEYWORDS = [
    "成功", "success", "已登录", "登录成功", "welcome",
    "loginsuccess", "already_online",
]

FAILURE_KEYWORDS = [
    "失败", "fail", "错误", "error", "密码错误", "账号不存在",
    "password_error", "user_not_found",
]

ISP_SUFFIXES = {
    "1": "",
    "2": "@cmcc",
    "3": "@unicom",
    "4": "@telecom",
    "5": "@glgd",
    "校园网": "",
    "中国移动": "@cmcc",
    "中国联通": "@unicom",
    "中国电信": "@telecom",
    "中国广电": "@glgd",
    "": "",
}

CAPTIVE_PROBE_URLS = (
    "http://1.1.1.1",
    "http://119.29.29.29",
)

REDIRECT_CONTEXT_FIELDS = (
    (
        "wlan_user_ip",
        ("wlanuserip", "ip", "userip", "user-ip", "client_ip", "uip", "station_ip"),
    ),
    ("wlan_user_ipv6", ("wlanuseripv6", "userv6ip")),
    (
        "wlan_user_mac",
        ("wlanusermac", "mac", "usermac", "user-mac", "client_mac", "station_mac"),
    ),
    ("wlan_ac_ip", ("wlanacip", "acip", "switchip", "nasip", "nas-ip")),
    ("wlan_ac_name", ("wlanacname", "sysname", "nasname", "nas-name")),
)

PORTAL_REFRESH_HEADERS = {
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
}
EPORTAL_JS_VERSION = "4.2"
EPORTAL_TERMINAL_TYPE = "1"  # PC client, matching the portal's browser flow.
EPORTAL_LANGUAGE = "zh-cn"
PORTAL_SETTLE_TIMEOUT_SECONDS = 3.0
DIAGNOSTIC_MESSAGE_LIMIT = 500
ISP_DIAGNOSTIC_LABELS = {
    "1": "校园网",
    "2": "中国移动",
    "3": "中国联通",
    "4": "中国电信",
    "5": "中国广电",
}


class AuthClient(QObject):
    """Campus network portal authentication client.

    Signals:
        login_success: Emitted when login succeeds.
        login_failed: Emitted when login fails (with error message).
        page_parsed: Emitted when the login page is parsed (with ParsedForm).
    """

    login_success = Signal(object)  # verified PortalSession
    login_failed = Signal(str)
    login_cancelled = Signal()
    login_started = Signal()
    page_parsed = Signal(object)  # ParsedForm
    isp_options_loaded = Signal(object)  # list[ISPInfo]
    isp_options_failed = Signal(str)
    diagnostic_message = Signal(str)
    _login_finished = Signal(object)  # LoginResult
    _isp_refresh_finished = Signal(object)

    def __init__(
        self,
        portal_url: str = "http://10.0.1.5/",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        super().__init__()
        self.portal_url = portal_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self._parsed_form: Optional[ParsedForm] = None
        self._login_cancel_event = threading.Event()
        self._login_future: Future[LoginResult] | None = None
        self._login_lock = threading.Lock()
        self._closed = False
        self._login_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="guetlinker-login",
        )
        self._isp_refresh_future: Future[list[ISPInfo]] | None = None
        self._isp_refresh_lock = threading.Lock()
        self._utility_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="guetlinker-portal",
        )
        self._login_client_factory = httpx.Client
        self._login_finished.connect(self._on_login_finished)
        self._isp_refresh_finished.connect(self._on_isp_refresh_finished)

        # HTTP client that accepts self-signed certs
        self._client = httpx.Client(
            verify=False,
            timeout=timeout,
            follow_redirects=True,
            # Portal requests must not be sent through an environment proxy.
            trust_env=False,
            headers=PORTAL_REFRESH_HEADERS,
        )

    # ── Public API ────────────────────────────────────────────────

    def fetch_and_parse(self) -> Optional[ParsedForm]:
        """Fetch the login page and parse its form structure.

        Returns:
            ParsedForm if successful, None otherwise.
        """
        try:
            response = self._client.get(self.portal_url)
            response.raise_for_status()
            form = self._parse_form(response.text)
            self._parsed_form = form
            self.page_parsed.emit(form)
            logger.info(
                "Parsed login page: action=%s, user_field=%s, isp_field=%s, isp_count=%d",
                form.action_url, form.username_field, form.isp_field,
                len(form.isp_options),
            )
            return form
        except httpx.HTTPError as e:
            logger.error("Failed to fetch login page: %s", e)
            return None

    def login(
        self,
        user_id: str,
        password: str,
        isp_value: str = "",
        cancel_event: threading.Event | None = None,
    ) -> LoginResult:
        """Synchronously run the GUET Dr.COM login protocol.

        Application code should call :meth:`start_login` so this work runs
        outside the Qt UI thread. The synchronous entry point remains useful
        for isolated protocol tests.
        """
        cancel = cancel_event or threading.Event()
        account = self._account_with_isp_suffix(user_id, isp_value)
        last_message = "服务器未确认登录成功"
        self._publish_diagnostic(
            "认证任务开始：运营商=%s，最大尝试=%d"
            % (ISP_DIAGNOSTIC_LABELS.get(isp_value, "未知"), self.max_retries)
        )

        request_timeout = min(self.timeout, 3.0)
        with self._login_client_factory(
            verify=False,
            timeout=request_timeout,
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/107.0.0.0 Safari/537.36"
                ),
                **PORTAL_REFRESH_HEADERS,
            },
        ) as client:
            # WLAN redirect parameters do not change during one login job.
            # Discover them once instead of paying the timeout on every retry.
            context = self._discover_redirect_context(client)
            self._publish_diagnostic(
                "认证上下文：已获取字段=%s"
                % (", ".join(sorted(context)) if context else "无")
            )
            for attempt in range(1, self.max_retries + 1):
                if cancel.is_set():
                    return LoginResult(False, "登录已取消", cancelled=True)

                logger.info("GUET login attempt %d/%d", attempt, self.max_retries)
                self._publish_diagnostic(
                    f"开始第 {attempt}/{self.max_retries} 次认证"
                )
                verified_session = self._verify_online(client, timeout=0.4)
                if verified_session:
                    self._publish_diagnostic("认证前检查：门户已经在线")
                    return LoginResult(
                        True,
                        "登录成功",
                        portal_session=self._enrich_session_from_context(
                            verified_session,
                            context,
                        ),
                    )

                # The current GUET environment exposes authloginport=801 and
                # real logs show /drcom/login timing out. Try the wireless
                # ePortal endpoint first, retaining Ethernet as a fallback.
                wireless_result = self._request_wireless_login(
                    client,
                    account,
                    password,
                    context,
                )
                last_message = wireless_result.message or last_message
                verified_session = (
                    self._wait_until_online(client, cancel, stage="无线接口")
                    if wireless_result.response_text
                    else None
                )
                if verified_session:
                    self._publish_diagnostic("认证完成：无线接口后门户已在线")
                    return LoginResult(
                        True,
                        "登录成功",
                        wireless_result.response_text,
                        portal_session=self._enrich_session_from_context(
                            verified_session,
                            context,
                        ),
                    )
                if wireless_result.success:
                    last_message = (
                        "无线登录请求已被服务器接受，但门户仍未确认在线"
                    )
                    logger.warning(
                        "Wireless login response was successful, "
                        "but the portal session is still offline"
                    )

                if cancel.is_set():
                    return LoginResult(False, "登录已取消", cancelled=True)

                ethernet_result = self._request_ethernet_login(
                    client,
                    account,
                    password,
                    context,
                )
                last_message = ethernet_result.message or last_message
                verified_session = (
                    self._wait_until_online(client, cancel, stage="有线接口")
                    if ethernet_result.response_text
                    else None
                )
                if verified_session:
                    self._publish_diagnostic("认证完成：有线接口后门户已在线")
                    return LoginResult(
                        True,
                        "登录成功",
                        ethernet_result.response_text,
                        portal_session=self._enrich_session_from_context(
                            verified_session,
                            context,
                        ),
                    )
                if ethernet_result.success:
                    last_message = (
                        "有线登录请求已被服务器接受，但门户仍未确认在线"
                    )
                    logger.warning(
                        "Ethernet login response was successful, "
                        "but the portal session is still offline"
                    )

                if attempt < self.max_retries and cancel.wait(self.retry_delay):
                    return LoginResult(False, "登录已取消", cancelled=True)

        self._publish_diagnostic(
            "认证任务失败：%s"
            % self._sanitize_diagnostic_text(
                last_message,
                account,
                password,
                self._encode_portal_password(password),
                base64.b64encode(password.encode("utf-8")).decode("ascii"),
            )
        )
        return LoginResult(
            False,
            f"登录失败，已重试 {self.max_retries} 次：{last_message}",
        )

    @property
    def is_login_in_progress(self) -> bool:
        with self._login_lock:
            return self._login_future is not None

    def start_login(
        self,
        user_id: str,
        password: str,
        isp_value: str = "",
    ) -> bool:
        """Start one cancellable login task outside the Qt UI thread."""
        with self._login_lock:
            if self._closed or self._login_future is not None:
                return False
            self._login_cancel_event = threading.Event()
            future = self._login_executor.submit(
                self.login,
                user_id,
                password,
                isp_value,
                self._login_cancel_event,
            )
            self._login_future = future

        future.add_done_callback(self._forward_login_result)
        self.login_started.emit()
        return True

    def cancel_login(self) -> bool:
        """Request cancellation of the active login task."""
        with self._login_lock:
            if self._login_future is None:
                return False
            self._login_cancel_event.set()
            return True

    def _forward_login_result(self, future: Future[LoginResult]) -> None:
        try:
            result = future.result()
        except Exception as e:
            logger.exception("Background login task failed")
            result = LoginResult(False, f"登录任务异常: {e}")

        with self._login_lock:
            if self._login_future is future:
                self._login_future = None
        if not self._closed:
            self._login_finished.emit(result)

    @Slot(object)
    def _on_login_finished(self, result: LoginResult) -> None:
        if result.cancelled:
            self.login_cancelled.emit()
        elif result.success and result.portal_session and result.portal_session.is_online:
            logger.info("Login successful")
            self.login_success.emit(result.portal_session)
        elif result.success:
            logger.warning("Rejected unverified login-success result")
            self.login_failed.emit("登录接口已响应，但未获得有效的在线会话")
        else:
            self.login_failed.emit(result.message)

    def _discover_redirect_context(
        self,
        client: httpx.Client,
    ) -> dict[str, str]:
        """Read WLAN parameters from a browser-style captive redirect."""
        for probe_url in CAPTIVE_PROBE_URLS:
            started = time.monotonic()
            try:
                response = client.get(probe_url, timeout=0.8)
            except httpx.HTTPError as e:
                logger.debug(
                    "Captive probe %s unavailable after %.2fs: %s",
                    probe_url,
                    time.monotonic() - started,
                    e,
                )
                continue

            location = response.headers.get("location", "")
            if not response.is_redirect or not location:
                continue

            query = {
                key.lower(): values
                for key, values in parse_qs(urlsplit(location).query).items()
            }
            context = {}
            for target, aliases in REDIRECT_CONTEXT_FIELDS:
                value = next(
                    (
                        query[alias.lower()][0]
                        for alias in aliases
                        if query.get(alias.lower())
                    ),
                    "",
                )
                if target == "wlan_user_mac":
                    value = value.replace("-", "").replace(":", "")
                if value:
                    context[target] = value
            if context:
                logger.info(
                    "Captured captive context from %s: %s",
                    probe_url,
                    ", ".join(sorted(context)),
                )
                return context

        logger.info("No captive-portal redirect context was available")
        return {}

    def _request_ethernet_login(
        self,
        client: httpx.Client,
        account: str,
        password: str,
        context: dict[str, str],
    ) -> LoginResult:
        params = [
            ("callback", "dr1003"),
            ("DDDDD", account),
            ("upass", password),
            *[(key, context[key]) for key in sorted(context)],
            ("0MKKey", "123456"),
        ]
        try:
            started = time.monotonic()
            response = client.get(
                self._portal_endpoint("/drcom/login"),
                params=params,
                timeout=0.8,
            )
            response.raise_for_status()
            result = self._check_login_result(response.text)
            self._publish_endpoint_response(
                "有线",
                response.status_code,
                result,
                account,
                password,
            )
            logger.debug(
                "Ethernet login endpoint responded in %.2fs",
                time.monotonic() - started,
            )
            return result
        except httpx.HTTPError as e:
            message = self._http_error_diagnostic("有线", e)
            self._publish_diagnostic(message)
            return LoginResult(False, message)

    def _request_wireless_login(
        self,
        client: httpx.Client,
        account: str,
        password: str,
        context: dict[str, str],
    ) -> LoginResult:
        encoded_password = self._encode_portal_password(password)
        request_context = dict(context)
        # The browser always includes this field, even when IPv6 is unavailable.
        request_context.setdefault("wlan_user_ipv6", "")
        params = [
            ("callback", "dr1003"),
            ("login_method", "1"),
            ("user_account", f",0,{account}"),
            ("user_password", encoded_password),
            *[(key, request_context[key]) for key in sorted(request_context)],
            ("terminal_type", EPORTAL_TERMINAL_TYPE),
            ("lang", EPORTAL_LANGUAGE),
            ("jsVersion", EPORTAL_JS_VERSION),
        ]
        try:
            started = time.monotonic()
            response = client.get(
                self._portal_endpoint("/eportal/portal/login", port=801),
                params=params,
                timeout=0.8,
            )
            response.raise_for_status()
            result = self._check_login_result(response.text)
            self._publish_endpoint_response(
                "无线",
                response.status_code,
                result,
                account,
                password,
                encoded_password,
                base64.b64encode(password.encode("utf-8")).decode("ascii"),
            )
            logger.debug(
                "Wireless login endpoint responded in %.2fs",
                time.monotonic() - started,
            )
            return result
        except httpx.HTTPError as e:
            message = self._http_error_diagnostic("无线", e)
            self._publish_diagnostic(message)
            return LoginResult(False, message)

    @staticmethod
    def _encode_portal_password(password: str) -> str:
        """Match GUET a41.js ``util.base64encode`` used by a44.js login.

        The portal keeps the low byte of each JavaScript UTF-16 code unit;
        it does not encode the string as UTF-8 first. Preserve the saved
        password unchanged and apply this legacy conversion only on the wire.
        """
        portal_bytes = password.encode("utf-16-le", errors="surrogatepass")[::2]
        return base64.b64encode(portal_bytes).decode("ascii")

    def _publish_endpoint_response(
        self,
        label: str,
        status_code: int,
        result: LoginResult,
        *secrets: str,
    ) -> None:
        """Log response metadata without storing credentials or request URLs."""
        payload = self._parse_jsonp_payload(result.response_text) or {}
        result_value = self._sanitize_diagnostic_text(
            payload.get("result", "缺失"),
            *secrets,
        )
        ret_code = self._sanitize_diagnostic_text(
            payload.get("ret_code", "缺失"),
            *secrets,
        )
        message = self._sanitize_diagnostic_text(result.message, *secrets)
        self._publish_diagnostic(
            f"{label}接口响应：HTTP={status_code}，result={result_value}，"
            f"ret_code={ret_code}，接口判定={'接受' if result.success else '拒绝'}，"
            f"msg={message or '无'}"
        )

    @staticmethod
    def _http_error_diagnostic(label: str, error: httpx.HTTPError) -> str:
        """Describe an HTTP failure without including its credential-bearing URL."""
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        status = f"，HTTP={status_code}" if status_code is not None else ""
        return f"{label}接口请求异常：{type(error).__name__}{status}"

    def _publish_diagnostic(self, message: str) -> None:
        """Persist and publish one credential-free authentication event."""
        safe_message = self._sanitize_diagnostic_text(message)
        logger.info("AUTH_DIAG %s", safe_message)
        self.diagnostic_message.emit(safe_message)

    @staticmethod
    def _sanitize_diagnostic_text(value: object, *secrets: str) -> str:
        """Collapse untrusted response text and remove known secret values."""
        text = " ".join(str(value).split())
        expanded_secrets = set(filter(None, secrets))
        expanded_secrets.update(
            secret.partition("@")[0]
            for secret in tuple(expanded_secrets)
            if "@" in secret
        )
        for secret in sorted(expanded_secrets, key=len, reverse=True):
            text = text.replace(secret, "[已隐藏]")
        return text[:DIAGNOSTIC_MESSAGE_LIMIT]

    def _verify_online(
        self,
        client: httpx.Client,
        *,
        timeout: float = 0.5,
    ) -> PortalSession | None:
        try:
            response = client.get(self.portal_url, timeout=timeout)
            if response.status_code != 200:
                return None
            session = parse_portal_page(response.text, self.portal_url)
            return session if session.is_online else None
        except httpx.HTTPError:
            return None

    def _wait_until_online(
        self,
        client: httpx.Client,
        cancel: threading.Event,
        *,
        stage: str = "认证接口",
    ) -> PortalSession | None:
        """Poll briefly; an endpoint response alone is never login success."""
        started = time.monotonic()
        deadline = time.monotonic() + PORTAL_SETTLE_TIMEOUT_SECONDS
        checks = 0
        while True:
            checks += 1
            session = self._verify_online(client)
            if session:
                self._publish_diagnostic(
                    "%s在线确认成功：耗时=%.2fs，检查=%d次"
                    % (stage, time.monotonic() - started, checks)
                )
                return session
            remaining = deadline - time.monotonic()
            if remaining <= 0 or cancel.wait(min(0.2, remaining)):
                self._publish_diagnostic(
                    "%s在线确认未通过：耗时=%.2fs，检查=%d次"
                    % (stage, time.monotonic() - started, checks)
                )
                return None

    @staticmethod
    def _enrich_session_from_context(
        session: PortalSession,
        context: dict[str, str],
    ) -> PortalSession:
        """Fill delayed portal IP fields from the verified redirect context."""
        return replace(
            session,
            ipv4=session.ipv4 or context.get("wlan_user_ip", ""),
            ipv6=(
                session.ipv6
                or context.get("wlan_user_ipv6", "")
                or find_local_ipv6(
                    session.ipv4 or context.get("wlan_user_ip", "")
                )
            ),
        )

    def _account_with_isp_suffix(self, user_id: str, isp_value: str) -> str:
        suffix = ISP_SUFFIXES.get(isp_value)
        if suffix is None and self._parsed_form:
            option = next(
                (
                    item for item in self._parsed_form.isp_options
                    if item.value == isp_value
                ),
                None,
            )
            suffix = option.suffix if option else ""
        suffix = suffix or ""
        base_account = re.sub(
            r"@(cmcc|unicom|telecom|glgd)$",
            "",
            user_id.strip(),
            flags=re.IGNORECASE,
        )
        return f"{base_account}{suffix}"

    def _portal_endpoint(self, path: str, port: int | None = None) -> str:
        portal = urlsplit(self.portal_url)
        host = portal.hostname or "10.0.1.5"
        netloc = f"{host}:{port}" if port else host
        return urlunsplit((portal.scheme or "http", netloc, path, "", ""))

    def get_isp_options(self, force_refresh: bool = False) -> list[ISPInfo]:
        """Get the list of ISP options from the login page.

        Fetches and parses the page if needed. ``force_refresh`` always
        requests the portal again instead of reusing a previously parsed page.
        """
        if force_refresh or not self._parsed_form:
            form = self.fetch_and_parse()
            if form is None:
                return []
        if self._parsed_form:
            return list(self._parsed_form.isp_options)
        return []

    def refresh_isp_options_async(self) -> bool:
        """Fetch ISP options in the background without blocking the Qt UI."""
        with self._isp_refresh_lock:
            if self._closed or self._isp_refresh_future is not None:
                return False
            future = self._utility_executor.submit(
                self.get_isp_options,
                True,
            )
            self._isp_refresh_future = future
        future.add_done_callback(self._forward_isp_refresh_result)
        return True

    def _forward_isp_refresh_result(
        self,
        future: Future[list[ISPInfo]],
    ) -> None:
        try:
            options = future.result()
            error = "" if options else "门户未返回运营商列表"
        except Exception as e:
            logger.exception("Background ISP refresh failed")
            options = []
            error = str(e)

        with self._isp_refresh_lock:
            if self._isp_refresh_future is future:
                self._isp_refresh_future = None
        if not self._closed:
            self._isp_refresh_finished.emit((options, error))

    @Slot(object)
    def _on_isp_refresh_finished(self, payload: object) -> None:
        options, error = payload
        if options:
            self.isp_options_loaded.emit(options)
        else:
            self.isp_options_failed.emit(error or "获取运营商列表失败")

    def get_portal_session(self) -> Optional[PortalSession]:
        """Fetch the portal page and return its public session information."""
        try:
            response = self._client.get(self.portal_url)
            response.raise_for_status()
            return parse_portal_page(response.text, self.portal_url)
        except httpx.HTTPError as e:
            logger.error("Failed to inspect portal session: %s", e)
            return None

    def logout(self, session: PortalSession | None = None) -> LogoutResult:
        """Log out the current portal session and verify the resulting page.

        The portal page never exposes a password. Logout uses only the public
        endpoint and parameters advertised by the current online page.
        """
        current = session if session and session.is_online else self.get_portal_session()
        if current is None:
            return LogoutResult(False, "无法获取当前校园网会话")
        if current.state == PortalPageState.LOGIN_REQUIRED:
            return LogoutResult(True, "当前已经断开")
        if not current.is_online:
            return LogoutResult(False, "无法确认当前校园网登录状态")
        if current.logout_request is None:
            return LogoutResult(False, "在线页未提供注销接口")

        request = current.logout_request
        try:
            if request.method == "POST":
                response = self._client.post(
                    request.url,
                    content=request.data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            else:
                response = self._client.get(request.url)
            response.raise_for_status()

            verified = self.get_portal_session()
            if verified and verified.state == PortalPageState.LOGIN_REQUIRED:
                logger.info("Portal logout verified")
                self._parsed_form = None
                return LogoutResult(True, "校园网已断开")
            if verified and verified.is_online:
                return LogoutResult(False, "注销请求已发送，但门户仍显示在线")
            return LogoutResult(False, "注销请求已发送，但无法确认是否已断开")
        except httpx.HTTPError as e:
            logger.error("Portal logout failed: %s", e)
            return LogoutResult(False, f"注销请求失败: {e}")

    # ── Private: HTML parsing ─────────────────────────────────────

    def _parse_form(self, html: str) -> ParsedForm:
        """Parse the login page HTML to extract form structure.

        Strategy:
            1. BeautifulSoup structural parsing
            2. Fallback to common field name patterns
        """
        soup = BeautifulSoup(html, "html.parser")
        form = ParsedForm()

        # Prefer a form that contains a password field. Portal pages sometimes
        # include unrelated search or language-selector forms before the login form.
        form_tag = next(
            (candidate for candidate in soup.find_all("form")
             if candidate.find("input", {"type": re.compile(r"^password$", re.I)})),
            soup.find("form"),
        )
        if form_tag:
            form.action_url = form_tag.get("action", "")
            form.method = form_tag.get("method", "POST").upper()

            # Parse input fields
            for inp in form_tag.find_all("input"):
                name = inp.get("name", "")
                input_type = inp.get("type", "text").lower()
                value = inp.get("value", "")

                if not name:
                    continue

                if input_type == "hidden":
                    form.hidden_fields[name] = value
                elif input_type in ("text", "tel", "email"):
                    if not form.username_field or self._looks_like_username(name):
                        form.username_field = name
                elif input_type == "password":
                    form.password_field = name

            # Parse select fields (ISP dropdown)
            for select in form_tag.find_all("select"):
                name = select.get("name", "")
                if not form.isp_field or self._looks_like_isp(name):
                    form.isp_field = name
                    form.isp_options = []
                    for opt in select.find_all("option"):
                        opt_value = opt.get("value", "")
                        opt_label = opt.get_text(strip=True)
                        if opt_value:
                            form.isp_options.append(
                                ISPInfo(value=opt_value, label=opt_label)
                            )
                            if opt.has_attr("selected") or not form.default_isp_value:
                                form.default_isp_value = opt_value
        else:
            # No <form> found — try fallback
            logger.warning("No <form> tag found, using fallback parsing")

        # Dr.COM 4.x portals render the operator control from a JavaScript
        # ``carrier`` object rather than an HTML <select>. The GUET portal's
        # object also contains a malformed title string, so parse the valid
        # data array independently instead of requiring the whole object to be
        # valid JSON.
        if not form.isp_options:
            scripted_options, scripted_default = self._parse_carrier_options(html)
            if scripted_options:
                form.isp_options = scripted_options
                form.default_isp_value = scripted_default

        # Apply fallback patterns if fields are missing
        if not form.username_field:
            form.username_field = self._find_field_name(html, USERNAME_PATTERNS)
        if not form.password_field:
            form.password_field = self._find_field_name(html, PASSWORD_PATTERNS)
        if not form.isp_field:
            form.isp_field = self._find_field_name(html, ISP_PATTERNS)

        # Default action URL to portal URL
        if not form.action_url:
            form.action_url = self.portal_url

        return form

    @staticmethod
    def _parse_carrier_options(html: str) -> tuple[list[ISPInfo], str]:
        """Extract ISP options from a Dr.COM JavaScript ``carrier`` object."""
        assignment = re.search(
            r"\bcarrier\s*=\s*(?P<quote>['\"])(?P<payload>.*?)(?P=quote)\s*;",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if not assignment:
            return [], ""

        payload = assignment.group("payload")
        data_match = re.search(
            r"""["']data["']\s*:\s*(?P<data>\[[^\]]*\])""",
            payload,
            re.IGNORECASE | re.DOTALL,
        )
        if not data_match:
            return [], ""

        try:
            carriers = json.loads(data_match.group("data"))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Unable to parse ISP data from portal carrier object")
            return [], ""

        options = []
        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            value = str(carrier.get("id", "")).strip()
            label = str(carrier.get("name", "")).strip()
            suffix = str(carrier.get("suffix", "")).strip()
            if value and label:
                options.append(
                    ISPInfo(value=value, label=label, suffix=suffix)
                )

        # The current GUET portal advertises carrier IDs 1-4 but omits China
        # Broadnet even while authenticated accounts use the public @glgd
        # suffix. Keep the portal as the primary source and apply this
        # GUET-specific compatibility completion only when its fingerprint is
        # present.
        is_guet_portal = "桂林电子科技大学" in html or "@glgd" in html
        has_broadnet = any(
            option.suffix.lower() == "@glgd" or "广电" in option.label
            for option in options
        )
        if is_guet_portal and not has_broadnet:
            used_values = {option.value for option in options}
            broadnet_value = "5"
            while broadnet_value in used_values:
                broadnet_value = str(int(broadnet_value) + 1)
            options.append(
                ISPInfo(
                    value=broadnet_value,
                    label="中国广电",
                    suffix="@glgd",
                )
            )

        default_match = re.search(
            r"""["']defaultID["']\s*:\s*["'](?P<value>[^"']*)["']""",
            payload,
            re.IGNORECASE,
        )
        default_value = default_match.group("value").strip() if default_match else ""
        if default_value not in {option.value for option in options}:
            default_value = options[0].value if options else ""

        return options, default_value

    @staticmethod
    def _looks_like_username(name: str) -> bool:
        """Check if a field name looks like a username field."""
        lower = name.lower()
        return any(p in lower for p in ("user", "account", "ddddd", "stuid", "login"))

    @staticmethod
    def _looks_like_isp(name: str) -> bool:
        """Check if a field name looks like an ISP selector."""
        lower = name.lower()
        return any(p in lower for p in ("isp", "service", "operator", "nettype", "network"))

    @staticmethod
    def _find_field_name(html: str, patterns: list[str]) -> str:
        """Search HTML for a field name matching any of the given patterns."""
        for pattern in patterns:
            # Look for name="pattern" in input/select tags
            match = re.search(
                rf'name\s*=\s*["\']?({re.escape(pattern)})["\']?',
                html, re.IGNORECASE,
            )
            if match:
                return match.group(1)
        return patterns[0] if patterns else ""

    # ── Private: helpers ──────────────────────────────────────────

    def _resolve_action_url(self, action: str) -> str:
        """Resolve a form action URL to an absolute URL."""
        if not action:
            return self.portal_url
        if action.startswith("http"):
            return action
        # Relative URL
        base = self.portal_url.rstrip("/")
        if action.startswith("/"):
            # Absolute path relative to origin
            from urllib.parse import urlparse
            parsed = urlparse(self.portal_url)
            return f"{parsed.scheme}://{parsed.netloc}{action}"
        return f"{base}/{action}"

    @staticmethod
    def _parse_jsonp_payload(response_text: str) -> dict | None:
        """Extract a JSON object from the Dr.COM JSONP response format."""
        jsonp_match = re.search(
            r"^[^(]*\(\s*(?P<payload>\{.*\})\s*\)\s*;?\s*$",
            response_text.strip(),
            re.DOTALL,
        )
        if not jsonp_match:
            return None
        try:
            payload = json.loads(jsonp_match.group("payload"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _check_login_result(response_text: str) -> LoginResult:
        """Check if the login response indicates success."""
        payload = AuthClient._parse_jsonp_payload(response_text)
        if payload is not None and "result" in payload:
            message = str(payload.get("msg") or payload.get("message") or "")
            result_value = payload["result"]
            success = (
                result_value is True
                or result_value == 1
                or (
                    isinstance(result_value, str)
                    and result_value.strip().lower() in {"1", "true", "ok"}
                )
            )
            return LoginResult(
                success=success,
                message=message or (
                    "登录成功" if success else "服务器拒绝登录"
                ),
                response_text=response_text,
            )

        text_lower = response_text.lower()

        # Check for success keywords
        for keyword in SUCCESS_KEYWORDS:
            if keyword.lower() in text_lower:
                return LoginResult(
                    success=True,
                    message="登录成功",
                    response_text=response_text,
                )

        # Check specific failure keywords first so the reported reason is useful.
        for keyword in sorted(FAILURE_KEYWORDS, key=len, reverse=True):
            if keyword.lower() in text_lower:
                return LoginResult(
                    success=False,
                    message=f"登录失败: {keyword}",
                    response_text=response_text,
                )

        # A response without a verified success marker must not be treated as a
        # successful authentication. The portal can return its login page again
        # with HTTP 200 after a rejected submission.
        return LoginResult(
            success=False,
            message="无法确认登录是否成功",
            response_text=response_text,
        )

    # ── Cleanup ───────────────────────────────────────────────────

    def close(self) -> None:
        """Cancel background authentication and release HTTP resources."""
        if self._closed:
            return
        self._closed = True
        self._login_cancel_event.set()
        self._login_executor.shutdown(wait=False, cancel_futures=True)
        self._utility_executor.shutdown(wait=False, cancel_futures=True)
        self._client.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
