use std::{net::IpAddr, time::Duration};

use chrono::Local;
use reqwest::{redirect::Policy, Client};
use serde::Serialize;

use crate::{
    error::AppResult,
    network::{find_local_ipv4, find_local_ipv6},
    portal::{parse_portal_page, PortalPageState, PortalSession},
};

const USER_AGENT: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36";
const CHECK_URLS: [&str; 2] = [
    "https://connectivitycheck.gstatic.com/generate_204",
    "https://www.msftconnecttest.com/connecttest.txt",
];

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum NetworkStatus {
    Connected,
    Disconnected,
    Reconnecting,
    #[default]
    Unknown,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NetworkSnapshot {
    pub connected: bool,
    pub status: NetworkStatus,
    pub account: String,
    pub operator: String,
    pub ipv4: String,
    pub ipv6: String,
    pub checked_at: String,
}

impl NetworkSnapshot {
    fn new(status: NetworkStatus, session: &PortalSession) -> Self {
        let mut ipv4 = session.ipv4.clone();
        if ipv4.is_empty() {
            ipv4 = find_local_ipv4();
        }
        let mut ipv6 = session.ipv6.clone();
        if ipv6.is_empty() && !ipv4.is_empty() {
            ipv6 = find_local_ipv6(&ipv4);
        }
        Self {
            connected: status == NetworkStatus::Connected,
            status,
            account: session.account_id(),
            operator: session.operator_name(),
            ipv4,
            ipv6,
            checked_at: Local::now().format("%H:%M:%S").to_string(),
        }
    }
}

#[derive(Clone, Debug)]
struct ProbeResult {
    portal_session: PortalSession,
    external_reachable: Option<bool>,
}

pub struct NetworkMonitor {
    client: Client,
    status: NetworkStatus,
    portal_session: PortalSession,
    consecutive_failures: u8,
    failure_threshold: u8,
    reconnect_in_progress: bool,
}

impl NetworkMonitor {
    pub fn new() -> AppResult<Self> {
        let mut builder = Client::builder()
            .redirect(Policy::limited(5))
            .no_proxy()
            .user_agent(USER_AGENT)
            .timeout(Duration::from_secs(3));

        let local_ip = find_local_ipv4();
        if let Ok(ip) = local_ip.parse::<IpAddr>() {
            builder = builder.local_address(Some(ip));
        }

        let client = builder.build()?;
        Ok(Self {
            client,
            status: NetworkStatus::Unknown,
            portal_session: PortalSession::default(),
            consecutive_failures: 0,
            failure_threshold: 2,
            reconnect_in_progress: false,
        })
    }

    pub fn snapshot(&self) -> NetworkSnapshot {
        NetworkSnapshot::new(self.status, &self.portal_session)
    }

    pub fn portal_session(&self) -> PortalSession {
        self.portal_session.clone()
    }

    pub async fn check(&mut self, portal_url: &str, include_external: bool) -> NetworkSnapshot {
        let result = self.probe(portal_url, include_external).await;
        self.apply_probe_result(result);
        self.snapshot()
    }

    pub fn begin_reconnect(&mut self) -> bool {
        if self.reconnect_in_progress {
            return false;
        }
        self.reconnect_in_progress = true;
        self.status = NetworkStatus::Reconnecting;
        true
    }

    pub fn cancel_reconnect(&mut self) {
        self.reconnect_in_progress = false;
        self.status = if self.portal_session.state == PortalPageState::LoginRequired {
            NetworkStatus::Disconnected
        } else {
            NetworkStatus::Unknown
        };
    }

    pub fn accept_verified_session(&mut self, session: PortalSession) {
        if !session.is_online() {
            return;
        }
        self.consecutive_failures = 0;
        self.reconnect_in_progress = false;
        self.portal_session = session;
        self.status = NetworkStatus::Connected;
    }

    pub fn mark_disconnected(&mut self) {
        self.consecutive_failures = self.failure_threshold;
        self.reconnect_in_progress = false;
        self.portal_session = PortalSession {
            state: PortalPageState::LoginRequired,
            ..PortalSession::default()
        };
        self.status = NetworkStatus::Disconnected;
    }

    pub fn on_system_resume(&mut self) {
        self.consecutive_failures = 0;
        self.reconnect_in_progress = false;
        if self.portal_session.is_online() {
            self.portal_session.state = PortalPageState::Unknown;
        }
    }

    async fn probe(&self, portal_url: &str, include_external: bool) -> ProbeResult {
        let portal_session = self.fetch_portal_session(portal_url).await;
        let external_reachable =
            if include_external && portal_session.state == PortalPageState::Unknown {
                Some(self.check_external().await)
            } else {
                None
            };
        ProbeResult {
            portal_session,
            external_reachable,
        }
    }

    fn apply_probe_result(&mut self, result: ProbeResult) {
        if result.portal_session.is_online() {
            self.portal_session = result.portal_session;
            self.consecutive_failures = 0;
            self.reconnect_in_progress = false;
            self.status = NetworkStatus::Connected;
            return;
        }

        if result.external_reachable == Some(true) {
            self.consecutive_failures = 0;
            self.reconnect_in_progress = false;
            self.status = NetworkStatus::Connected;
            if !result.portal_session.user_id.is_empty() {
                self.portal_session.user_id = result.portal_session.user_id;
            }
            if !result.portal_session.ipv4.is_empty() {
                self.portal_session.ipv4 = result.portal_session.ipv4;
            }
            if self.portal_session.ipv4.is_empty() {
                self.portal_session.ipv4 = find_local_ipv4();
            }
            if self.portal_session.ipv6.is_empty() && !self.portal_session.ipv4.is_empty() {
                self.portal_session.ipv6 = find_local_ipv6(&self.portal_session.ipv4);
            }
            return;
        }

        self.portal_session = result.portal_session;
        if self.portal_session.state == PortalPageState::LoginRequired {
            self.consecutive_failures = self.failure_threshold;
            if !self.reconnect_in_progress {
                self.status = NetworkStatus::Disconnected;
            }
            return;
        }
        if result.external_reachable != Some(false) {
            return;
        }

        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
        if self.consecutive_failures >= self.failure_threshold && !self.reconnect_in_progress {
            self.status = NetworkStatus::Disconnected;
        }
    }

    async fn fetch_portal_session(&self, portal_url: &str) -> PortalSession {
        let response = self
            .client
            .get(portal_url)
            .header("Cache-Control", "no-cache, no-store, max-age=0")
            .header("Pragma", "no-cache")
            .header(
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            )
            .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
            .send()
            .await;
        let Ok(response) = response else {
            return PortalSession::default();
        };
        if response.status() != reqwest::StatusCode::OK {
            return PortalSession::default();
        }
        let Ok(html) = response.text().await else {
            return PortalSession::default();
        };
        let mut session = parse_portal_page(&html, portal_url);
        if session.ipv4.is_empty() {
            session.ipv4 = find_local_ipv4();
        }
        if session.is_online() && session.ipv6.is_empty() && !session.ipv4.is_empty() {
            session.ipv6 = find_local_ipv6(&session.ipv4);
        }
        session
    }

    async fn check_external(&self) -> bool {
        for url in CHECK_URLS {
            let response = self.client.get(url).send().await;
            let Ok(response) = response else {
                continue;
            };
            if response.status() == reqwest::StatusCode::NO_CONTENT {
                return true;
            }
            if response.status() == reqwest::StatusCode::OK
                && url.ends_with("connecttest.txt")
                && response
                    .text()
                    .await
                    .is_ok_and(|body| body.contains("Microsoft Connect Test"))
            {
                return true;
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn probe(state: PortalPageState, external: Option<bool>) -> ProbeResult {
        ProbeResult {
            portal_session: PortalSession {
                state,
                ..PortalSession::default()
            },
            external_reachable: external,
        }
    }

    #[test]
    fn login_required_disconnects_immediately() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::LoginRequired, None));
        assert_eq!(monitor.status, NetworkStatus::Disconnected);
    }

    #[test]
    fn requires_two_external_failures_when_portal_is_unknown() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        assert_eq!(monitor.status, NetworkStatus::Unknown);
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        assert_eq!(monitor.status, NetworkStatus::Disconnected);
    }

    #[test]
    fn online_portal_resets_failure_count() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        monitor.apply_probe_result(probe(PortalPageState::Online, None));
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        assert_eq!(monitor.status, NetworkStatus::Connected);
    }

    #[test]
    fn failed_reconnect_keeps_login_required_status() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::LoginRequired, None));
        assert!(monitor.begin_reconnect());

        monitor.cancel_reconnect();

        assert_eq!(monitor.status, NetworkStatus::Disconnected);
    }

    #[test]
    fn failed_reconnect_waits_for_portal_when_network_is_unreachable() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(false)));
        assert!(monitor.begin_reconnect());

        monitor.cancel_reconnect();

        assert_eq!(monitor.status, NetworkStatus::Unknown);
    }

    #[test]
    fn probe_does_not_overwrite_reconnecting_status() {
        let mut monitor = NetworkMonitor::new().unwrap();
        assert!(monitor.begin_reconnect());

        monitor.apply_probe_result(probe(PortalPageState::LoginRequired, None));

        assert_eq!(monitor.status, NetworkStatus::Reconnecting);
    }

    #[test]
    fn external_connectivity_is_enough_when_portal_is_unknown() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::Unknown, Some(true)));
        assert_eq!(monitor.status, NetworkStatus::Connected);
    }

    #[test]
    fn on_system_resume_resets_state_and_invalidates_online_session() {
        let mut monitor = NetworkMonitor::new().unwrap();
        monitor.apply_probe_result(probe(PortalPageState::Online, None));
        assert_eq!(monitor.status, NetworkStatus::Connected);
        assert!(monitor.portal_session.is_online());

        monitor.on_system_resume();
        assert_eq!(monitor.consecutive_failures, 0);
        assert!(!monitor.reconnect_in_progress);
        assert_eq!(monitor.portal_session.state, PortalPageState::Unknown);
    }
}
