use std::sync::atomic::Ordering;

use serde::Serialize;
use tauri::{AppHandle, State};

use crate::{
    auth::{IspInfo, LoginResult, LogoutResult},
    config::{AppSettings, Credentials},
    error::AppError,
    monitor::{NetworkSnapshot, NetworkStatus},
    self_service::{AccountOverview, SelfServiceLoginResult, TrafficSummary},
    state::AppState,
};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveSettingsResult {
    notification_tested: bool,
    notification_error: String,
}

#[tauri::command]
pub async fn get_network_snapshot(state: State<'_, AppState>) -> Result<NetworkSnapshot, String> {
    Ok(state.monitor.lock().await.snapshot())
}

pub async fn refresh_network(state: &AppState, app: &AppHandle) -> Result<NetworkSnapshot, String> {
    poll_network(state, app, true).await
}

pub async fn poll_network(
    state: &AppState,
    app: &AppHandle,
    include_external: bool,
) -> Result<NetworkSnapshot, String> {
    let (portal_url, auto_reconnect, notifications, credentials) = {
        let config = state.config.lock().await;
        (
            config.portal_url().to_owned(),
            config.auto_reconnect(),
            config.notifications_enabled(),
            config.credentials(),
        )
    };
    let (snapshot, portal_online) = {
        let mut monitor = state.monitor.lock().await;
        let snapshot = monitor.check(&portal_url, include_external).await;
        (snapshot, monitor.portal_session().is_online())
    };
    if portal_online {
        state.resume_auto_reconnect();
    }
    let status_changed = state.record_network_status(snapshot.status).await;
    let should_reconnect = snapshot.status == NetworkStatus::Disconnected
        && auto_reconnect
        && state.auto_reconnect_allowed()
        && credentials.is_some();
    if status_changed && snapshot.status == NetworkStatus::Disconnected {
        let message = if should_reconnect {
            "检测到断网，正在尝试自动重连…"
        } else {
            "检测到校园网断线"
        };
        notify_if_enabled(app, notifications, message);
    }
    if should_reconnect {
        let result = connect(state, &portal_url, credentials).await;
        if let Ok(snapshot) = &result {
            state.record_network_status(snapshot.status).await;
            notify_if_enabled(app, notifications, "校园网已自动重新连接");
        }
        return result;
    }
    Ok(snapshot)
}

#[tauri::command]
pub async fn set_connection(
    connected: bool,
    state: State<'_, AppState>,
    app: AppHandle,
) -> Result<NetworkSnapshot, String> {
    let (portal_url, credentials, notifications) = {
        let config = state.config.lock().await;
        (
            config.portal_url().to_owned(),
            config.credentials(),
            config.notifications_enabled(),
        )
    };
    let result = if connected {
        state.resume_auto_reconnect();
        connect(state.inner(), &portal_url, credentials).await
    } else {
        state.pause_auto_reconnect();
        disconnect(state.inner(), &portal_url).await
    };
    match &result {
        Ok(snapshot) => {
            state.record_network_status(snapshot.status).await;
            let message = if connected {
                "校园网登录成功"
            } else {
                "校园网已断开"
            };
            notify_if_enabled(&app, notifications, message);
        }
        Err(error) => {
            let action = if connected {
                "登录未成功"
            } else {
                "断开失败"
            };
            notify_if_enabled(&app, notifications, &format!("{action}：{error}"));
        }
    }
    result
}

#[tauri::command]
pub async fn cancel_connection(state: State<'_, AppState>) -> Result<(), String> {
    state.login_cancel.store(true, Ordering::Relaxed);
    state.monitor.lock().await.cancel_reconnect();
    Ok(())
}

#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> Result<AppSettings, String> {
    Ok(state.config.lock().await.settings())
}

#[tauri::command]
pub async fn reveal_saved_password(state: State<'_, AppState>) -> Result<String, String> {
    state
        .config
        .lock()
        .await
        .reveal_password()
        .map_err(String::from)
}

#[tauri::command]
pub async fn save_settings(
    settings: AppSettings,
    state: State<'_, AppState>,
    app: AppHandle,
) -> Result<SaveSettingsResult, String> {
    sync_autostart(&app, settings.auto_start)?;
    let auto_reconnect = settings.auto_reconnect;
    let notifications_enabled = settings.notification && !settings.quiet;
    state
        .config
        .lock()
        .await
        .save_settings(settings)
        .map_err(String::from)?;
    if auto_reconnect {
        state.resume_auto_reconnect();
    }
    let notification_error = if notifications_enabled {
        show_notification(&app, "通知已开启，GuetLinker 将及时报告网络状态")
            .err()
            .unwrap_or_default()
    } else {
        String::new()
    };
    Ok(SaveSettingsResult {
        notification_tested: notifications_enabled,
        notification_error,
    })
}

#[cfg(all(windows, not(debug_assertions)))]
pub fn sync_autostart(app: &AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;

    let manager = app.autolaunch();
    let result = if enabled {
        manager.enable()
    } else {
        manager.disable()
    };
    result.map_err(|error| format!("开机启动设置失败: {error}"))
}

#[cfg(all(windows, debug_assertions))]
pub fn sync_autostart(_app: &AppHandle, enabled: bool) -> Result<(), String> {
    use std::io::ErrorKind;
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};

    const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
    const ENTRY_NAME: &str = "GuetLinker";

    let (run_key, _) = RegKey::predef(HKEY_CURRENT_USER)
        .create_subkey(RUN_KEY)
        .map_err(|error| format!("无法打开 Windows 启动项：{error}"))?;
    if !enabled {
        return match run_key.delete_value(ENTRY_NAME) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
            Err(error) => Err(format!("无法关闭开机启动：{error}")),
        };
    }

    let executable = release_executable_path()?;
    if !executable.is_file() {
        return Err(format!(
            "尚未生成独立 Release 程序：{}",
            executable.display()
        ));
    }
    run_key
        .set_value(ENTRY_NAME, &format!("\"{}\"", executable.display()))
        .map_err(|error| format!("无法设置开机启动：{error}"))
}

#[cfg(all(windows, debug_assertions))]
fn release_executable_path() -> Result<std::path::PathBuf, String> {
    let current = std::env::current_exe().map_err(|error| format!("无法定位当前程序：{error}"))?;
    release_executable_for(&current)
}

#[cfg(all(windows, debug_assertions))]
fn release_executable_for(current: &std::path::Path) -> Result<std::path::PathBuf, String> {
    let target = current
        .parent()
        .and_then(std::path::Path::parent)
        .ok_or_else(|| "无法定位 Rust target 目录".to_owned())?;
    let file_name = current
        .file_name()
        .ok_or_else(|| "无法确定程序文件名".to_owned())?;
    Ok(target.join("release").join(file_name))
}

#[cfg(not(windows))]
pub fn sync_autostart(_app: &AppHandle, _enabled: bool) -> Result<(), String> {
    Ok(())
}

fn notify_if_enabled(app: &AppHandle, enabled: bool, message: &str) {
    if enabled {
        let _ = show_notification(app, message);
    }
}

#[cfg(windows)]
fn show_notification(app: &AppHandle, message: &str) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;

    ensure_windows_notifications_available()?;
    app.notification()
        .builder()
        .title("GuetLinker")
        .body(message)
        .show()
        .map_err(|error| format!("系统通知发送失败：{error}"))
}

#[cfg(windows)]
fn ensure_windows_notifications_available() -> Result<(), String> {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};

    const TOAST_PATH: &str = r"Software\Microsoft\Windows\CurrentVersion\PushNotifications";

    let toast_enabled = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(TOAST_PATH)
        .ok()
        .and_then(|key| key.get_value::<u32, _>("ToastEnabled").ok());
    if toast_enabled == Some(0) {
        return Err("Windows 系统通知已关闭，请前往“设置 → 系统 → 通知”开启".into());
    }

    Ok(())
}

#[cfg(not(windows))]
fn show_notification(_app: &AppHandle, _message: &str) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub async fn get_isp_options(state: State<'_, AppState>) -> Result<Vec<IspInfo>, String> {
    let portal_url = state.config.lock().await.portal_url().to_owned();
    let options = state
        .auth
        .isp_options(&portal_url)
        .await
        .map_err(String::from)?;
    if options.is_empty() {
        Err("门户未返回运营商列表".into())
    } else {
        Ok(options)
    }
}

#[tauri::command]
pub async fn self_service_login(
    account: String,
    password: String,
    captcha: String,
    state: State<'_, AppState>,
) -> Result<SelfServiceLoginResult, String> {
    Ok(state
        .self_service
        .lock()
        .await
        .login(&account, &password, &captcha)
        .await)
}

#[tauri::command]
pub async fn self_service_prepare_login(
    account: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    state
        .self_service
        .lock()
        .await
        .prepare_login(&account)
        .await
        .map_err(String::from)
}

#[tauri::command]
pub async fn self_service_captcha(state: State<'_, AppState>) -> Result<String, String> {
    state
        .self_service
        .lock()
        .await
        .captcha_image()
        .await
        .map_err(String::from)
}

#[tauri::command]
pub async fn self_service_account_overview(
    state: State<'_, AppState>,
) -> Result<AccountOverview, String> {
    state
        .self_service
        .lock()
        .await
        .account_overview()
        .await
        .map_err(String::from)
}

#[tauri::command]
pub async fn self_service_traffic(
    start_date: String,
    end_date: String,
    state: State<'_, AppState>,
) -> Result<TrafficSummary, String> {
    state
        .self_service
        .lock()
        .await
        .traffic(&start_date, &end_date)
        .await
        .map_err(String::from)
}

#[tauri::command]
pub async fn reset_self_service(state: State<'_, AppState>) -> Result<(), String> {
    state
        .self_service
        .lock()
        .await
        .reset()
        .map_err(String::from)
}

async fn connect(
    state: &AppState,
    portal_url: &str,
    credentials: Option<Credentials>,
) -> Result<NetworkSnapshot, String> {
    let credentials = credentials.ok_or_else(|| "请先在连接与设置中填写学号和密码".to_owned())?;
    if !state.monitor.lock().await.begin_reconnect() {
        return Err("正在连接，请稍候".into());
    }
    state.login_cancel.store(false, Ordering::Relaxed);
    let result = state
        .auth
        .login(
            portal_url,
            &credentials.account,
            &credentials.password,
            &credentials.operator,
            state.login_cancel.clone(),
        )
        .await;
    apply_login_result(state, result).await
}

async fn apply_login_result(
    state: &AppState,
    result: LoginResult,
) -> Result<NetworkSnapshot, String> {
    let mut monitor = state.monitor.lock().await;
    if result.success {
        let session = result
            .portal_session
            .ok_or_else(|| AppError::Protocol("门户未返回已验证的在线会话".into()).to_string())?;
        monitor.accept_verified_session(session);
        Ok(monitor.snapshot())
    } else {
        monitor.cancel_reconnect();
        Err(result.message)
    }
}

async fn disconnect(state: &AppState, portal_url: &str) -> Result<NetworkSnapshot, String> {
    state.login_cancel.store(true, Ordering::Relaxed);
    let session = state.monitor.lock().await.portal_session();
    let result: LogoutResult = state.auth.logout(portal_url, Some(session)).await;
    if !result.success {
        return Err(result.message);
    }
    let mut monitor = state.monitor.lock().await;
    monitor.mark_disconnected();
    Ok(monitor.snapshot())
}

#[cfg(all(test, windows, debug_assertions))]
mod tests {
    use std::path::Path;

    use super::release_executable_for;

    #[test]
    fn development_autostart_targets_release_executable() {
        let current = Path::new(r"C:\project\target\debug\guetlinker-desktop.exe");
        let expected = Path::new(r"C:\project\target\release\guetlinker-desktop.exe");

        assert_eq!(release_executable_for(current).unwrap(), expected);
    }
}
