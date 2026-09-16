use std::time::{Duration, Instant};

use chrono::Local;
use serde::{Deserialize, Serialize};
use tokio::net::TcpStream;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodePingResult {
    pub id: String,
    pub name: String,
    pub target: String,
    pub latency_ms: Option<u32>,
    pub is_online: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticStep {
    pub id: String,
    pub name: String,
    pub status: String, // "pass", "warning", "fail"
    pub title: String,
    pub details: String,
    pub suggestion: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticReport {
    pub timestamp: String,
    pub overall_status: String, // "healthy", "warning", "error"
    pub summary: String,
    pub steps: Vec<DiagnosticStep>,
    pub export_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PublicEgressInfo {
    pub ip: String,
    pub country: String,
    pub country_code: String,
    pub region: String,
    pub city: String,
    pub isp: String,
    pub org: String,
    pub is_proxy_node: bool,
    pub is_cernet: bool,
    pub latency_ms: Option<u32>,
}

#[derive(Debug, Clone, Deserialize)]
struct IpApiResponse {
    status: Option<String>,
    country: Option<String>,
    #[serde(rename = "countryCode")]
    country_code: Option<String>,
    #[serde(rename = "regionName")]
    region_name: Option<String>,
    city: Option<String>,
    isp: Option<String>,
    org: Option<String>,
    query: Option<String>,
}

pub async fn measure_tcp_ping(addr: &str, timeout_ms: u64) -> Option<u32> {
    let start = Instant::now();
    match tokio::time::timeout(Duration::from_millis(timeout_ms), TcpStream::connect(addr)).await {
        Ok(Ok(_)) => {
            let elapsed = start.elapsed().as_millis() as u32;
            Some(elapsed.max(1))
        }
        _ => None,
    }
}

pub async fn probe_network_quality() -> Vec<NodePingResult> {
    let targets = [
        ("gateway", "桂电认证网关", "10.0.1.5:80"),
        ("guet_web", "桂电官网", "www.guet.edu.cn:443"),
        ("dns", "公共DNS服务", "223.5.5.5:53"),
        ("internet", "国内公共网络", "www.baidu.com:443"),
    ];

    let mut results = Vec::with_capacity(targets.len());
    for (id, name, addr) in targets {
        let latency = if id == "gateway" {
            match measure_tcp_ping(addr, 1500).await {
                Some(lat) => Some(lat),
                None => measure_tcp_ping("10.0.1.5:801", 1500).await,
            }
        } else {
            measure_tcp_ping(addr, 1500).await
        };
        results.push(NodePingResult {
            id: id.to_string(),
            name: name.to_string(),
            target: addr.to_string(),
            is_online: latency.is_some(),
            latency_ms: latency,
        });
    }
    results
}

pub async fn fetch_public_egress() -> Option<PublicEgressInfo> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(4))
        .build()
        .ok()?;

    let start = Instant::now();
    let response = client
        .get("http://ip-api.com/json/?lang=zh-CN")
        .send()
        .await
        .ok()?;

    let latency_ms = start.elapsed().as_millis() as u32;
    let data: IpApiResponse = response.json().await.ok()?;

    if data.status.as_deref() != Some("success") {
        return None;
    }

    let ip = data.query.unwrap_or_default();
    if ip.is_empty() {
        return None;
    }

    let country = data.country.unwrap_or_else(|| "未知地区".into());
    let country_code = data.country_code.unwrap_or_default();
    let region = data.region_name.unwrap_or_default();
    let city = data.city.unwrap_or_default();
    let isp = data.isp.unwrap_or_default();
    let org = data.org.unwrap_or_default();

    let combined_network = format!("{country} {region} {city} {isp} {org}").to_lowercase();
    let is_cernet = combined_network.contains("cernet")
        || combined_network.contains("教育网")
        || combined_network.contains("桂林电子科技大学")
        || combined_network.contains("guilin university of electronic technology");

    let cc = country_code.to_uppercase();
    let is_proxy_node = if !cc.is_empty() && cc != "CN" {
        true
    } else {
        let combined_org = format!("{isp} {org}").to_lowercase();
        combined_org.contains("cloudflare")
            || combined_org.contains("digitalocean")
            || combined_org.contains("vultr")
            || combined_org.contains("linode")
            || combined_org.contains("aws")
            || combined_org.contains("amazon")
            || combined_org.contains("google")
            || combined_org.contains("microsoft")
            || combined_org.contains("oracle")
            || combined_org.contains("m247")
            || combined_org.contains("ovh")
    };

    Some(PublicEgressInfo {
        ip,
        country,
        country_code,
        region,
        city,
        isp,
        org,
        is_proxy_node,
        is_cernet,
        latency_ms: Some(latency_ms.max(1)),
    })
}

pub async fn run_system_diagnostic(
    local_ip: &str,
    is_logged_in: bool,
    saved_account: Option<&str>,
) -> DiagnosticReport {
    let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let mut steps = Vec::new();
    let mut has_error = false;
    let mut has_warning = false;

    // 1. 本地网络与 IP 分配
    let ip_clean = local_ip.trim();
    if ip_clean.is_empty() || ip_clean == "—" || ip_clean == "0.0.0.0" {
        has_error = true;
        steps.push(DiagnosticStep {
            id: "local_ip".into(),
            name: "本地 IP 分配".into(),
            status: "fail".into(),
            title: "未获取到有效 IP 地址".into(),
            details: "本机网卡未分配到 IP，可能是网线未插紧或未连接桂电 Wi-Fi。".into(),
            suggestion: Some("请检查物理网线连接，或重新连接 GUET-WiFi".into()),
        });
    } else if ip_clean.starts_with("169.254.") {
        has_error = true;
        steps.push(DiagnosticStep {
            id: "local_ip".into(),
            name: "本地 IP 分配".into(),
            status: "fail".into(),
            title: "DHCP 分配失败 (APIPA 状态)".into(),
            details: format!("当前 IP 为 {ip_clean}，表明未能成功从校园网 DHCP 服务器获取地址。"),
            suggestion: Some("建议禁用并重新启用网卡，或重启 Wi-Fi 开关".into()),
        });
    } else {
        steps.push(DiagnosticStep {
            id: "local_ip".into(),
            name: "本地 IP 分配".into(),
            status: "pass".into(),
            title: "IP 分配正常".into(),
            details: format!("本机 IPv4: {ip_clean}"),
            suggestion: None,
        });
    }

    // 2. 校园网认证网关连通性 (10.0.1.5:80 / 10.0.1.5:801)
    let gateway_ping = match measure_tcp_ping("10.0.1.5:80", 1500).await {
        Some(ms) => Some((ms, 80)),
        None => measure_tcp_ping("10.0.1.5:801", 1500).await.map(|ms| (ms, 801)),
    };
    match gateway_ping {
        Some((ms, port)) => {
            steps.push(DiagnosticStep {
                id: "gateway".into(),
                name: format!("校园网网关 (10.0.1.5:{port})"),
                status: "pass".into(),
                title: "认证网关通信正常".into(),
                details: format!("往返延迟: {ms} ms"),
                suggestion: None,
            });
        }
        None => {
            has_error = true;
            steps.push(DiagnosticStep {
                id: "gateway".into(),
                name: "校园网网关 (10.0.1.5)".into(),
                status: "fail".into(),
                title: "无法访问认证网关".into(),
                details: "无法与桂电认证门户 10.0.1.5 建立 TCP 握手 (端口 80/801 均超时)。".into(),
                suggestion: Some("请确认当前设备接入的是桂电校内有线或无线网络 (非手机个人热点)".into()),
            });
        }
    }

    // 3. DNS 解析与连通性
    let dns_ping = measure_tcp_ping("223.5.5.5:53", 2000).await;
    match dns_ping {
        Some(ms) => {
            steps.push(DiagnosticStep {
                id: "dns".into(),
                name: "域名解析 (DNS)".into(),
                status: "pass".into(),
                title: "DNS 服务器可达".into(),
                details: format!("公共 DNS 响应延迟: {ms} ms"),
                suggestion: None,
            });
        }
        None => {
            has_warning = true;
            steps.push(DiagnosticStep {
                id: "dns".into(),
                name: "域名解析 (DNS)".into(),
                status: "warning".into(),
                title: "DNS 探测响应超时".into(),
                details: "DNS 服务器 223.5.5.5 未在规定时间内响应。".into(),
                suggestion: Some("建议将网卡 DNS 修改为自动获取或 10.0.1.5".into()),
            });
        }
    }

    // 4. 外网与国内公共网络连通性
    let internet_ping = measure_tcp_ping("www.baidu.com:443", 2500).await;
    match internet_ping {
        Some(ms) => {
            steps.push(DiagnosticStep {
                id: "internet".into(),
                name: "外网连通性".into(),
                status: "pass".into(),
                title: "互联网访问通畅".into(),
                details: format!("公共网络响应延迟: {ms} ms"),
                suggestion: None,
            });
        }
        None => {
            if is_logged_in {
                has_warning = true;
                steps.push(DiagnosticStep {
                    id: "internet".into(),
                    name: "外网连通性".into(),
                    status: "warning".into(),
                    title: "校园网已登录但外网暂不可达".into(),
                    details: "门户认证状态显示为在线，但外部网络连接超时，可能是校外出口拥堵或账户欠费停机。".into(),
                    suggestion: Some("请前往“账户”页查询账户是否存在欠费停机或停用警告".into()),
                });
            } else {
                steps.push(DiagnosticStep {
                    id: "internet".into(),
                    name: "外网连通性".into(),
                    status: "fail".into(),
                    title: "尚未登录校园网认证".into(),
                    details: "外网受限，需要完成 Dr.COM Web 认证后方可接入互联网。".into(),
                    suggestion: Some("请在主界面点击【连接】完成校园网登录".into()),
                });
            }
        }
    }

    // 5. 本地凭据配置检查
    if let Some(account) = saved_account {
        steps.push(DiagnosticStep {
            id: "credentials".into(),
            name: "本地认证配置".into(),
            status: "pass".into(),
            title: "已配置校园网账号".into(),
            details: format!("配置账号: {account}"),
            suggestion: None,
        });
    } else {
        has_warning = true;
        steps.push(DiagnosticStep {
            id: "credentials".into(),
            name: "本地认证配置".into(),
            status: "warning".into(),
            title: "未配置保存账号".into(),
            details: "尚未在“连接与设置”中保存学号凭据，无法执行自动重连。".into(),
            suggestion: Some("前往“连接与设置”页面保存账号密码以享受无感自愈重连".into()),
        });
    }

    // 6. 公网与代理出口安全探测
    if let Some(egress) = fetch_public_egress().await {
        if egress.is_cernet {
            has_warning = true;
            steps.push(DiagnosticStep {
                id: "egress_safety".into(),
                name: "公网出口与代理安全".into(),
                status: "warning".into(),
                title: "当前处于校园网教育网出口 (严查代理)".into(),
                details: format!("公网出口 IP: {} (CERNET/桂电)，学校对教育网出口严格审计代理行为。", egress.ip),
                suggestion: Some("切勿在教育网出口开启翻墙工具以防学号被封，建议在“连接与设置”中切换至【中国移动】出口".into()),
            });
        } else if egress.is_proxy_node {
            steps.push(DiagnosticStep {
                id: "egress_safety".into(),
                name: "公网出口与代理安全".into(),
                status: "pass".into(),
                title: "代理/翻墙出口已生效".into(),
                details: format!("出口 IP: {} ({} {} · {})", egress.ip, egress.country, egress.city, egress.isp),
                suggestion: None,
            });
        } else {
            steps.push(DiagnosticStep {
                id: "egress_safety".into(),
                name: "公网出口与代理安全".into(),
                status: "pass".into(),
                title: "运营商商业专线出口 (安全直连)".into(),
                details: format!("出口 IP: {} ({} {} · {})", egress.ip, egress.country, egress.city, egress.isp),
                suggestion: None,
            });
        }
    }

    let (overall_status, summary) = if has_error {
        ("error".to_string(), "体检发现网络阻碍，请根据上方建议排查。".to_string())
    } else if has_warning {
        ("warning".to_string(), "核心链路正常，但存在部分警告，网络可能受限。".to_string())
    } else {
        ("healthy".to_string(), "各项网络指标均表现优异，校园网运行稳定！".to_string())
    };

    // 构造报障导出文本
    let mut export_lines = Vec::new();
    export_lines.push("================ GuetLinker 网络体检报障单 ================".to_string());
    export_lines.push(format!("生成时间: {timestamp}"));
    export_lines.push(format!("客户端版本: v{} (Tauri 2 + Rust)", env!("CARGO_PKG_VERSION")));
    export_lines.push(format!("综合评估: {summary}"));
    export_lines.push("--------------------------------------------------------".to_string());
    for s in &steps {
        let tag = match s.status.as_str() {
            "pass" => "[正常]",
            "warning" => "[警告]",
            _ => "[故障]",
        };
        export_lines.push(format!("{tag} {} : {} ({})", s.name, s.title, s.details));
        if let Some(sug) = &s.suggestion {
            export_lines.push(format!("       建议排查: {sug}"));
        }
    }
    export_lines.push("========================================================".to_string());
    let export_text = export_lines.join("\n");

    DiagnosticReport {
        timestamp,
        overall_status,
        summary,
        steps,
        export_text,
    }
}
