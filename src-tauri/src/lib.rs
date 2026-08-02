mod auth;
mod commands;
mod config;
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
    Manager,
};

const TRAY_ID: &str = "main-tray";
const PORTAL_POLL_INTERVAL: Duration = Duration::from_millis(500);
const RECONNECT_RETRY_DELAY: Duration = Duration::from_millis(1500);

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
        ])
        .run(tauri::generate_context!())
        .expect("error while running GuetLinker");
}

fn setup_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let check = MenuItem::with_id(app, "check", "立即检测", true, None::<&str>)?;
    let connect = MenuItem::with_id(app, "connect", "连接", true, None::<&str>)?;
    let disconnect = MenuItem::with_id(app, "disconnect", "断开", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let separator_before_actions = PredefinedMenuItem::separator(app)?;
    let separator_before_quit = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(
        app,
        &[
            &show,
            &separator_before_actions,
            &check,
            &connect,
            &disconnect,
            &separator_before_quit,
            &quit,
        ],
    )?;
    let mut tray = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip("GuetLinker")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "check" => run_tray_action(app, TrayAction::Check),
            "connect" => run_tray_action(app, TrayAction::Connect),
            "disconnect" => run_tray_action(app, TrayAction::Disconnect),
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
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

fn start_network_monitor(app: &tauri::AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut last_full_check = None;
        loop {
            let state = app.state::<state::AppState>();
            let full_check_interval =
                Duration::from_secs(state.config.lock().await.check_interval());
            let include_external = last_full_check
                .is_none_or(|checked_at: Instant| checked_at.elapsed() >= full_check_interval);
            if include_external {
                last_full_check = Some(Instant::now());
            }
            let result = commands::poll_network(state.inner(), &app, include_external).await;
            let retry_delay = if result.is_err() {
                RECONNECT_RETRY_DELAY
            } else {
                PORTAL_POLL_INTERVAL
            };
            publish_network_result(&app, state.inner(), result).await;
            tokio::time::sleep(retry_delay).await;
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
    update_tray_tooltip(app, &snapshot);
}

fn update_tray_tooltip(app: &tauri::AppHandle, snapshot: &monitor::NetworkSnapshot) {
    let status = match snapshot.status {
        monitor::NetworkStatus::Connected if !snapshot.account.is_empty() => "校园网已登录",
        monitor::NetworkStatus::Connected => "网络已连接",
        monitor::NetworkStatus::Disconnected => "校园网未连接",
        monitor::NetworkStatus::Reconnecting => "正在重连…",
        monitor::NetworkStatus::Unknown => "状态未知",
    };
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_tooltip(Some(format!("GuetLinker — {status}")));
    }
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}
