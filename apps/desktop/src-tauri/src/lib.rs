use tauri::Manager;
use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopRuntimeConfig {
    ai_base_url: String,
    is_desktop: bool,
    platform: &'static str,
    secret_storage_mode: &'static str,
    vault_state: &'static str,
}

#[tauri::command]
fn desktop_runtime_config() -> DesktopRuntimeConfig {
    DesktopRuntimeConfig {
        ai_base_url: std::env::var("VIBE_LEARNER_DESKTOP_AI_BASE_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string()),
        is_desktop: true,
        platform: match std::env::consts::OS {
            "macos" => "macos",
            "windows" => "windows",
            "linux" => "linux",
            _ => "unknown",
        },
        secret_storage_mode: "stronghold",
        vault_state: "unconfigured",
    }
}

fn runtime_config_script() -> tauri::Result<String> {
    let payload = serde_json::to_string(&desktop_runtime_config())
        .map_err(|err| tauri::Error::Anyhow(err.into()))?;
    Ok(format!(
        "window.__VIBE_LEARNER_DESKTOP_CONFIG__ = Object.freeze({payload});"
    ))
}

fn inject_runtime_config_window(window: &tauri::WebviewWindow) -> tauri::Result<()> {
    window.eval(runtime_config_script()?)
}

fn inject_runtime_config_webview(webview: &tauri::Webview) -> tauri::Result<()> {
    webview.eval(runtime_config_script()?)
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![desktop_runtime_config])
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                inject_runtime_config_window(&window)?;
            }
            Ok(())
        })
        .on_page_load(|window, _| {
            let _ = inject_runtime_config_webview(window);
        })
        .run(tauri::generate_context!())
        .expect("error while running vibe learner desktop shell");
}
