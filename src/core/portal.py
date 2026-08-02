"""Parsing helpers for the GUET Dr.COM portal page.

The portal exposes session details and logout configuration as JavaScript
variables. This module converts those values into typed application state
without relying on account credentials or reading a password from the page.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


PORTAL_OPERATOR_NAMES = {
    "@cmcc": "中国移动",
    "@unicom": "中国联通",
    "@telecom": "中国电信",
    "@glgd": "中国广电",
}


class PortalPageState(enum.Enum):
    """Authentication state represented by a portal page."""

    ONLINE = "online"
    LOGIN_REQUIRED = "login_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PortalLogoutRequest:
    """Logout request advertised by the portal page."""

    url: str
    method: str = "GET"
    data: str = ""


@dataclass(frozen=True)
class PortalSession:
    """Public session information exposed by the portal."""

    state: PortalPageState = PortalPageState.UNKNOWN
    user_id: str = ""
    ipv4: str = ""
    ipv6: str = ""
    logout_request: PortalLogoutRequest | None = None

    @property
    def is_online(self) -> bool:
        return self.state == PortalPageState.ONLINE

    @property
    def account_id(self) -> str:
        """Account portion before the operator suffix."""
        return split_portal_account(self.user_id)[0]

    @property
    def operator_name(self) -> str:
        """Chinese operator name derived from the public account suffix."""
        return split_portal_account(self.user_id)[1]


def split_portal_account(user_id: str) -> tuple[str, str]:
    """Split ``account@operator`` without exposing the suffix in account UI."""
    raw = user_id.strip()
    if not raw:
        return "", ""
    account, separator, suffix = raw.partition("@")
    if not separator:
        return account, "校园网"
    operator = PORTAL_OPERATOR_NAMES.get(
        f"@{suffix.lower()}",
        "未知运营商",
    )
    return account, operator


def parse_portal_page(html: str, portal_url: str) -> PortalSession:
    """Parse online state, public session details, and logout configuration."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    user_id = _script_value(html, "uid")
    ipv4 = _valid_ip_value(_script_value(html, "v4ip"))
    ipv6 = _valid_ip_value(_script_value(html, "v6ip"))

    # Only authoritative page-state markers prove that the campus session is
    # online. ``uid`` can remain populated briefly after logout and therefore
    # is session metadata, not a success condition by itself.
    online_markers = (
        "注销" in title,
        "Dr.COMWebLoginID_1.htm" in html,
        bool(re.search(r"\bpage\.run\s*\(\s*1\s*\)", html)),
    )
    login_markers = (
        "登录" in title and "成功" not in title,
        "Dr.COMWebLoginID_0.htm" in html,
        bool(re.search(r"\bpage\.run\s*\(\s*0\s*\)", html)),
        bool(re.search(r"<input[^>]+type\s*=\s*['\"]password['\"]", html, re.IGNORECASE)),
    )

    if any(online_markers):
        state = PortalPageState.ONLINE
    elif any(login_markers):
        state = PortalPageState.LOGIN_REQUIRED
    else:
        state = PortalPageState.UNKNOWN

    logout_request = _parse_logout_request(html, portal_url) if state == PortalPageState.ONLINE else None
    return PortalSession(
        state=state,
        user_id=user_id,
        ipv4=ipv4,
        ipv6=ipv6,
        logout_request=logout_request,
    )


def _parse_logout_request(html: str, portal_url: str) -> PortalLogoutRequest | None:
    path = _script_value(html, "authlogoutpath")
    if not path:
        return None

    if path.lower().startswith(("http://", "https://")):
        url = path
    else:
        portal = urlsplit(portal_url)
        host = _script_value(html, "authlogoutIP") or portal.hostname or ""
        port = _script_value(html, "authlogoutport")
        netloc = host
        if port and port not in ("0", "-1"):
            netloc = f"{host}:{port}"
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = urlunsplit((portal.scheme or "http", netloc, normalized_path, "", ""))

    query = _script_value(html, "authlogoutparam").lstrip("?&")
    if query:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    post_data = _script_value(html, "authlogoutpost")
    method = "POST" if post_data else "GET"
    return PortalLogoutRequest(url=url, method=method, data=post_data)


def _script_value(html: str, name: str) -> str:
    quoted = re.search(
        rf"\b{re.escape(name)}\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)\s*;",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if quoted:
        return quoted.group("value").strip()

    numeric = re.search(
        rf"\b{re.escape(name)}\s*=\s*(?P<value>-?\d+)\s*;",
        html,
        re.IGNORECASE,
    )
    return numeric.group("value").strip() if numeric else ""


def _valid_ip_value(value: str) -> str:
    value = value.strip()
    if not value or value in {"0.0.0.0", "000.000.000.000.", "::"}:
        return ""
    return value
