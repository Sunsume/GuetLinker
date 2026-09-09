use std::{env, fs, path::PathBuf};

use aes_gcm::{
    aead::{Aead, Generate, Key, KeyInit},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::{AppError, AppResult};

const DEFAULT_PORTAL_URL: &str = "http://10.0.1.5/";
const MIN_CHECK_INTERVAL: u64 = 10;
const MAX_CHECK_INTERVAL: u64 = 300;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, rename_all = "camelCase")]
pub struct AppSettings {
    pub student_id: String,
    pub password: String,
    pub operator: String,
    pub quiet: bool,
    pub notification: bool,
    pub auto_reconnect: bool,
    pub auto_start: bool,
    pub start_minimized: bool,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            student_id: String::new(),
            password: String::new(),
            operator: "校园网".into(),
            quiet: false,
            notification: true,
            auto_reconnect: false,
            auto_start: false,
            start_minimized: false,
        }
    }
}

#[derive(Clone, Debug)]
pub struct Credentials {
    pub account: String,
    pub password: String,
    pub operator: String,
}

#[derive(Debug)]
pub struct ConfigStore {
    path: PathBuf,
    data: StoredConfig,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, rename_all = "camelCase")]
struct StoredConfig {
    student_id: String,
    encrypted_password: String,
    operator: String,
    quiet: bool,
    notification: bool,
    auto_reconnect: bool,
    auto_start: bool,
    start_minimized: bool,
    portal_url: String,
    check_interval: u64,
}

impl Default for StoredConfig {
    fn default() -> Self {
        Self {
            student_id: String::new(),
            encrypted_password: String::new(),
            operator: "校园网".into(),
            quiet: false,
            notification: true,
            auto_reconnect: false,
            auto_start: false,
            start_minimized: false,
            portal_url: DEFAULT_PORTAL_URL.into(),
            check_interval: 30,
        }
    }
}

impl ConfigStore {
    pub fn load(path: PathBuf) -> AppResult<Self> {
        let data = if path.exists() {
            serde_json::from_str(&fs::read_to_string(&path)?)?
        } else {
            StoredConfig::default()
        };
        Ok(Self { path, data })
    }

    pub fn settings(&self) -> AppSettings {
        let password = if self.data.encrypted_password.is_empty() {
            String::new()
        } else {
            "••••••••".to_owned()
        };
        AppSettings {
            student_id: self.data.student_id.clone(),
            password,
            operator: self.data.operator.clone(),
            quiet: self.data.quiet,
            notification: self.data.notification,
            auto_reconnect: self.data.auto_reconnect,
            auto_start: self.data.auto_start,
            start_minimized: self.data.start_minimized,
        }
    }

    pub fn save_settings(&mut self, settings: AppSettings) -> AppResult<()> {
        self.data.student_id = settings.student_id.trim().to_owned();
        self.data.operator = settings.operator;
        self.data.quiet = settings.quiet;
        self.data.notification = settings.notification;
        self.data.auto_reconnect = settings.auto_reconnect;
        self.data.auto_start = settings.auto_start;
        self.data.start_minimized = settings.start_minimized;
        if !is_password_placeholder(&settings.password) {
            self.data.encrypted_password = encrypt_password(&settings.password)?;
        }
        self.sync()
    }

    pub fn credentials(&self) -> Option<Credentials> {
        let password = self.decrypt_password().ok()?;
        (!self.data.student_id.is_empty() && !password.is_empty() && !self.data.operator.is_empty())
            .then(|| Credentials {
                account: self.data.student_id.clone(),
                password,
                operator: self.data.operator.clone(),
            })
    }

    pub fn reveal_password(&self) -> AppResult<String> {
        self.decrypt_password()
    }

    pub fn portal_url(&self) -> &str {
        &self.data.portal_url
    }

    pub fn auto_reconnect(&self) -> bool {
        self.data.auto_reconnect
    }

    pub fn notifications_enabled(&self) -> bool {
        self.data.notification && !self.data.quiet
    }

    pub fn check_interval(&self) -> u64 {
        self.data
            .check_interval
            .clamp(MIN_CHECK_INTERVAL, MAX_CHECK_INTERVAL)
    }

    fn decrypt_password(&self) -> AppResult<String> {
        decrypt_password(&self.data.encrypted_password)
    }

    fn sync(&self) -> AppResult<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.path, serde_json::to_vec_pretty(&self.data)?)?;
        Ok(())
    }
}

fn is_password_placeholder(password: &str) -> bool {
    !password.is_empty() && password.chars().all(|character| character == '•')
}

fn encrypt_password(password: &str) -> AppResult<String> {
    if password.is_empty() {
        return Ok(String::new());
    }
    let cipher = password_cipher();
    let nonce = Nonce::generate();
    let ciphertext = cipher
        .encrypt(&nonce, password.as_bytes())
        .map_err(|_| AppError::Crypto)?;
    let mut payload = nonce.to_vec();
    payload.extend(ciphertext);
    Ok(URL_SAFE_NO_PAD.encode(payload))
}

fn decrypt_password(encrypted: &str) -> AppResult<String> {
    if encrypted.is_empty() {
        return Ok(String::new());
    }
    let payload = URL_SAFE_NO_PAD
        .decode(encrypted)
        .map_err(|_| AppError::Crypto)?;
    if payload.len() <= 12 {
        return Err(AppError::Crypto);
    }
    let (nonce, ciphertext) = payload.split_at(12);
    let nonce = Nonce::try_from(nonce).map_err(|_| AppError::Crypto)?;
    let plaintext = password_cipher()
        .decrypt(&nonce, ciphertext)
        .map_err(|_| AppError::Crypto)?;
    String::from_utf8(plaintext).map_err(|_| AppError::Crypto)
}

fn password_cipher() -> Aes256Gcm {
    let machine = format!(
        "{}:{}",
        env::var("COMPUTERNAME")
            .or_else(|_| env::var("HOSTNAME"))
            .unwrap_or_else(|_| "unknown".into()),
        env::var("USERNAME")
            .or_else(|_| env::var("USER"))
            .unwrap_or_else(|_| "unknown".into())
    );
    let digest = Sha256::digest(machine.as_bytes());
    let key = Key::<Aes256Gcm>::try_from(digest.as_slice())
        .expect("SHA-256 always produces a 256-bit key");
    Aes256Gcm::new(&key)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn persists_encrypted_settings() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("config.json");
        let mut store = ConfigStore::load(path.clone()).unwrap();
        store
            .save_settings(AppSettings {
                student_id: "20240001".into(),
                password: "secret".into(),
                operator: "中国移动".into(),
                auto_reconnect: true,
                ..AppSettings::default()
            })
            .unwrap();

        let raw = fs::read_to_string(&path).unwrap();
        assert!(!raw.contains("secret"));
        let loaded = ConfigStore::load(path).unwrap();
        let credentials = loaded.credentials().unwrap();
        assert_eq!(credentials.account, "20240001");
        assert_eq!(credentials.password, "secret");
        assert_eq!(credentials.operator, "中国移动");
        assert_eq!(loaded.reveal_password().unwrap(), "secret");
        assert!(loaded.auto_reconnect());
    }

    #[test]
    fn password_placeholder_keeps_existing_secret() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("config.json");
        let mut store = ConfigStore::load(path).unwrap();
        store
            .save_settings(AppSettings {
                password: "secret".into(),
                student_id: "1".into(),
                operator: "校园网".into(),
                ..AppSettings::default()
            })
            .unwrap();
        let mut settings = store.settings();
        settings.password = "••••••".into();
        store.save_settings(settings).unwrap();
        assert_eq!(store.credentials().unwrap().password, "secret");
    }
}
