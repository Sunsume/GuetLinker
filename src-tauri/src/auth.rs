use std::{
    collections::BTreeMap,
    net::IpAddr,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};

use base64::{engine::general_purpose::STANDARD, Engine};
use regex::Regex;
use reqwest::{redirect::Policy, Client};
use scraper::{Html, Selector};
use serde::Serialize;
use serde_json::Value;
use url::Url;

use crate::{
    error::{AppError, AppResult},
    network::find_local_ipv6,
    portal::{parse_portal_page, PortalPageState, PortalSession},
};

const CAPTIVE_PROBE_URLS: [&str; 2] = ["http://1.1.1.1", "http://119.29.29.29"];
const USER_AGENT: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36";
const USERNAME_PATTERNS: [&str; 9] = [
    "username",
    "user_id",
    "DDDDD",
    "account",
    "userid",
    "stuId",
    "studentId",
    "login_name",
    "UserName",
];
const PASSWORD_PATTERNS: [&str; 7] = [
    "password",
    "upass",
    "pwd",
    "userPassword",
    "PassWord",
    "login_password",
    "Password",
];
const ISP_PATTERNS: [&str; 7] = [
    "ISP_select",
    "service",
    "operator",
    "isp",
    "ISP",
    "netType",
    "network_type",
];

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IspInfo {
    pub value: String,
    pub label: String,
    pub suffix: String,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ParsedForm {
    pub action_url: String,
    pub method: String,
    pub username_field: String,
    pub password_field: String,
    pub isp_field: String,
    pub isp_options: Vec<IspInfo>,
    pub default_isp_value: String,
    pub hidden_fields: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoginResult {
    pub success: bool,
    pub message: String,
    pub response_text: String,
    pub cancelled: bool,
    pub portal_session: Option<PortalSession>,
}

impl LoginResult {
    fn success(message: impl Into<String>, response_text: impl Into<String>) -> Self {
        Self {
            success: true,
            message: message.into(),
            response_text: response_text.into(),
            cancelled: false,
            portal_session: None,
        }
    }

    fn failure(message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
            response_text: String::new(),
            cancelled: false,
            portal_session: None,
        }
    }

    fn cancelled() -> Self {
        Self {
            cancelled: true,
            ..Self::failure("登录已取消")
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LogoutResult {
    pub success: bool,
    pub message: String,
}

#[derive(Clone)]
pub struct AuthService {
    client: Client,
    max_retries: u8,
    retry_delay: Duration,
}

pub fn is_definitive_credential_error(message: &str) -> bool {
    let lower = message.to_ascii_lowercase();
    let keywords = [
        "密码错误",
        "账号不存在",
        "用户不存在",
        "password_error",
        "user_not_found",
        "欠费",
        "停机",
        "锁定",
        "冻结",
        "余额不足",
        "销户",
        "限制登录",
    ];
    keywords.iter().any(|k| lower.contains(k))
}

impl AuthService {
    pub fn new() -> AppResult<Self> {
        let mut builder = Client::builder()
            .danger_accept_invalid_certs(true)
            .redirect(Policy::limited(5))
            .no_proxy()
            .user_agent(USER_AGENT)
            .timeout(Duration::from_secs(3));

        let local_ip = crate::network::find_local_ipv4();
        if let Ok(ip) = local_ip.parse::<IpAddr>() {
            builder = builder.local_address(Some(ip));
        }

        let client = builder.build()?;
        Ok(Self {
            client,
            max_retries: 3,
            retry_delay: Duration::from_secs(1),
        })
    }

    pub async fn login(
        &self,
        portal_url: &str,
        user_id: &str,
        password: &str,
        operator: &str,
        cancel: Arc<AtomicBool>,
    ) -> LoginResult {
        if user_id.trim().is_empty() || password.is_empty() {
            return LoginResult::failure("请输入学号和密码");
        }

        let account = account_with_isp_suffix(user_id, operator);
        let context = self.discover_redirect_context().await;
        let mut last_message = "服务器未确认登录成功".to_owned();

        for attempt in 1..=self.max_retries {
            if cancel.load(Ordering::Relaxed) {
                return LoginResult::cancelled();
            }

            if let Some(session) = self.verify_online(portal_url).await {
                return verified_login(session, &context, String::new());
            }

            let wireless = self
                .request_wireless_login(portal_url, &account, password, &context)
                .await;
            if !wireless.message.is_empty() {
                last_message = wireless.message.clone();
            }
            if wireless.success {
                if let Some(session) = self.wait_until_online(portal_url, &cancel).await {
                    return verified_login(session, &context, wireless.response_text);
                }
                last_message = "无线登录请求已被服务器接受，但门户仍未确认在线".into();
            } else if is_definitive_credential_error(&wireless.message) {
                return wireless;
            }

            if cancel.load(Ordering::Relaxed) {
                return LoginResult::cancelled();
            }

            let ethernet = self
                .request_ethernet_login(portal_url, &account, password, &context)
                .await;
            if !ethernet.message.is_empty() {
                last_message = ethernet.message.clone();
            }
            if ethernet.success {
                if let Some(session) = self.wait_until_online(portal_url, &cancel).await {
                    return verified_login(session, &context, ethernet.response_text);
                }
                last_message = "有线登录请求已被服务器接受，但门户仍未确认在线".into();
            } else if is_definitive_credential_error(&ethernet.message) {
                return ethernet;
            }

            if attempt < self.max_retries && wait_delay_or_cancel(self.retry_delay, &cancel).await {
                return LoginResult::cancelled();
            }
        }

        LoginResult::failure(format!(
            "登录失败，已重试 {} 次：{last_message}",
            self.max_retries
        ))
    }

    pub async fn portal_session(&self, portal_url: &str) -> Option<PortalSession> {
        let response = self
            .client
            .get(portal_url)
            .header("Cache-Control", "no-cache, no-store, max-age=0")
            .header("Pragma", "no-cache")
            .timeout(Duration::from_secs(2))
            .send()
            .await
            .ok()?;
        if !response.status().is_success() {
            return None;
        }
        let response_url = response.url().clone();
        let html = response.text().await.ok()?;
        let base_url = if response_url.as_str().is_empty() {
            portal_url
        } else {
            response_url.as_str()
        };
        Some(parse_portal_page(&html, base_url))
    }

    pub async fn logout(&self, portal_url: &str, session: Option<PortalSession>) -> LogoutResult {
        let current = match session {
            Some(value) if value.is_online() => value,
            _ => match self.portal_session(portal_url).await {
                Some(value) => value,
                None => PortalSession::default(),
            },
        };

        if current.state == PortalPageState::LoginRequired {
            return logout_success("当前已经断开");
        }

        let mut logged_out = false;

        // 1. Try logout request parsed from the online session
        if let Some(request) = &current.logout_request {
            let response = if request.method == "POST" {
                self.client
                    .post(&request.url)
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .body(request.data.clone())
                    .send()
                    .await
            } else {
                self.client.get(&request.url).send().await
            };
            if let Ok(value) = response {
                // Dr.COM logout typically responds with a 302 redirect back to login page or 200 OK
                if value.status().is_success() || value.status().is_redirection() {
                    logged_out = true;
                }
            }
        }

        // 2. Fallback to standard Dr.COM endpoints if not yet confirmed
        if !logged_out {
            if let Ok(portal) = url::Url::parse(portal_url) {
                let origin = format!("{}://{}", portal.scheme(), portal.host_str().unwrap_or("10.0.1.5"));
                let candidates = [
                    format!("{origin}/F.htm"),
                    format!("{origin}:801/eportal/portal/logout"),
                    format!("{origin}/eportal/portal/logout"),
                ];
                for candidate in candidates {
                    if let Ok(res) = self.client.get(&candidate).timeout(Duration::from_millis(1500)).send().await {
                        if res.status().is_success() || res.status().is_redirection() {
                            logged_out = true;
                            break;
                        }
                    }
                }
            }
        }

        // 3. Check portal session verification if reachable
        if let Some(value) = self.portal_session(portal_url).await {
            if value.state == PortalPageState::LoginRequired {
                return logout_success("校园网已断开");
            }
            if value.is_online() && !logged_out {
                return logout_failure("注销请求已发送，但门户仍显示在线");
            }
        }

        logout_success("校园网已断开")
    }

    pub async fn isp_options(&self, portal_url: &str) -> AppResult<Vec<IspInfo>> {
        let response = self
            .client
            .get(portal_url)
            .send()
            .await?
            .error_for_status()?;
        let html = response.text().await?;
        Ok(parse_form(&html, portal_url).isp_options)
    }

    async fn request_wireless_login(
        &self,
        portal_url: &str,
        account: &str,
        password: &str,
        context: &BTreeMap<String, String>,
    ) -> LoginResult {
        let endpoint = match portal_endpoint(portal_url, "/eportal/portal/login", Some(801)) {
            Ok(value) => value,
            Err(error) => return LoginResult::failure(error.to_string()),
        };
        let mut params = vec![
            ("callback".to_owned(), "dr1003".to_owned()),
            ("login_method".to_owned(), "1".to_owned()),
            ("user_account".to_owned(), format!(",0,{account}")),
            ("user_password".to_owned(), STANDARD.encode(password)),
        ];
        params.extend(
            context
                .iter()
                .map(|(key, value)| (key.clone(), value.clone())),
        );
        endpoint_login_result(
            self.client
                .get(endpoint)
                .query(&params)
                .timeout(Duration::from_millis(2000))
                .send()
                .await,
            "无线",
        )
        .await
    }

    async fn request_ethernet_login(
        &self,
        portal_url: &str,
        account: &str,
        password: &str,
        context: &BTreeMap<String, String>,
    ) -> LoginResult {
        let endpoint = match portal_endpoint(portal_url, "/drcom/login", None) {
            Ok(value) => value,
            Err(error) => return LoginResult::failure(error.to_string()),
        };
        let mut params = vec![
            ("callback".to_owned(), "dr1003".to_owned()),
            ("DDDDD".to_owned(), account.to_owned()),
            ("upass".to_owned(), password.to_owned()),
        ];
        params.extend(
            context
                .iter()
                .map(|(key, value)| (key.clone(), value.clone())),
        );
        params.push(("0MKKey".to_owned(), "123456".to_owned()));
        endpoint_login_result(
            self.client
                .get(endpoint)
                .query(&params)
                .timeout(Duration::from_millis(2000))
                .send()
                .await,
            "有线",
        )
        .await
    }

    async fn verify_online(&self, portal_url: &str) -> Option<PortalSession> {
        self.portal_session(portal_url)
            .await
            .filter(PortalSession::is_online)
    }

    async fn wait_until_online(
        &self,
        portal_url: &str,
        cancel: &AtomicBool,
    ) -> Option<PortalSession> {
        let deadline = Instant::now() + Duration::from_millis(2500);
        loop {
            if let Some(session) = self.verify_online(portal_url).await {
                return Some(session);
            }
            if cancel.load(Ordering::Relaxed) || Instant::now() >= deadline {
                return None;
            }
            tokio::time::sleep(Duration::from_millis(350)).await;
        }
    }

    async fn discover_redirect_context(&self) -> BTreeMap<String, String> {
        for url in CAPTIVE_PROBE_URLS {
            let response = self
                .client
                .get(url)
                .timeout(Duration::from_millis(800))
                .send()
                .await;
            let Ok(response) = response else {
                continue;
            };
            let Some(location) = response.headers().get(reqwest::header::LOCATION) else {
                continue;
            };
            let Ok(location) = location.to_str() else {
                continue;
            };
            let context = parse_redirect_context(location);
            if !context.is_empty() {
                return context;
            }
        }
        BTreeMap::new()
    }
}

pub fn parse_form(html: &str, portal_url: &str) -> ParsedForm {
    let document = Html::parse_document(html);
    let form_selector = selector("form");
    let input_selector = selector("input");
    let select_selector = selector("select");
    let option_selector = selector("option");
    let forms: Vec<_> = document.select(&form_selector).collect();
    let form_node = forms
        .iter()
        .copied()
        .find(|form| {
            form.select(&input_selector).any(|input| {
                input
                    .value()
                    .attr("type")
                    .is_some_and(|kind| kind.eq_ignore_ascii_case("password"))
            })
        })
        .or_else(|| forms.first().copied());

    let mut parsed = ParsedForm {
        action_url: portal_url.to_owned(),
        method: "POST".into(),
        ..ParsedForm::default()
    };

    if let Some(form) = form_node {
        parsed.action_url = resolve_action_url(portal_url, form.value().attr("action"));
        parsed.method = form
            .value()
            .attr("method")
            .unwrap_or("POST")
            .to_ascii_uppercase();

        for input in form.select(&input_selector) {
            let Some(name) = input.value().attr("name") else {
                continue;
            };
            let input_type = input
                .value()
                .attr("type")
                .unwrap_or("text")
                .to_ascii_lowercase();
            match input_type.as_str() {
                "hidden" => {
                    parsed.hidden_fields.insert(
                        name.to_owned(),
                        input.value().attr("value").unwrap_or_default().to_owned(),
                    );
                }
                "password" => parsed.password_field = name.to_owned(),
                "text" | "tel" | "email"
                    if parsed.username_field.is_empty() || looks_like_username(name) =>
                {
                    parsed.username_field = name.to_owned();
                }
                _ => {}
            }
        }

        for select in form.select(&select_selector) {
            let name = select.value().attr("name").unwrap_or_default();
            if !parsed.isp_field.is_empty() && !looks_like_isp(name) {
                continue;
            }
            parsed.isp_field = name.to_owned();
            parsed.isp_options.clear();
            for option in select.select(&option_selector) {
                let value = option.value().attr("value").unwrap_or_default().trim();
                if value.is_empty() {
                    continue;
                }
                let label = option.text().collect::<String>().trim().to_owned();
                parsed.isp_options.push(IspInfo {
                    value: value.to_owned(),
                    label,
                    suffix: String::new(),
                });
                if parsed.default_isp_value.is_empty() || option.value().attr("selected").is_some()
                {
                    parsed.default_isp_value = value.to_owned();
                }
            }
        }
    }

    if parsed.isp_options.is_empty() {
        let (options, default_value) = parse_carrier_options(html);
        parsed.isp_options = options;
        parsed.default_isp_value = default_value;
    }
    if parsed.username_field.is_empty() {
        parsed.username_field = find_field_name(html, &USERNAME_PATTERNS);
    }
    if parsed.password_field.is_empty() {
        parsed.password_field = find_field_name(html, &PASSWORD_PATTERNS);
    }
    if parsed.isp_field.is_empty() {
        parsed.isp_field = find_field_name(html, &ISP_PATTERNS);
    }
    parsed
}

pub fn check_login_result(response_text: &str) -> LoginResult {
    let jsonp = Regex::new(r"(?s)^[^(]*\(\s*(\{.*\})\s*\)\s*;?\s*$").expect("valid JSONP regex");
    if let Some(payload) = jsonp
        .captures(response_text.trim())
        .and_then(|captures| captures.get(1))
        .and_then(|capture| serde_json::from_str::<Value>(capture.as_str()).ok())
    {
        if let Some(result) = payload.get("result") {
            let success = matches!(result, Value::Bool(true))
                || result.as_i64() == Some(1)
                || result
                    .as_str()
                    .is_some_and(|value| matches!(value, "1" | "true"));
            let message = payload
                .get("msg")
                .or_else(|| payload.get("message"))
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .unwrap_or(if success {
                    "登录成功"
                } else {
                    "服务器拒绝登录"
                });
            let mut login = if success {
                LoginResult::success(message, response_text)
            } else {
                LoginResult::failure(message)
            };
            login.response_text = response_text.to_owned();
            return login;
        }
    }

    let lower = response_text.to_lowercase();
    if [
        "成功",
        "success",
        "已登录",
        "登录成功",
        "welcome",
        "loginsuccess",
        "already_online",
    ]
    .iter()
    .any(|keyword| lower.contains(&keyword.to_lowercase()))
    {
        return LoginResult::success("登录成功", response_text);
    }
    let failures = [
        "password_error",
        "user_not_found",
        "密码错误",
        "账号不存在",
        "失败",
        "错误",
        "error",
        "fail",
    ];
    if let Some(keyword) = failures
        .iter()
        .find(|keyword| lower.contains(&keyword.to_lowercase()))
    {
        return LoginResult::failure(format!("登录失败: {keyword}"));
    }
    LoginResult::failure("无法确认登录是否成功")
}

pub fn account_with_isp_suffix(user_id: &str, operator: &str) -> String {
    let suffix = match operator {
        "2" | "中国移动" => "@cmcc",
        "3" | "中国联通" => "@unicom",
        "4" | "中国电信" => "@telecom",
        "5" | "中国广电" => "@glgd",
        _ => "",
    };
    let suffix_regex = Regex::new(r"(?i)@(cmcc|unicom|telecom|glgd)$").expect("valid suffix regex");
    let account = suffix_regex.replace(user_id.trim(), "");
    format!("{account}{suffix}")
}

fn parse_carrier_options(html: &str) -> (Vec<IspInfo>, String) {
    let assignment =
        Regex::new(r#"(?is)\bcarrier\s*=\s*(['\"])(.*?)['\"]\s*;"#).expect("valid carrier regex");
    let Some(payload) = assignment
        .captures(html)
        .and_then(|captures| captures.get(2))
        .map(|capture| capture.as_str())
    else {
        return (Vec::new(), String::new());
    };
    let data_regex =
        Regex::new(r#"(?is)[\"']data[\"']\s*:\s*(\[[^\]]*\])"#).expect("valid carrier data regex");
    let Some(data) = data_regex
        .captures(payload)
        .and_then(|captures| captures.get(1))
    else {
        return (Vec::new(), String::new());
    };
    let carriers = serde_json::from_str::<Vec<Value>>(data.as_str()).unwrap_or_default();
    let mut options: Vec<IspInfo> = carriers
        .into_iter()
        .filter_map(|carrier| {
            let value = carrier.get("id")?.as_str()?.trim();
            let label = carrier.get("name")?.as_str()?.trim();
            if value.is_empty() || label.is_empty() {
                return None;
            }
            Some(IspInfo {
                value: value.to_owned(),
                label: label.to_owned(),
                suffix: carrier
                    .get("suffix")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .trim()
                    .to_owned(),
            })
        })
        .collect();

    let guet_portal = html.contains("桂林电子科技大学") || html.contains("@glgd");
    let has_broadnet = options
        .iter()
        .any(|option| option.suffix.eq_ignore_ascii_case("@glgd") || option.label.contains("广电"));
    if guet_portal && !has_broadnet {
        let mut next_value = 5;
        while options
            .iter()
            .any(|option| option.value == next_value.to_string())
        {
            next_value += 1;
        }
        options.push(IspInfo {
            value: next_value.to_string(),
            label: "中国广电".into(),
            suffix: "@glgd".into(),
        });
    }

    let default_regex = Regex::new(r#"(?is)[\"']defaultID[\"']\s*:\s*[\"']([^\"']*)[\"']"#)
        .expect("valid default carrier regex");
    let advertised_default = default_regex
        .captures(payload)
        .and_then(|captures| captures.get(1))
        .map(|capture| capture.as_str().trim())
        .unwrap_or_default();
    let default_value = options
        .iter()
        .find(|option| option.value == advertised_default)
        .or_else(|| options.first())
        .map(|option| option.value.clone())
        .unwrap_or_default();
    (options, default_value)
}

fn parse_redirect_context(location: &str) -> BTreeMap<String, String> {
    let Ok(url) = Url::parse(location) else {
        return BTreeMap::new();
    };
    let query: BTreeMap<String, String> = url
        .query_pairs()
        .map(|(key, value)| (key.to_ascii_lowercase(), value.into_owned()))
        .collect();
    let fields: [(&str, &[&str]); 5] = [
        (
            "wlan_user_ip",
            &[
                "wlanuserip",
                "ip",
                "userip",
                "user-ip",
                "client_ip",
                "uip",
                "station_ip",
            ],
        ),
        ("wlan_user_ipv6", &["wlanuseripv6", "userv6ip"]),
        (
            "wlan_user_mac",
            &[
                "wlanusermac",
                "mac",
                "usermac",
                "user-mac",
                "client_mac",
                "station_mac",
            ],
        ),
        (
            "wlan_ac_ip",
            &["wlanacip", "acip", "switchip", "nasip", "nas-ip"],
        ),
        (
            "wlan_ac_name",
            &["wlanacname", "sysname", "nasname", "nas-name"],
        ),
    ];
    fields
        .into_iter()
        .filter_map(|(target, aliases)| {
            let value = aliases.iter().find_map(|alias| query.get(*alias))?;
            let normalized = if target == "wlan_user_mac" {
                value.replace(['-', ':'], "")
            } else {
                value.clone()
            };
            (!normalized.is_empty()).then(|| (target.to_owned(), normalized))
        })
        .collect()
}

fn verified_login(
    mut session: PortalSession,
    context: &BTreeMap<String, String>,
    response_text: String,
) -> LoginResult {
    if session.ipv4.is_empty() {
        session.ipv4 = context.get("wlan_user_ip").cloned().unwrap_or_default();
    }
    if session.ipv6.is_empty() {
        session.ipv6 = context
            .get("wlan_user_ipv6")
            .cloned()
            .unwrap_or_else(|| find_local_ipv6(&session.ipv4));
    }
    let mut result = LoginResult::success("登录成功", response_text);
    result.portal_session = Some(session);
    result
}

async fn endpoint_login_result(
    response: Result<reqwest::Response, reqwest::Error>,
    connection_type: &str,
) -> LoginResult {
    let response = match response {
        Ok(value) => value,
        Err(error) => {
            return LoginResult::failure(format!("{connection_type}登录请求失败: {error}"))
        }
    };
    if !response.status().is_success() {
        return LoginResult::failure(format!(
            "{connection_type}登录请求失败: HTTP {}",
            response.status()
        ));
    }
    match response.text().await {
        Ok(text) => check_login_result(&text),
        Err(error) => LoginResult::failure(format!("{connection_type}登录响应读取失败: {error}")),
    }
}

fn portal_endpoint(portal_url: &str, path: &str, port: Option<u16>) -> AppResult<Url> {
    let mut url =
        Url::parse(portal_url).map_err(|_| AppError::Validation("校园网门户地址无效".into()))?;
    url.set_path(path);
    url.set_query(None);
    url.set_fragment(None);
    url.set_port(port)
        .map_err(|_| AppError::Validation("校园网门户端口无效".into()))?;
    Ok(url)
}

fn resolve_action_url(portal_url: &str, action: Option<&str>) -> String {
    let action = action.unwrap_or_default().trim();
    if action.is_empty() {
        return portal_url.to_owned();
    }
    Url::parse(portal_url)
        .and_then(|base| base.join(action))
        .map(|url| url.into())
        .unwrap_or_else(|_| action.to_owned())
}

fn looks_like_username(name: &str) -> bool {
    let lower = name.to_ascii_lowercase();
    ["user", "account", "ddddd", "stuid", "login"]
        .iter()
        .any(|pattern| lower.contains(pattern))
}

fn looks_like_isp(name: &str) -> bool {
    let lower = name.to_ascii_lowercase();
    ["isp", "service", "operator", "nettype", "network"]
        .iter()
        .any(|pattern| lower.contains(pattern))
}

fn find_field_name(html: &str, patterns: &[&str]) -> String {
    for pattern in patterns {
        let escaped = regex::escape(pattern);
        let regex = Regex::new(&format!(r#"(?i)name\s*=\s*[\"']?({escaped})[\"']?"#))
            .expect("escaped field regex is valid");
        if let Some(value) = regex.captures(html).and_then(|captures| captures.get(1)) {
            return value.as_str().to_owned();
        }
    }
    patterns.first().copied().unwrap_or_default().to_owned()
}

fn selector(value: &str) -> Selector {
    Selector::parse(value).expect("static selector is valid")
}

async fn wait_delay_or_cancel(delay: Duration, cancel: &AtomicBool) -> bool {
    let deadline = Instant::now() + delay;
    while Instant::now() < deadline {
        if cancel.load(Ordering::Relaxed) {
            return true;
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        tokio::time::sleep(remaining.min(Duration::from_millis(50))).await;
    }
    cancel.load(Ordering::Relaxed)
}

fn logout_success(message: &str) -> LogoutResult {
    LogoutResult {
        success: true,
        message: message.into(),
    }
}

fn logout_failure(message: &str) -> LogoutResult {
    LogoutResult {
        success: false,
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_password_form_and_javascript_carriers() {
        let html = r#"
            <form action="/search"><input name="q"></form>
            <form action="/login" method="post">
              <input type="hidden" name="token" value="abc">
              <input name="DDDDD"><input type="password" name="upass">
            </form>
            <script>carrier='{"data":[{"id":"1","name":"校园网","suffix":""},{"id":"2","name":"中国移动","suffix":"@cmcc"}],"defaultID":"2"}';</script>
        "#;
        let form = parse_form(html, "http://10.0.1.5/");
        assert_eq!(form.action_url, "http://10.0.1.5/login");
        assert_eq!(form.username_field, "DDDDD");
        assert_eq!(form.password_field, "upass");
        assert_eq!(
            form.hidden_fields.get("token").map(String::as_str),
            Some("abc")
        );
        assert_eq!(form.default_isp_value, "2");
        assert_eq!(form.isp_options.len(), 2);
    }

    #[test]
    fn completes_guet_carriers_with_broadnet() {
        let html = r#"桂林电子科技大学<script>carrier='{"data":[{"id":"1","name":"校园网","suffix":""}],"defaultID":"1"}';</script>"#;
        let form = parse_form(html, "http://10.0.1.5/");
        assert!(form
            .isp_options
            .iter()
            .any(|option| option.suffix == "@glgd"));
    }

    #[test]
    fn parses_jsonp_result_without_treating_plain_html_as_success() {
        assert!(check_login_result(r#"dr1003({"result":1,"msg":"ok"})"#).success);
        assert!(!check_login_result(r#"dr1003({"result":0,"msg":"密码错误"})"#).success);
        assert!(!check_login_result("<html>登录页面</html>").success);
    }

    #[test]
    fn normalizes_account_suffix_and_redirect_context() {
        assert_eq!(
            account_with_isp_suffix("2024@unicom", "中国移动"),
            "2024@cmcc"
        );
        let context = parse_redirect_context(
            "http://10.0.1.5/?wlanuserip=192.0.2.4&mac=AA-BB-CC-DD-EE-FF&nasip=10.0.0.1",
        );
        assert_eq!(
            context.get("wlan_user_ip").map(String::as_str),
            Some("192.0.2.4")
        );
        assert_eq!(
            context.get("wlan_user_mac").map(String::as_str),
            Some("AABBCCDDEEFF")
        );
        assert_eq!(
            context.get("wlan_ac_ip").map(String::as_str),
            Some("10.0.0.1")
        );
    }
}
