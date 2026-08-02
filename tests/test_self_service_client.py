"""Protocol tests for the GUET self-service login and CAPTCHA flow."""

import hashlib
from urllib.parse import parse_qs

import httpx
import pytest

from src.core.self_service_client import SelfServiceClient


def _login_html(*, captcha: bool, error: str = "", checkcode: str = "6663") -> str:
    hidden = "" if captcha else "hide"
    return f"""
    <html><body>
      <form action="/Self/login/verify;jsessionid=TEST" method="post">
        <input name="foo" type="text">
        <input name="bar" type="password">
        <input name="checkcode" type="hidden" value="{checkcode}">
        <input name="account"><input name="password">
        <div id="randomDiv" class="form-group {hidden}">
          <input name="code">
        </div>
      </form>
      <div id="errorTip"></div>
      <script>
        (function (tip) {{
          if (tip) {{ $(tip).appendTo("#errorTip"); }}
        }})('{error}');
      </script>
    </body></html>
    """


def test_one_failed_submit_reveals_captcha_and_never_retries():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/Self/login/":
            return httpx.Response(200, text=_login_html(captcha=False))
        if request.method == "POST":
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert form["foo"] == [""]
            assert form["bar"] == [""]
            assert form["checkcode"] == ["6663"]
            assert form["account"] == ["20240001"]
            assert form["password"] == [
                hashlib.md5(b"wrong-password").hexdigest()
            ]
            return httpx.Response(
                200,
                text=_login_html(
                    captcha=True,
                    error="账号或密码错误，请输入验证码",
                    checkcode="7777",
                ),
            )
        if request.url.path == "/Self/login/randomCode":
            return httpx.Response(200, content=b"captcha-image")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = SelfServiceClient(client=http)

    result = client.login("20240001", "wrong-password")

    assert result.success is False
    assert result.captcha_required is True
    assert result.captcha_image == b"captcha-image"
    assert "验证码" in result.message
    assert [request.method for request in requests].count("POST") == 1


def test_captcha_submit_reuses_session_page_and_accepts_redirected_success():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "GET" and request.url.path == "/Self/login/":
            return httpx.Response(
                200,
                text=_login_html(captcha=True, checkcode="8888"),
            )
        if request.method == "GET" and request.url.path == "/Self/login/randomCode":
            return httpx.Response(200, content=b"image")
        if request.method == "POST":
            post_count += 1
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert form["code"] == ["AB12"]
            assert form["checkcode"] == ["8888"]
            return httpx.Response(
                302,
                headers={"Location": "/Self/index"},
            )
        if request.url.path == "/Self/index":
            return httpx.Response(
                200,
                text='<html><span class="user-name">张同学</span></html>',
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = SelfServiceClient(client=http)

    first = client.login("20240001", "secret")
    assert first.captcha_required is True
    assert post_count == 0

    result = client.login("20240001", "secret", "AB12")

    assert result.success is True
    assert result.session is not None
    assert result.session.account == "20240001"
    assert result.session.display_name == "张同学"
    assert post_count == 1


def test_login_page_parser_resolves_session_action_and_hidden_captcha():
    page = SelfServiceClient.parse_login_page(
        _login_html(captcha=False, checkcode="1234"),
        "https://nicdrcom.guet.edu.cn/Self/login/",
    )

    assert page.action_url == (
        "https://nicdrcom.guet.edu.cn/Self/login/verify;jsessionid=TEST"
    )
    assert page.checkcode == "1234"
    assert page.captcha_required is False


def test_traffic_summary_uses_date_form_parameters():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/Self/bill/getUserOnlineLog"
        assert request.url.params["startTime"] == "2026-07-01"
        assert request.url.params["endTime"] == "2026-07-31"
        assert request.url.params["pageSize"] == "10"
        assert request.url.params["pageNumber"] == "1"
        return httpx.Response(
            200,
            json={
                "total": 37,
                "rows": [],
                "summary": {
                    "INTERNETUPFLOW": 1285.84,
                    "INTERNETDOWNFLOW": "9660.167",
                    "CHINANETUPFLOW": 15.466,
                    "CHINANETDOWNFLOW": 384.938,
                    "FLOW": 0,
                },
            },
        )

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = SelfServiceClient(client=http)

    result = client.fetch_traffic("2026-07-01", "2026-07-31")

    assert result.international_up_mb == 1285.84
    assert result.international_down_mb == 9660.167
    assert result.domestic_up_mb == 15.466
    assert result.domestic_down_mb == 384.938


def test_account_overview_reads_status_and_only_wiring_data():
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/Self/dashboard":
            return httpx.Response(
                200,
                text="""
                <div class="row">
                  <label>状　　态：</label>
                  <div><span class="label label-success">正常</span></div>
                </div>
                <script>window.user = {"phone": "must-not-be-read"};</script>
                """,
            )
        if request.url.path == "/Self/setting/personList":
            return httpx.Response(
                200,
                text="""
                <input name="mobile" value="must-not-be-read">
                <input name="userCompany" value="近期存在一次异常记录">
                """,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = SelfServiceClient(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    result = client.fetch_account_overview()

    assert result.status == "正常"
    assert result.anomaly_info == "近期存在一次异常记录"
    assert requested_paths == [
        "/Self/dashboard",
        "/Self/setting/personList",
    ]


@pytest.mark.parametrize("value", ["", "N/A", " n/a "])
def test_empty_wiring_data_is_shown_as_no_anomaly(value):
    html = f'<input name="userCompany" value="{value}">'

    assert SelfServiceClient.parse_anomaly_info(html) == "暂无异常信息"


def test_traffic_query_rejects_more_than_sixty_days_before_request():
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid date range must not send a request")

    client = SelfServiceClient(
        client=httpx.Client(transport=httpx.MockTransport(unexpected_request))
    )

    with pytest.raises(ValueError, match="60 天"):
        client.fetch_traffic("2026-01-01", "2026-04-01")
