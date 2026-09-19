"""Tests for GuetLinker authentication client."""

import base64
import threading
import httpx
import pytest

from src.core.auth_client import AuthClient, ParsedForm, ISPInfo, LoginResult
from src.core.portal import PortalPageState, PortalSession, parse_portal_page
from tests.test_portal import LOGIN_PAGE, ONLINE_PAGE


class TestParsedForm:
    """Tests for ParsedForm data class."""

    def test_defaults(self):
        form = ParsedForm()
        assert form.action_url == ""
        assert form.method == "POST"
        assert form.username_field == ""
        assert form.password_field == ""
        assert form.isp_field == ""
        assert form.isp_options == []
        assert form.default_isp_value == ""
        assert form.hidden_fields == {}


class TestAuthClientParsing:
    """Tests for the HTML form parsing logic."""

    def _make_client(self) -> AuthClient:
        return AuthClient(portal_url="http://10.0.1.5/")

    def test_parse_simple_form(self):
        """Parse a simple login form with username, password, and ISP select."""
        html = """
        <html>
        <body>
        <form action="/login" method="POST">
            <input type="text" name="username" />
            <input type="password" name="password" />
            <select name="ISP_select">
                <option value="chinanet">电信</option>
                <option value="cmcc">移动</option>
                <option value="unicom">联通</option>
            </select>
            <input type="hidden" name="token" value="abc123" />
            <input type="submit" value="登录" />
        </form>
        </body>
        </html>
        """
        client = self._make_client()
        form = client._parse_form(html)

        assert form.action_url == "/login"
        assert form.method == "POST"
        assert form.username_field == "username"
        assert form.password_field == "password"
        assert form.isp_field == "ISP_select"
        assert len(form.isp_options) == 3
        assert form.isp_options[0] == ISPInfo(value="chinanet", label="电信")
        assert form.isp_options[1] == ISPInfo(value="cmcc", label="移动")
        assert form.isp_options[2] == ISPInfo(value="unicom", label="联通")
        assert form.default_isp_value == "chinanet"
        assert form.hidden_fields == {"token": "abc123"}

    def test_parse_form_with_ddddd_fields(self):
        """Parse a form using DDDDD field name (common in some campus systems)."""
        html = """
        <form action="/auth" method="post">
            <input type="text" name="DDDDD" />
            <input type="password" name="upass" />
            <select name="service">
                <option value="0">电信</option>
                <option value="1">移动</option>
            </select>
        </form>
        """
        client = self._make_client()
        form = client._parse_form(html)

        assert form.username_field == "DDDDD"
        assert form.password_field == "upass"
        assert form.isp_field == "service"
        assert len(form.isp_options) == 2

    def test_parse_drcom_carrier_options(self):
        """Parse the JavaScript carrier data used by the current GUET portal."""
        html = """
        <script>
        portalname='桂林电子科技大学';
        carrier='{"yys":{"title": "服务类型,"mode":"radiobutton","type":"1",
        "data":[
            {"id":"1","name":"校园网","suffix":""},
            {"id":"2","name":"中国移动","suffix":"@cmcc"},
            {"id":"3","name":"中国联通","suffix":"@unicom"},
            {"id":"4","name":"中国电信","suffix":"@telecom"}
        ],"defaultID":"1"}}';
        </script>
        """
        form = self._make_client()._parse_form(html)

        assert form.isp_options == [
            ISPInfo(value="1", label="校园网", suffix=""),
            ISPInfo(value="2", label="中国移动", suffix="@cmcc"),
            ISPInfo(value="3", label="中国联通", suffix="@unicom"),
            ISPInfo(value="4", label="中国电信", suffix="@telecom"),
            ISPInfo(value="5", label="中国广电", suffix="@glgd"),
        ]
        assert form.default_isp_value == "1"

    def test_parse_no_form_fallback(self):
        """When no <form> tag exists, fallback to pattern matching."""
        html = """
        <input type="text" name="username" />
        <input type="password" name="password" />
        <select name="ISP_select">
            <option value="1">电信</option>
        </select>
        """
        client = self._make_client()
        form = client._parse_form(html)

        # Should use fallback patterns
        assert form.username_field == "username"
        assert form.password_field == "password"
        assert form.isp_field == "ISP_select"

    def test_resolve_action_url_absolute(self):
        """Absolute action URL should be used as-is."""
        client = self._make_client()
        assert client._resolve_action_url("http://10.0.1.5/login") == "http://10.0.1.5/login"

    def test_resolve_action_url_relative(self):
        """Relative action URL should be resolved against portal URL."""
        client = self._make_client()
        result = client._resolve_action_url("/cgi-bin/login")
        assert result.startswith("http://10.0.1.5/")

    def test_resolve_action_url_empty(self):
        """Empty action URL should default to portal URL."""
        client = self._make_client()
        assert client._resolve_action_url("") == "http://10.0.1.5/"

    def test_check_login_result_success(self):
        """Response with success keywords should be detected."""
        result = AuthClient._check_login_result("登录成功！欢迎回来")
        assert result.success is True

    def test_check_login_result_failure(self):
        """Response with failure keywords should be detected."""
        result = AuthClient._check_login_result("密码错误，请重新输入")
        assert result.success is False
        assert "密码错误" in result.message

    def test_check_login_result_ambiguous(self):
        """An unrecognized response cannot be considered a successful login."""
        result = AuthClient._check_login_result("<html>redirecting...</html>")
        assert result.success is False
        assert result.message == "无法确认登录是否成功"

    def test_check_login_result_uses_jsonp_result_field(self):
        failed = AuthClient._check_login_result(
            'dr1003({"result":0,"msg":"认证失败"})'
        )
        succeeded = AuthClient._check_login_result(
            'dr1003({"result":1,"msg":"认证成功"})'
        )
        succeeded_with_portal_value = AuthClient._check_login_result(
            'dr1003({"result":"ok","msg":"1"})'
        )

        assert failed.success is False
        assert failed.message == "认证失败"
        assert succeeded.success is True
        assert succeeded.message == "认证成功"
        assert succeeded_with_portal_value.success is True
        assert succeeded_with_portal_value.message == "1"

    @pytest.mark.parametrize("password", ["special-secret", "päss中😀!"])
    def test_endpoint_diagnostic_redacts_credentials(self, password):
        client = self._make_client()
        messages = []
        client.diagnostic_message.connect(messages.append)
        account = "20240001@glgd"
        encoded_password = client._encode_portal_password(password)
        utf8_password = base64.b64encode(password.encode()).decode()

        class Response:
            status_code = 200
            text = (
                'dr1003({"result":0,"ret_code":1,"msg":"'
                f'{account} {password} {encoded_password} {utf8_password}'
                '"})'
            )

            def raise_for_status(self):
                pass

        class FakeClient:
            def get(self, url, params=None, timeout=None):
                return Response()

        client._request_wireless_login(
            FakeClient(),
            account,
            password,
            {},
        )

        diagnostic = "\n".join(messages)
        assert "result=0" in diagnostic
        assert "ret_code=1" in diagnostic
        assert account not in diagnostic
        assert "20240001" not in diagnostic
        assert password not in diagnostic
        assert encoded_password not in diagnostic
        assert utf8_password not in diagnostic
        client.close()

    @pytest.mark.parametrize(
        ("password", "expected"),
        [
            ("secret", "c2VjcmV0"),
            ("päss!", "cORzcyE="),
            ("A中!", "QS0h"),
            ("A😀!", "QT0AIQ=="),
        ],
    )
    def test_wireless_password_matches_guet_javascript(self, password, expected):
        """Golden values from a41.js, including UTF-16 surrogate pairs."""
        client = self._make_client()
        requests = []

        def capture(request):
            requests.append(request)
            return httpx.Response(200, text='dr1003({"result":1})')

        try:
            with httpx.Client(transport=httpx.MockTransport(capture)) as mock:
                client._request_wireless_login(
                    mock, "20240001@glgd", password, {}
                )
            assert len(requests) == 1
            assert requests[0].url.params["user_password"] == expected
        finally:
            client.close()

    def test_parse_prefers_login_form(self):
        """The parser should ignore unrelated forms before the login form."""
        html = """
        <form action="/search"><input type="text" name="query" /></form>
        <form action="/login">
            <input type="text" name="UserID" />
            <input type="password" name="Password" />
        </form>
        """
        form = self._make_client()._parse_form(html)
        assert form.action_url == "/login"
        assert form.username_field == "UserID"
        assert form.password_field == "Password"

    def test_fallback_preserves_field_case(self):
        """Fallback matching must preserve the exact portal field name."""
        html = '<input type="text" name="UserName" />'
        form = self._make_client()._parse_form(html)
        assert form.username_field == "UserName"

    def test_guet_login_uses_wireless_first_and_ethernet_fallback(self):
        """Use both GUET GET protocols with exact parameters and a fast order."""
        client = AuthClient(
            portal_url="http://10.0.1.5/",
            max_retries=1,
            retry_delay=0,
        )
        calls = []
        portal_checks = []

        class Response:
            def __init__(self, text="", status_code=200, location=""):
                self.text = text
                self.status_code = status_code
                self.headers = {"location": location} if location else {}
                self.is_redirect = bool(location)

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url, params=None, timeout=None):
                calls.append((url, params))
                if url == "http://1.1.1.1":
                    return Response(
                        status_code=302,
                        location=(
                            "http://10.0.1.5/?"
                            "wlanuserip=10.1.2.3&"
                            "wlanusermac=AA-BB-CC-DD-EE-FF&"
                            "wlanacip=10.0.0.1&wlanacname=GUET-AC"
                        ),
                    )
                if url.endswith("/drcom/login"):
                    return Response('dr1003({"result":1,"msg":"认证成功"})')
                if url.endswith("/eportal/portal/login"):
                    return Response('dr1003({"result":0,"msg":"需要有线登录"})')
                if url == client.portal_url:
                    portal_checks.append(True)
                    return Response(
                        LOGIN_PAGE if len(portal_checks) < 3 else ONLINE_PAGE
                    )
                raise AssertionError(f"unexpected URL: {url}")

        client._login_client_factory = FakeClient
        verified_session = parse_portal_page(ONLINE_PAGE, client.portal_url)
        verification_rounds = iter([None, verified_session])
        client._wait_until_online = lambda *args, **kwargs: next(
            verification_rounds
        )
        result = client.login("20240001", "secret", "5")

        assert result.success is True
        assert result.portal_session is not None
        assert result.portal_session.ipv6 == "2001:db8::1"
        wireless = calls[2]
        assert wireless == (
            "http://10.0.1.5:801/eportal/portal/login",
            [
                ("callback", "dr1003"),
                ("login_method", "1"),
                ("user_account", ",0,20240001@glgd"),
                (
                    "user_password",
                    base64.b64encode(b"secret").decode("ascii"),
                ),
                ("wlan_ac_ip", "10.0.0.1"),
                ("wlan_ac_name", "GUET-AC"),
                ("wlan_user_ip", "10.1.2.3"),
                ("wlan_user_ipv6", ""),
                ("wlan_user_mac", "AABBCCDDEEFF"),
                ("terminal_type", "1"),
                ("lang", "zh-cn"),
                ("jsVersion", "4.2"),
            ],
        )
        ethernet = calls[3]
        assert ethernet == (
            "http://10.0.1.5/drcom/login",
            [
                ("callback", "dr1003"),
                ("DDDDD", "20240001@glgd"),
                ("upass", "secret"),
                ("wlan_ac_ip", "10.0.0.1"),
                ("wlan_ac_name", "GUET-AC"),
                ("wlan_user_ip", "10.1.2.3"),
                ("wlan_user_mac", "AABBCCDDEEFF"),
                ("0MKKey", "123456"),
            ],
        )
        client.close()

    def test_delayed_online_state_overrides_legacy_failure_response(self):
        """The GUET gateway can authenticate before returning a success code."""
        client = AuthClient(
            portal_url="http://10.0.1.5/",
            max_retries=1,
            retry_delay=0,
        )
        requested_urls = []
        online_session = parse_portal_page(ONLINE_PAGE, client.portal_url)

        class Response:
            status_code = 200
            headers = {}
            is_redirect = False

            def __init__(self, text=""):
                self.text = text

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url, params=None, timeout=None):
                requested_urls.append(url)
                if url == "http://1.1.1.1":
                    return Response()
                if url == "http://119.29.29.29":
                    return Response()
                if url == client.portal_url:
                    return Response(LOGIN_PAGE)
                if url.endswith("/eportal/portal/login"):
                    return Response('dr1003({"result":0,"msg":"1"})')
                raise AssertionError(f"unexpected URL: {url}")

        client._login_client_factory = FakeClient
        client._wait_until_online = lambda *args, **kwargs: online_session

        result = client.login("20240001", "secret", "5")

        assert result.success is True
        assert result.portal_session == online_session
        assert not any(url.endswith("/drcom/login") for url in requested_urls)
        client.close()

    def test_endpoint_success_is_not_success_until_portal_is_online(
        self,
        monkeypatch,
    ):
        """A result=1 response must not create a false login-success event."""
        client = AuthClient(
            portal_url="http://10.0.1.5/",
            max_retries=1,
            retry_delay=0,
        )

        class Response:
            status_code = 200
            headers = {}
            is_redirect = False
            text = 'dr1003({"result":1,"msg":"认证成功"})'

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url, params=None, timeout=None):
                return Response()

        client._login_client_factory = FakeClient
        monkeypatch.setattr(client, "_verify_online", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            client,
            "_wait_until_online",
            lambda *args, **kwargs: False,
        )

        result = client.login("20240001", "secret", "1")

        assert result.success is False
        assert "门户仍未确认在线" in result.message
        client.close()

    def test_unverified_success_result_emits_failure(self):
        client = self._make_client()
        succeeded = []
        failed = []
        client.login_success.connect(succeeded.append)
        client.login_failed.connect(failed.append)

        client._on_login_finished(LoginResult(True, "接口成功"))

        assert succeeded == []
        assert failed == ["登录接口已响应，但未获得有效的在线会话"]
        client.close()

    def test_redirect_context_falls_back_and_accepts_portal_aliases(self):
        client = self._make_client()
        calls = []

        class Response:
            def __init__(self, location=""):
                self.headers = {"location": location} if location else {}
                self.is_redirect = bool(location)

        class FakeClient:
            def get(self, url, timeout=None):
                calls.append(url)
                if url == "http://1.1.1.1":
                    return Response()
                return Response(
                    "http://10.0.1.5/?"
                    "UserIP=10.2.3.4&UserV6IP=2001%3A%3A8&"
                    "user-mac=AA%3ABB%3ACC%3ADD%3AEE%3AFF&"
                    "nasip=10.0.0.8&nasname=GUET"
                )

        context = client._discover_redirect_context(FakeClient())

        assert calls == ["http://1.1.1.1", "http://119.29.29.29"]
        assert context == {
            "wlan_user_ip": "10.2.3.4",
            "wlan_user_ipv6": "2001::8",
            "wlan_user_mac": "AABBCCDDEEFF",
            "wlan_ac_ip": "10.0.0.8",
            "wlan_ac_name": "GUET",
        }
        client.close()

    def test_verified_session_uses_redirect_ipv6_when_portal_field_is_delayed(self):
        session = PortalSession(
            state=PortalPageState.ONLINE,
            user_id="20240001",
            ipv4="10.2.3.4",
        )

        enriched = AuthClient._enrich_session_from_context(
            session,
            {"wlan_user_ipv6": "2001::8"},
        )

        assert enriched.is_online is True
        assert enriched.ipv6 == "2001::8"

    def test_background_login_can_cancel_during_retry_wait(self, qtbot):
        """Cancellation interrupts the retry delay without blocking the UI."""
        client = AuthClient(
            portal_url="http://10.0.1.5/",
            max_retries=3,
            retry_delay=30,
        )
        calls = []
        cancelled = []
        client.login_cancelled.connect(lambda: cancelled.append(True))

        class Response:
            status_code = 200
            headers = {}
            is_redirect = False

            def __init__(self, text=""):
                self.text = text

            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url, params=None, timeout=None):
                calls.append(url)
                if url == client.portal_url:
                    return Response(LOGIN_PAGE)
                return Response('dr1003({"result":0,"msg":"认证失败"})')

        client._login_client_factory = FakeClient

        assert client.start_login("20240001", "secret", "1") is True
        qtbot.waitUntil(lambda: len(calls) >= 5, timeout=2000)
        assert client.cancel_login() is True
        qtbot.waitUntil(lambda: cancelled == [True], timeout=2000)

        assert client.is_login_in_progress is False
        client.close()

    def test_isp_options_empty(self, monkeypatch):
        """ISP options should be empty when no portal page can be fetched."""
        client = self._make_client()
        monkeypatch.setattr(client, "fetch_and_parse", lambda: None)
        assert client.get_isp_options() == []

    def test_isp_options_force_refresh_replaces_cached_page(self, monkeypatch):
        """The refresh action must fetch again even when an empty page is cached."""
        client = self._make_client()
        client._parsed_form = ParsedForm()
        refreshed = ParsedForm(
            isp_options=[ISPInfo(value="1", label="校园网")],
        )
        calls = []

        def fetch():
            calls.append(True)
            client._parsed_form = refreshed
            return refreshed

        monkeypatch.setattr(client, "fetch_and_parse", fetch)

        assert client.get_isp_options(force_refresh=True) == refreshed.isp_options
        assert calls == [True]

    def test_async_isp_refresh_is_single_flight(self, monkeypatch, qtbot):
        client = self._make_client()
        release = threading.Event()
        loaded = []
        options = [ISPInfo("1", "校园网", "")]
        client.isp_options_loaded.connect(lambda value: loaded.append(value))

        def fetch(force_refresh=False):
            release.wait(1)
            return options

        monkeypatch.setattr(client, "get_isp_options", fetch)

        assert client.refresh_isp_options_async() is True
        assert client.refresh_isp_options_async() is False
        release.set()
        qtbot.waitUntil(lambda: loaded == [options], timeout=2000)
        client.close()

    def test_logout_uses_portal_endpoint_and_verifies_result(self, monkeypatch):
        """Logout is tested with mocked HTTP only; it must never require a password."""
        client = self._make_client()
        session = parse_portal_page(ONLINE_PAGE, client.portal_url)
        calls = []

        class Response:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                pass

        def fake_get(url):
            calls.append(url)
            if url == client.portal_url:
                return Response(LOGIN_PAGE)
            return Response("logout accepted")

        monkeypatch.setattr(client._client, "get", fake_get)

        result = client.logout(session)

        assert result.success is True
        assert calls == [
            (
                "http://10.0.1.5:801/eportal/"
                "?c=ACSetting&a=Logout&ver=1.0&url=drappall"
            ),
            client.portal_url,
        ]

    def test_logout_without_advertised_endpoint_is_rejected(self, monkeypatch):
        """An online page without a logout URL must not send a guessed request."""
        client = self._make_client()
        session = PortalSession(
            state=PortalPageState.ONLINE,
            user_id="20240001",
        )
        monkeypatch.setattr(
            client._client,
            "get",
            lambda _: pytest.fail("logout should not send an HTTP request"),
        )

        result = client.logout(session)

        assert result.success is False
        assert result.message == "在线页未提供注销接口"
