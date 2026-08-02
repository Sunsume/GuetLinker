"""Tests for Dr.COM portal page classification and session parsing."""

import pytest

from src.core.portal import (
    PortalPageState,
    parse_portal_page,
    split_portal_account,
)


ONLINE_PAGE = """
<html>
<head>
<title>注销页</title>
<!--Dr.COMWebLoginID_1.htm-->
<script>
uid='000000000000@glgd';
v4ip='192.0.2.10';
v6ip='2001:db8::1';
authlogouttype=1;
authlogoutIP='';
authlogoutport=801;
authlogoutpath='/eportal/?c=ACSetting&a=Logout&ver=1.0';
authlogoutparam='url=drappall';
authlogoutpost='';
</script>
</head>
<body></body>
<script>page.run(1);</script>
</html>
"""

LOGIN_PAGE = """
<html>
<head><title>登录页</title><!--Dr.COMWebLoginID_0.htm--></head>
<body><input type="password" name="upass"></body>
<script>page.run(0);</script>
</html>
"""


def test_parse_online_session_and_logout_request():
    session = parse_portal_page(ONLINE_PAGE, "http://10.0.1.5/")

    assert session.state == PortalPageState.ONLINE
    assert session.is_online is True
    assert session.user_id == "000000000000@glgd"
    assert session.account_id == "000000000000"
    assert session.operator_name == "中国广电"
    assert session.ipv4 == "192.0.2.10"
    assert session.ipv6 == "2001:db8::1"
    assert session.logout_request is not None
    assert session.logout_request.method == "GET"
    assert session.logout_request.url == (
        "http://10.0.1.5:801/eportal/"
        "?c=ACSetting&a=Logout&ver=1.0&url=drappall"
    )


def test_parse_login_required_page():
    session = parse_portal_page(LOGIN_PAGE, "http://10.0.1.5/")

    assert session.state == PortalPageState.LOGIN_REQUIRED
    assert session.is_online is False
    assert session.logout_request is None


def test_stale_uid_does_not_override_login_page_state():
    html = LOGIN_PAGE.replace(
        "</script>",
        "uid='000000000000@glgd';</script>",
    )

    session = parse_portal_page(html, "http://10.0.1.5/")

    assert session.state == PortalPageState.LOGIN_REQUIRED
    assert session.is_online is False


def test_parse_unknown_page():
    session = parse_portal_page("<html><title>Gateway</title></html>", "http://10.0.1.5/")

    assert session.state == PortalPageState.UNKNOWN
    assert session.is_online is False


@pytest.mark.parametrize(
    ("raw", "account", "operator"),
    [
        ("20240001", "20240001", "校园网"),
        ("20240001@cmcc", "20240001", "中国移动"),
        ("20240001@unicom", "20240001", "中国联通"),
        ("20240001@telecom", "20240001", "中国电信"),
        ("20240001@glgd", "20240001", "中国广电"),
        ("20240001@future", "20240001", "未知运营商"),
        ("", "", ""),
    ],
)
def test_split_portal_account_operator_suffix(raw, account, operator):
    assert split_portal_account(raw) == (account, operator)
