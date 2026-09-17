mod auth;
mod commands;
mod config;
mod diagnostics;
mod error;
mod monitor;
mod network;
mod portal;
mod self_service;
mod state;

use std::time::{Duration, Instant};

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

const TRAY_ID: &str = "main-tray";

#[derive(Clone, Copy)]
enum TrayAction {
    Check,
    Connect,
    Disconnect,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(windows)]
    let builder = builder
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_notification::init());

    builder
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let config_path = app.path().app_config_dir()?.join("config.json");
            let state = state::AppState::new(config_path)
                .map_err(|error| Box::<dyn std::error::Error>::from(error.to_string()))?;
            let auto_start = state.auto_start;
            let start_minimized = state.start_minimized;
            app.manage(state);
            setup_tray(app)?;
            start_network_monitor(app.handle());
            if let Err(error) = commands::sync_autostart(app.handle(), auto_start) {
                eprintln!("{error}");
            }
            if start_minimized {
                if let Some(window) = app.get_webview_window("main") {
                    window.hide()?;
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_network_snapshot,
            commands::set_connection,
            commands::cancel_connection,
            commands::get_settings,
            commands::reveal_saved_password,
            commands::save_settings,
            commands::get_isp_options,
            commands::self_service_login,
            commands::self_service_prepare_login,
            commands::self_service_captcha,
            commands::self_service_account_overview,
            commands::self_service_traffic,
            commands::reset_self_service,
            commands::check_app_update,
            commands::get_network_quality,
            commands::run_network_diagnostics,
            commands::get_public_egress_info,
        ])
        .run(tauri::generate_context!())
        .expect("error while running GuetLinker");
}

const TRAY_CONNECTED_RGBA: &[u8; 4096] = include_bytes!("../icons/tray-connected.rgba");
const TRAY_DISCONNECTED_RGBA: &[u8; 4096] = include_bytes!("../icons/tray-disconnected.rgba");
const TRAY_RECONNECTING_RGBA: &[u8; 4096] = include_bytes!("../icons/tray-reconnecting.rgba");
const TRAY_UNKNOWN_RGBA: &[u8; 4096] = include_bytes!("../icons/tray-unknown.rgba");

fn get_tray_icon(status: monitor::NetworkStatus) -> tauri::image::Image<'static> {
    let bytes: &'static [u8] = match status {
        monitor::NetworkStatus::Connected => TRAY_CONNECTED_RGBA,
        monitor::NetworkStatus::Disconnected => TRAY_DISCONNECTED_RGBA,
        monitor::NetworkStatus::Reconnecting => TRAY_RECONNECTING_RGBA,
        monitor::NetworkStatus::Unknown => TRAY_UNKNOWN_RGBA,
    };
    tauri::image::Image::new(bytes, 32, 32)
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let check = MenuItem::with_id(app, "check", "立即检测", true, None::<&str>)?;
    let connect = MenuItem::with_id(app, "connect", "连接", true, None::<&str>)?;
    let disconnect = MenuItem::with_id(app, "disconnect", "断开", true, None::<&str>)?;
    let update = MenuItem::with_id(app, "update", "检查更新…", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let separator_before_actions = PredefinedMenuItem::separator(app)?;
    let separator_before_update = PredefinedMenuItem::separator(app)?;
    let separator_before_quit = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(
        app,
        &[
            &show,
            &separator_before_actions,
            &check,
            &connect,
            &disconnect,
            &separator_before_update,
            &update,
            &separator_before_quit,
            &quit,
        ],
    )?;
    let tray = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip("GuetLinker")
        .icon(get_tray_icon(monitor::NetworkStatus::Unknown))
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "check" => run_tray_action(app, TrayAction::Check),
            "connect" => run_tray_action(app, TrayAction::Connect),
            "disconnect" => run_tray_action(app, TrayAction::Disconnect),
            "update" => {
                show_main_window(app);
                let _ = app.emit("open-check-update", ());
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });
    tray.build(app)?;
    Ok(())
}

fn start_network_monitor(app: &tauri::AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut last_full_check = None;
        let mut consecutive_reconnect_failures: u32 = 0;
        loop {
            let state = app.state::<state::AppState>();
            let (check_interval_secs, auto_reconnect) = {
                let config = state.config.lock().await;
                (config.check_interval(), config.auto_reconnect())
            };

            let full_check_interval = Duration::from_secs(check_interval_secs);
            let include_external = last_full_check
                .is_none_or(|checked_at: Instant| checked_at.elapsed() >= full_check_interval);
            if include_external {
                last_full_check = Some(Instant::now());
            }

            let result = commands::poll_network(state.inner(), &app, include_external).await;

            let delay = match &result {
                Ok(snapshot) if snapshot.connected => {
                    consecutive_reconnect_failures = 0;
                    // 在线状态：按配置周期（默认 25~30 秒）静默心跳，增加 0..3000ms 随机抖动模拟真人
                    let jitter_ms = (Instant::now().elapsed().as_nanos() % 3000) as u64;
                    Duration::from_millis(check_interval_secs * 1000 + jitter_ms)
                }
                Ok(snapshot) if snapshot.status == monitor::NetworkStatus::Reconnecting => {
                    // 正在重连中，给底层 2 秒缓冲时间
                    Duration::from_millis(2000)
                }
                Ok(_) => {
                    // 已断线
                    if auto_reconnect && state.auto_reconnect_allowed() {
                        // 指数退避重试：3s -> 6s -> 12s -> 最大 30s
                        consecutive_reconnect_failures =
                            consecutive_reconnect_failures.saturating_add(1);
                        let backoff_secs =
                            (3u64 * (1 << (consecutive_reconnect_failures - 1).min(3))).min(30);
                        Duration::from_secs(backoff_secs)
                    } else {
                        // 未开启重连或已触发密码错误熔断保护，进入 10 秒低频待命
                        Duration::from_secs(10)
                    }
                }
                Err(_) => {
                    // 探测或通信异常，退避保护
                    consecutive_reconnect_failures =
                        consecutive_reconnect_failures.saturating_add(1);
                    let backoff_secs =
                        (3u64 * (1 << (consecutive_reconnect_failures - 1).min(3))).min(30);
                    Duration::from_secs(backoff_secs)
                }
            };

            publish_network_result(&app, state.inner(), result).await;

            let sleep_start = Instant::now();
            tokio::time::sleep(delay).await;
            let sleep_elapsed = sleep_start.elapsed();

            // Detect system sleep/resume if timer slept significantly longer than expected (> 5s beyond delay)
            if sleep_elapsed > delay + Duration::from_secs(5) {
                state.monitor.lock().await.on_system_resume();
                last_full_check = None;
                consecutive_reconnect_failures = 0;
                // Wait briefly for network adapter re-association (DHCP/Wi-Fi) after resume
                tokio::time::sleep(Duration::from_millis(1000)).await;
            }
        }
    });
}

fn run_tray_action(app: &tauri::AppHandle, action: TrayAction) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let state = app.state::<state::AppState>();
        let result = match action {
            TrayAction::Check => commands::refresh_network(state.inner(), &app).await,
            TrayAction::Connect => commands::set_connection(true, state, app.clone()).await,
            TrayAction::Disconnect => commands::set_connection(false, state, app.clone()).await,
        };
        let state = app.state::<state::AppState>();
        publish_network_result(&app, state.inner(), result).await;
    });
}

async fn publish_network_result(
    app: &tauri::AppHandle,
    state: &state::AppState,
    result: Result<monitor::NetworkSnapshot, String>,
) {
    let snapshot = match result {
        Ok(snapshot) => snapshot,
        Err(_) => state.monitor.lock().await.snapshot(),
    };
    update_tray(app, &snapshot);
    let _ = app.emit("network-status-changed", &snapshot);
}

fn update_tray(app: &tauri::AppHandle, snapshot: &monitor::NetworkSnapshot) {
    let status = match snapshot.status {
        monitor::NetworkStatus::Connected if !snapshot.account.is_empty() => "校园网已登录",
        monitor::NetworkStatus::Connected => "网络已连接",
        monitor::NetworkStatus::Disconnected => "校园网未连接",
        monitor::NetworkStatus::Reconnecting => "正在重连…",
        monitor::NetworkStatus::Unknown => "状态未知",
    };
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_tooltip(Some(format!("GuetLinker — {status}")));
        let _ = tray.set_icon(Some(get_tray_icon(snapshot.status)));
    }
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}
