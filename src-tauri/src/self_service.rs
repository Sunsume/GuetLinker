use std::{
    net::IpAddr,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use base64::{engine::general_purpose::STANDARD, Engine};
use chrono::NaiveDate;
use md5::{Digest, Md5};
use regex::Regex;
use reqwest::Client;
use scraper::{ElementRef, Html, Selector};
use serde::Serialize;
use serde_json::{Map, Value};
use url::Url;

use crate::error::{AppError, AppResult};

pub const SELF_SERVICE_URL: &str = "https://nicdrcom.guet.edu.cn/Self/";
const USER_AGENT: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36";

#[derive(Clone, Debug, PartialEq, Eq)]
struct LoginPage {
    action_url: String,
    checkcode: String,
    captcha_required: bool,
    error_message: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelfServiceSession {
    pub account: String,
    pub display_name: String,
    pub landing_url: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelfServiceLoginResult {
    pub success: bool,
    pub message: String,
    pub captcha_required: bool,
    pub captcha_image: String,
    pub session: Option<SelfServiceSession>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountOverview {
    pub status: String,
    pub anomaly_info: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TrafficSummary {
    pub start_date: String,
    pub end_date: String,
    pub international_up_mb: f64,
    pub international_down_mb: f64,
    pub domestic_up_mb: f64,
    pub domestic_down_mb: f64,
}

pub struct SelfServiceClient {
    base_url: Url,
    client: Client,
    pending_page: Option<LoginPage>,
    pending_account: String,
}

impl SelfServiceClient {
    pub fn new() -> AppResult<Self> {
        Self::with_base_url(SELF_SERVICE_URL)
    }

    pub fn with_base_url(base_url: &str) -> AppResult<Self> {
        let base_url = normalized_base_url(base_url)?;
        Ok(Self {
            base_url,
            client: build_client()?,
            pending_page: None,
            pending_account: String::new(),
        })
    }

    pub async fn login(
        &mut self,
        account: &str,
        password: &str,
        captcha: &str,
    ) -> SelfServiceLoginResult {
        let account = account.trim();
        if account.is_empty() || password.is_empty() {
            return login_failure("请输入学号和密码");
        }

        let page = if self.pending_account.is_empty() || self.pending_account == account {
            self.pending_page.clone()
        } else {
            None
        };
        let page = match page {
            Some(value) => value,
            None => match self.fetch_login_page().await {
                Ok(value) => {
                    self.pending_page = Some(value.clone());
                    self.pending_account = account.to_owned();
                    value
                }
                Err(error) => return login_failure(error.to_string()),
            },
        };

        if page.captcha_required && captcha.trim().is_empty() {
            return self.captcha_result("请输入验证码").await;
        }

        let password_hash = Md5::digest(password.as_bytes())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let payload = [
            ("foo", ""),
            ("bar", ""),
            ("checkcode", page.checkcode.as_str()),
            ("account", account),
            ("password", password_hash.as_str()),
            ("code", captcha.trim()),
            ("submit", ""),
        ];
        let response = self
            .client
            .post(&page.action_url)
            .form(&payload)
            .send()
            .await;
        let response = match response {
            Ok(value) => value,
            Err(error) if error.is_timeout() => {
                return login_failure("自助服务系统响应超时，请稍后重试")
            }
            Err(_) => return login_failure("无法连接校园网自助服务系统"),
        };
        if !response.status().is_success() {
            return login_failure("无法连接校园网自助服务系统");
        }
        let response_url = response.url().clone();
        let html = match response.text().await {
            Ok(value) => value,
            Err(_) => return login_failure("自助服务系统返回了无法识别的数据"),
        };

        if is_authenticated_response(&response_url, &html) {
            self.pending_page = None;
            self.pending_account.clear();
            return SelfServiceLoginResult {
                success: true,
                message: "自助服务登录成功".into(),
                captcha_required: false,
                captcha_image: String::new(),
                session: Some(SelfServiceSession {
                    account: account.to_owned(),
                    display_name: parse_display_name(&html, account),
                    landing_url: response_url.into(),
                }),
            };
        }

        let next_page = match parse_login_page(&html, response_url.as_str()) {
            Ok(value) => value,
            Err(error) => return login_failure(error.to_string()),
        };
        let message = if next_page.error_message.is_empty() {
            "账号、密码或验证码不正确".to_owned()
        } else {
            next_page.error_message.clone()
        };
        let captcha_required = next_page.captcha_required;
        self.pending_page = Some(next_page);
        self.pending_account = account.to_owned();
        if captcha_required {
            return self.captcha_result(&message).await;
        }
        login_failure(message)
    }

    pub async fn prepare_login(&mut self, account: &str) -> AppResult<String> {
        self.reset()?;
        let page = self.fetch_login_page().await?;
        self.pending_page = Some(page);
        self.pending_account = account.trim().to_owned();
        self.captcha_image().await
    }

    pub async fn captcha_image(&self) -> AppResult<String> {
        let image = self.fetch_captcha().await?;
        Ok(STANDARD.encode(image))
    }

    pub async fn account_overview(&self) -> AppResult<AccountOverview> {
        let dashboard_url = self.base_url.join("dashboard").map_err(invalid_url)?;
        let dashboard = self
            .client
            .get(dashboard_url)
            .send()
            .await?
            .error_for_status()?;
        ensure_authenticated_url(dashboard.url())?;
        let dashboard_html = dashboard.text().await?;

        let person_url = self
            .base_url
            .join("setting/personList")
            .map_err(invalid_url)?;
        let person = self
            .client
            .get(person_url)
            .send()
            .await?
            .error_for_status()?;
        ensure_authenticated_url(person.url())?;
        let person_html = person.text().await?;

        Ok(AccountOverview {
            status: parse_account_status(&dashboard_html)?,
            anomaly_info: parse_anomaly_info(&person_html)?,
        })
    }

    pub async fn traffic(&self, start_date: &str, end_date: &str) -> AppResult<TrafficSummary> {
        validate_date_range(start_date, end_date)?;
        let endpoint = self
            .base_url
            .join("bill/getUserOnlineLog")
            .map_err(invalid_url)?;
        let response = self
            .client
            .get(endpoint)
            .query(&[
                ("pageSize", "10"),
                ("pageNumber", "1"),
                ("sortName", "loginTime"),
                ("sortOrder", "DESC"),
                ("startTime", start_date),
                ("endTime", end_date),
            ])
            .send()
            .await?
            .error_for_status()?;
        ensure_authenticated_url(response.url())?;
        let payload = response.json::<Value>().await?;
        parse_traffic_summary(payload, start_date, end_date)
    }

    pub fn reset(&mut self) -> AppResult<()> {
        self.client = build_client()?;
        self.pending_page = None;
        self.pending_account.clear();
        Ok(())
    }

    async fn fetch_login_page(&self) -> AppResult<LoginPage> {
        let url = self.base_url.join("login/").map_err(invalid_url)?;
        let response = self.client.get(url).send().await?.error_for_status()?;
        let page_url = response.url().clone();
        let html = response.text().await?;
        parse_login_page(&html, page_url.as_str())
    }

    async fn fetch_captcha(&self) -> AppResult<Vec<u8>> {
        let endpoint = self
            .base_url
            .join("login/randomCode")
            .map_err(invalid_url)?;
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64();
        let response = self
            .client
            .get(endpoint)
            .query(&[("t", format!("{timestamp:.6}"))])
            .send()
            .await?
            .error_for_status()?;
        Ok(response.bytes().await?.to_vec())
    }

    async fn captcha_result(&self, message: &str) -> SelfServiceLoginResult {
        match self.captcha_image().await {
            Ok(image) => SelfServiceLoginResult {
                success: false,
                message: message.into(),
                captcha_required: true,
                captcha_image: image,
                session: None,
            },
            Err(_) => SelfServiceLoginResult {
                success: false,
                message: format!("{message}；验证码图片加载失败，请刷新"),
                captcha_required: true,
                captcha_image: String::new(),
                session: None,
            },
        }
    }
}

fn build_client() -> AppResult<Client> {
    let mut builder = Client::builder()
        .danger_accept_invalid_certs(true)
        .cookie_store(true)
        .no_proxy()
        .user_agent(USER_AGENT)
        .timeout(Duration::from_secs(8));

    let local_ip = crate::network::find_local_ipv4();
    if let Ok(ip) = local_ip.parse::<IpAddr>() {
        builder = builder.local_address(Some(ip));
    }

    Ok(builder.build()?)
}

fn normalized_base_url(base_url: &str) -> AppResult<Url> {
    let normalized = format!("{}/", base_url.trim_end_matches('/'));
    Url::parse(&normalized).map_err(invalid_url)
}

fn parse_login_page(html: &str, page_url: &str) -> AppResult<LoginPage> {
    let document = Html::parse_document(html);
    let form = document
        .select(&selector("form"))
        .next()
        .ok_or_else(|| AppError::Protocol("自助服务登录页格式已变化".into()))?;
    let action = form.value().attr("action").unwrap_or_default().trim();
    let action_url = Url::parse(page_url)
        .and_then(|url| url.join(action))
        .map_err(invalid_url)?
        .to_string();
    let checkcode = form
        .select(&selector("input[name=\"checkcode\"]"))
        .next()
        .and_then(|input| input.value().attr("value"))
        .unwrap_or_default()
        .trim()
        .to_owned();
    let random_div = document.select(&selector("#randomDiv")).next();
    let visible_captcha = random_div.is_some_and(|element| {
        !element
            .value()
            .classes()
            .any(|class_name| class_name == "hide")
    });
    let error_message = parse_error_message(&document);
    let captcha_required = visible_captcha || error_message.contains("验证码");
    Ok(LoginPage {
        action_url,
        checkcode,
        captcha_required,
        error_message,
    })
}

fn parse_error_message(document: &Html) -> String {
    if let Some(error_box) = document.select(&selector("#errorTip")).next() {
        let direct = element_text(error_box);
        if !direct.is_empty() {
            return direct;
        }
    }

    let injection = Regex::new(r#"(?s)\}\)\(\s*(['\"])(.*?)['\"]\s*\)\s*;"#)
        .expect("valid error injection regex");
    for script in document.select(&selector("script")) {
        let text = script.text().collect::<String>();
        if !text.contains("#errorTip") {
            continue;
        }
        let Some(value) = injection
            .captures_iter(&text)
            .last()
            .and_then(|captures| captures.get(2))
        else {
            continue;
        };
        return html_escape::decode_html_entities(value.as_str())
            .replace(r"\'", "'")
            .replace(r#"\""#, "\"")
            .replace(r"\n", " ")
            .trim()
            .to_owned();
    }
    String::new()
}

fn is_authenticated_response(url: &Url, html: &str) -> bool {
    let path = url.path().to_ascii_lowercase();
    if path.trim_end_matches('/').ends_with("/login") {
        return false;
    }
    let document = Html::parse_document(html);
    !document
        .select(&selector("form"))
        .filter_map(|form| form.value().attr("action"))
        .any(|action| action.to_ascii_lowercase().contains("/login/verify"))
}

fn parse_display_name(html: &str, account: &str) -> String {
    let document = Html::parse_document(html);
    for value in [
        ".user-name",
        ".username",
        "#userName",
        ".navbar-text",
        "[data-user-name]",
    ] {
        if let Some(element) = document.select(&selector(value)).next() {
            let text = element_text(element);
            if !text.is_empty() && text != account && text.chars().count() <= 40 {
                return text;
            }
        }
    }
    let text = document.root_element().text().collect::<Vec<_>>().join(" ");
    let welcome =
        Regex::new(r"欢迎(?:您|回来)?[，,:：\s]+([^\s，,]{1,20})").expect("valid welcome regex");
    welcome
        .captures(&text)
        .and_then(|captures| captures.get(1))
        .map(|value| value.as_str().to_owned())
        .unwrap_or_default()
}

fn parse_account_status(html: &str) -> AppResult<String> {
    let document = Html::parse_document(html);
    for row in document.select(&selector(".row")) {
        let Some(label) = row.select(&selector("label")).next() else {
            continue;
        };
        let key: String = element_text(label)
            .chars()
            .filter(|character| !matches!(character, ' ' | '\t' | '\r' | '\n' | '　' | ':' | '：'))
            .collect();
        if key != "状态" {
            continue;
        }
        let value = row
            .select(&selector("span.label"))
            .next()
            .or_else(|| row.select(&selector("span")).next())
            .map(element_text)
            .unwrap_or_default();
        if !value.is_empty() {
            return Ok(value);
        }
    }
    Err(AppError::Protocol("账户状态页面格式已变化".into()))
}

fn parse_anomaly_info(html: &str) -> AppResult<String> {
    let document = Html::parse_document(html);
    let input = document
        .select(&selector("input[name=\"userCompany\"]"))
        .next()
        .ok_or_else(|| AppError::Protocol("账号异常信息页面格式已变化".into()))?;
    let value = input.value().attr("value").unwrap_or_default().trim();
    if value.is_empty() || value.eq_ignore_ascii_case("N/A") {
        Ok("暂无异常信息".into())
    } else {
        Ok(value.to_owned())
    }
}

fn validate_date_range(start_date: &str, end_date: &str) -> AppResult<()> {
    let start = NaiveDate::parse_from_str(start_date, "%Y-%m-%d")
        .map_err(|_| AppError::Validation("日期格式必须为 YYYY-MM-DD".into()))?;
    let end = NaiveDate::parse_from_str(end_date, "%Y-%m-%d")
        .map_err(|_| AppError::Validation("日期格式必须为 YYYY-MM-DD".into()))?;
    if start > end {
        return Err(AppError::Validation("开始日期不能晚于结束日期".into()));
    }
    if (end - start).num_days() > 60 {
        return Err(AppError::Validation("查询时间范围不能超过 60 天".into()));
    }
    Ok(())
}

fn parse_traffic_summary(
    payload: Value,
    start_date: &str,
    end_date: &str,
) -> AppResult<TrafficSummary> {
    let object = payload
        .as_object()
        .ok_or_else(|| AppError::Protocol("上网记录中没有流量汇总数据".into()))?;
    let empty_result = object.get("rows").is_none_or(value_is_empty)
        && object.get("total").is_none_or(value_is_zero);
    let empty_summary = Map::new();
    let summary = match object.get("summary").and_then(Value::as_object) {
        Some(value) => value,
        None if empty_result => &empty_summary,
        None => return Err(AppError::Protocol("上网记录中没有流量汇总数据".into())),
    };
    Ok(TrafficSummary {
        start_date: start_date.into(),
        end_date: end_date.into(),
        international_up_mb: summary_number(summary, "INTERNETUPFLOW")?,
        international_down_mb: summary_number(summary, "INTERNETDOWNFLOW")?,
        domestic_up_mb: summary_number(summary, "CHINANETUPFLOW")?,
        domestic_down_mb: summary_number(summary, "CHINANETDOWNFLOW")?,
    })
}

fn summary_number(summary: &Map<String, Value>, key: &str) -> AppResult<f64> {
    let value = summary.get(key).unwrap_or(&Value::Null);
    if value.is_null() {
        return Ok(0.0);
    }
    value
        .as_f64()
        .or_else(|| value.as_str().and_then(|text| text.parse().ok()))
        .ok_or_else(|| AppError::Protocol(format!("流量字段 {key} 格式无效")))
}

fn value_is_empty(value: &Value) -> bool {
    value.as_array().is_some_and(Vec::is_empty) || value.is_null()
}

fn value_is_zero(value: &Value) -> bool {
    value.as_i64() == Some(0) || value.is_null()
}

fn ensure_authenticated_url(url: &Url) -> AppResult<()> {
    if url.path().to_ascii_lowercase().contains("/login") {
        Err(AppError::Protocol(
            "自助服务登录已过期，请切换账号后重新登录".into(),
        ))
    } else {
        Ok(())
    }
}

fn element_text(element: ElementRef<'_>) -> String {
    element
        .text()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn selector(value: &str) -> Selector {
    Selector::parse(value).expect("static selector is valid")
}

fn invalid_url(_: url::ParseError) -> AppError {
    AppError::Validation("自助服务地址无效".into())
}

fn login_failure(message: impl Into<String>) -> SelfServiceLoginResult {
    SelfServiceLoginResult {
        success: false,
        message: message.into(),
        captcha_required: false,
        captcha_image: String::new(),
        session: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_login_page_state_and_script_error() {
        let html = r##"
            <form action="verify"><input name="checkcode" value="nonce"></form>
            <div id="randomDiv"><img></div>
            <script>$("#errorTip").html(x);})("验证码错误");</script>
        "##;
        let page = parse_login_page(html, "https://example.test/Self/login/").unwrap();
        assert_eq!(page.action_url, "https://example.test/Self/login/verify");
        assert_eq!(page.checkcode, "nonce");
        assert!(page.captcha_required);
        assert_eq!(page.error_message, "验证码错误");
    }

    #[test]
    fn parses_account_status_and_anomaly_info() {
        let dashboard =
            r#"<div class="row"><label>状态：</label><span class="label">正常</span></div>"#;
        assert_eq!(parse_account_status(dashboard).unwrap(), "正常");
        assert_eq!(
            parse_anomaly_info(r#"<input name="userCompany" value="N/A">"#).unwrap(),
            "暂无异常信息"
        );
    }

    #[test]
    fn validates_date_range() {
        assert!(validate_date_range("2026-01-01", "2026-03-03").is_err());
        assert!(validate_date_range("2026-01-02", "2026-01-01").is_err());
        assert!(validate_date_range("2026-01-01", "2026-03-02").is_ok());
    }

    #[test]
    fn parses_traffic_summary_and_empty_result() {
        let summary = parse_traffic_summary(
            serde_json::json!({
                "summary": {
                    "INTERNETUPFLOW": "1.25",
                    "INTERNETDOWNFLOW": 2,
                    "CHINANETUPFLOW": null,
                    "CHINANETDOWNFLOW": "3.5"
                }
            }),
            "2026-01-01",
            "2026-01-31",
        )
        .unwrap();
        assert_eq!(summary.international_up_mb, 1.25);
        assert_eq!(summary.domestic_down_mb, 3.5);

        let empty = parse_traffic_summary(
            serde_json::json!({"rows": [], "total": 0}),
            "2026-01-01",
            "2026-01-31",
        )
        .unwrap();
        assert_eq!(empty.international_down_mb, 0.0);
    }
}
