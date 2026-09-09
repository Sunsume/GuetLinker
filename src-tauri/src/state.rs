use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

use tokio::sync::Mutex;

use crate::{
    auth::AuthService,
    config::ConfigStore,
    error::AppResult,
    monitor::{NetworkMonitor, NetworkStatus},
    self_service::SelfServiceClient,
};

pub struct AppState {
    pub config: Mutex<ConfigStore>,
    pub auth: AuthService,
    pub monitor: Mutex<NetworkMonitor>,
    pub self_service: Mutex<SelfServiceClient>,
    pub login_cancel: Arc<AtomicBool>,
    pub auto_start: bool,
    pub start_minimized: bool,
    auto_reconnect_paused: AtomicBool,
    last_network_status: Mutex<NetworkStatus>,
}

impl AppState {
    pub fn new(config_path: PathBuf) -> AppResult<Self> {
        let config = ConfigStore::load(config_path)?;
        let settings = config.settings();
        Ok(Self {
            config: Mutex::new(config),
            auth: AuthService::new()?,
            monitor: Mutex::new(NetworkMonitor::new()?),
            self_service: Mutex::new(SelfServiceClient::new()?),
            login_cancel: Arc::new(AtomicBool::new(false)),
            auto_start: settings.auto_start,
            start_minimized: settings.start_minimized,
            auto_reconnect_paused: AtomicBool::new(false),
            last_network_status: Mutex::new(NetworkStatus::Unknown),
        })
    }

    pub fn auto_reconnect_allowed(&self) -> bool {
        !self.auto_reconnect_paused.load(Ordering::Relaxed)
    }

    pub fn pause_auto_reconnect(&self) {
        self.auto_reconnect_paused.store(true, Ordering::Relaxed);
    }

    pub fn resume_auto_reconnect(&self) {
        self.auto_reconnect_paused.store(false, Ordering::Relaxed);
    }

    pub async fn record_network_status(&self, status: NetworkStatus) -> bool {
        let mut previous = self.last_network_status.lock().await;
        let changed = *previous != status;
        *previous = status;
        changed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn auto_reconnect_can_be_paused_until_manual_connect() {
        let directory = tempfile::tempdir().unwrap();
        let state = AppState::new(directory.path().join("config.json")).unwrap();

        assert!(state.auto_reconnect_allowed());
        state.pause_auto_reconnect();
        assert!(!state.auto_reconnect_allowed());
        state.resume_auto_reconnect();
        assert!(state.auto_reconnect_allowed());
    }
}
