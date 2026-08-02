use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PortalPageState {
    Online,
    LoginRequired,
    #[default]
    Unknown,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PortalLogoutRequest {
    pub url: String,
    pub method: String,
    pub data: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PortalSession {
    pub state: PortalPageState,
    pub user_id: String,
    pub ipv4: String,
    pub ipv6: String,
    pub logout_request: Option<PortalLogoutRequest>,
}

impl PortalSession {
    pub fn is_online(&self) -> bool {
        self.state == PortalPageState::Online
    }

    pub fn account_id(&self) -> String {
        split_portal_account(&self.user_id).0
    }

    pub fn operator_name(&self) -> String {
        split_portal_account(&self.user_id).1
    }
}

pub fn split_portal_account(user_id: &str) -> (String, String) {
    let raw = user_id.trim();
    if raw.is_empty() {
        return (String::new(), String::new());
    }

    let Some((account, suffix)) = raw.split_once('@') else {
        return (raw.to_owned(), "校园网".to_owned());
    };
    let operator = match suffix.to_ascii_lowercase().as_str() {
        "cmcc" => "中国移动",
        "unicom" => "中国联通",
        "telecom" => "中国电信",
        "glgd" => "中国广电",
        _ => "未知运营商",
    };
    (account.to_owned(), operator.to_owned())
}

pub fn parse_portal_page(html: &str, portal_url: &str) -> PortalSession {
    let title = capture(html, r"(?is)<title[^>]*>(.*?)</title>").unwrap_or_default();
    let user_id = script_value(html, "uid");
    let ipv4 = valid_ip_value(&script_value(html, "v4ip"));
    let ipv6 = valid_ip_value(&script_value(html, "v6ip"));

    let online = title.contains("注销")
        || html.contains("Dr.COMWebLoginID_1.htm")
        || is_match(html, r"(?i)\bpage\.run\s*\(\s*1\s*\)");
    let login_required = (title.contains("登录") && !title.contains("成功"))
        || html.contains("Dr.COMWebLoginID_0.htm")
        || is_match(html, r"(?i)\bpage\.run\s*\(\s*0\s*\)")
        || is_match(html, r#"(?i)<input[^>]+type\s*=\s*['\"]password['\"]"#);

    let state = if online {
        PortalPageState::Online
    } else if login_required {
        PortalPageState::LoginRequired
    } else {
        PortalPageState::Unknown
    };
    let logout_request = (state == PortalPageState::Online)
        .then(|| parse_logout_request(html, portal_url))
        .flatten();

    PortalSession {
        state,
        user_id,
        ipv4,
        ipv6,
        logout_request,
    }
}

fn parse_logout_request(html: &str, portal_url: &str) -> Option<PortalLogoutRequest> {
    let path = script_value(html, "authlogoutpath");
    if path.is_empty() {
        return None;
    }

    let mut url = if path.starts_with("http://") || path.starts_with("https://") {
        path
    } else {
        let portal = url::Url::parse(portal_url).ok()?;
        let host = non_empty(&script_value(html, "authlogoutIP"))
            .unwrap_or_else(|| portal.host_str().unwrap_or_default().to_owned());
        let port = script_value(html, "authlogoutport");
        let authority = if port.is_empty() || matches!(port.as_str(), "0" | "-1") {
            host
        } else {
            format!("{host}:{port}")
        };
        let normalized_path = if path.starts_with('/') {
            path
        } else {
            format!("/{path}")
        };
        format!("{}://{authority}{normalized_path}", portal.scheme())
    };

    let query = script_value(html, "authlogoutparam")
        .trim_start_matches(['?', '&'])
        .to_owned();
    if !query.is_empty() {
        url.push(if url.contains('?') { '&' } else { '?' });
        url.push_str(&query);
    }

    let data = script_value(html, "authlogoutpost");
    let method = if data.is_empty() { "GET" } else { "POST" };
    Some(PortalLogoutRequest {
        url,
        method: method.to_owned(),
        data,
    })
}

fn script_value(html: &str, name: &str) -> String {
    let name = regex::escape(name);
    let quoted = format!(r#"(?is)\b{name}\s*=\s*['\"]([^'\"]*)['\"]\s*;"#);
    if let Some(value) = capture(html, &quoted) {
        return value;
    }
    let numeric = format!(r"(?i)\b{name}\s*=\s*(-?\d+)\s*;");
    capture(html, &numeric).unwrap_or_default()
}

fn valid_ip_value(value: &str) -> String {
    let value = value.trim();
    if value.is_empty() || matches!(value, "0.0.0.0" | "000.000.000.000." | "::") {
        String::new()
    } else {
        value.to_owned()
    }
}

fn non_empty(value: &str) -> Option<String> {
    (!value.is_empty()).then(|| value.to_owned())
}

fn capture(input: &str, pattern: &str) -> Option<String> {
    Regex::new(pattern)
        .ok()?
        .captures(input)?
        .get(1)
        .map(|value| value.as_str().trim().to_owned())
}

fn is_match(input: &str, pattern: &str) -> bool {
    Regex::new(pattern).is_ok_and(|regex| regex.is_match(input))
}

#[cfg(test)]
mod tests {
    use super::*;

    const ONLINE_PAGE: &str = r#"
        <title>注销页</title><!--Dr.COMWebLoginID_1.htm--><script>
        uid='000000000000@glgd';v4ip='192.0.2.10';v6ip='2001:db8::1';
        authlogoutIP='';authlogoutport=801;
        authlogoutpath='/eportal/?c=ACSetting&a=Logout&ver=1.0';
        authlogoutparam='url=drappall';authlogoutpost='';
        </script><script>page.run(1);</script>
    "#;

    #[test]
    fn parses_online_session_and_logout_request() {
        let session = parse_portal_page(ONLINE_PAGE, "http://10.0.1.5/");
        assert!(session.is_online());
        assert_eq!(session.account_id(), "000000000000");
        assert_eq!(session.operator_name(), "中国广电");
        assert_eq!(session.ipv4, "192.0.2.10");
        assert_eq!(session.ipv6, "2001:db8::1");
        let logout = session.logout_request.unwrap();
        assert_eq!(logout.method, "GET");
        assert_eq!(
            logout.url,
            "http://10.0.1.5:801/eportal/?c=ACSetting&a=Logout&ver=1.0&url=drappall"
        );
    }

    #[test]
    fn stale_user_id_does_not_override_login_state() {
        let html = "<title>登录页</title><input type='password'><script>uid='x@cmcc';page.run(0);</script>";
        let session = parse_portal_page(html, "http://10.0.1.5/");
        assert_eq!(session.state, PortalPageState::LoginRequired);
        assert!(!session.is_online());
    }

    #[test]
    fn splits_operator_suffixes() {
        assert_eq!(
            split_portal_account("20240001@cmcc"),
            ("20240001".into(), "中国移动".into())
        );
        assert_eq!(
            split_portal_account("20240001"),
            ("20240001".into(), "校园网".into())
        );
        assert_eq!(split_portal_account(""), (String::new(), String::new()));
    }
}
