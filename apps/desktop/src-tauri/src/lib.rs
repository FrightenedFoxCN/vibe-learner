use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use argon2::{Algorithm, Argon2, Params, Version};
use serde::Serialize;
use tauri::Manager;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopRuntimeConfig {
    ai_base_url: String,
    is_desktop: bool,
    platform: &'static str,
    secret_storage_mode: &'static str,
    vault_state: &'static str,
    vault_path: String,
    storage_root: String,
}

struct ManagedSidecar {
    child: Option<Child>,
}

impl Drop for ManagedSidecar {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

struct DesktopAppState {
    ai_base_url: String,
    storage_root: String,
    vault_path: String,
    vault_state: &'static str,
    _sidecar: Mutex<ManagedSidecar>,
}

#[tauri::command]
fn desktop_runtime_config(state: tauri::State<'_, DesktopAppState>) -> DesktopRuntimeConfig {
    runtime_config_from_state(state.inner())
}

fn runtime_config_from_state(state: &DesktopAppState) -> DesktopRuntimeConfig {
    DesktopRuntimeConfig {
        ai_base_url: state.ai_base_url.clone(),
        is_desktop: true,
        platform: match std::env::consts::OS {
            "macos" => "macos",
            "windows" => "windows",
            "linux" => "linux",
            _ => "unknown",
        },
        secret_storage_mode: "stronghold",
        vault_state: state.vault_state,
        vault_path: state.vault_path.clone(),
        storage_root: state.storage_root.clone(),
    }
}

fn runtime_config_script(state: &DesktopAppState) -> tauri::Result<String> {
    let payload = serde_json::to_string(&runtime_config_from_state(state))
        .map_err(|err| tauri::Error::Anyhow(err.into()))?;
    Ok(format!(
        "window.__VIBE_LEARNER_DESKTOP_CONFIG__ = Object.freeze({payload});"
    ))
}

fn inject_runtime_config_window(
    window: &tauri::WebviewWindow,
    state: &DesktopAppState,
) -> tauri::Result<()> {
    window.eval(runtime_config_script(state)?)
}

fn inject_runtime_config_webview(
    webview: &tauri::Webview,
    state: &DesktopAppState,
) -> tauri::Result<()> {
    webview.eval(runtime_config_script(state)?)
}

fn build_desktop_state(app: &tauri::AppHandle) -> Result<DesktopAppState, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("desktop_app_data_dir_failed:{err}"))?;
    fs::create_dir_all(&app_data_dir)
        .map_err(|err| format!("desktop_app_data_dir_create_failed:{err}"))?;

    let storage_root = app_data_dir.join("ai-data");
    fs::create_dir_all(&storage_root)
        .map_err(|err| format!("desktop_storage_root_create_failed:{err}"))?;

    let vault_path = app_data_dir.join("vibe-learner.secrets.hold");
    let vault_state = if vault_path.exists() {
        "locked"
    } else {
        "unconfigured"
    };

    let port = available_port().map_err(|err| format!("desktop_port_allocation_failed:{err}"))?;
    let ai_base_url = format!("http://127.0.0.1:{port}");
    let child = spawn_sidecar_process(port, &storage_root)?;
    wait_for_sidecar_health(port)?;

    Ok(DesktopAppState {
        ai_base_url,
        storage_root: storage_root.to_string_lossy().into_owned(),
        vault_path: vault_path.to_string_lossy().into_owned(),
        vault_state,
        _sidecar: Mutex::new(ManagedSidecar { child: Some(child) }),
    })
}

fn available_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn spawn_sidecar_process(port: u16, storage_root: &Path) -> Result<Child, String> {
    let services_ai_dir = repo_root().join("services").join("ai");
    if !services_ai_dir.exists() {
        return Err(format!(
            "desktop_sidecar_source_missing:{}",
            services_ai_dir.display()
        ));
    }

    let database_url = format!(
        "sqlite:///{}",
        storage_root.join("vibe_learner.db").to_string_lossy()
    );
    let allowed_origins = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ]
    .join(",");

    Command::new("uv")
        .current_dir(&services_ai_dir)
        .arg("run")
        .arg("python")
        .arg("-m")
        .arg("app.sidecar")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .env("DATABASE_URL", database_url)
        .env("VIBE_LEARNER_STORAGE_ROOT", storage_root)
        .env("VIBE_LEARNER_DESKTOP_MODE", "true")
        .env("VIBE_LEARNER_ALLOWED_ORIGINS", allowed_origins)
        .env("VIBE_LEARNER_OCR_ENGINE", "onnxtr")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|err| format!("desktop_sidecar_spawn_failed:{err}"))
}

fn wait_for_sidecar_health(port: u16) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if check_sidecar_health(port) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(200));
    }
    Err("desktop_sidecar_health_timeout".to_string())
}

fn check_sidecar_health(port: u16) -> bool {
    let socket = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&socket, Duration::from_millis(300)) else {
        return false;
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));

    if stream
        .write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }

    let mut buffer = [0_u8; 256];
    match stream.read(&mut buffer) {
        Ok(size) if size > 0 => std::str::from_utf8(&buffer[..size])
            .map(|content| content.contains("200 OK"))
            .unwrap_or(false),
        _ => false,
    }
}

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .map(Path::to_path_buf)
        .expect("repo root should be available from src-tauri")
}

fn stronghold_key_deriver(password: &str) -> Vec<u8> {
    let params = Params::new(64 * 1024, 3, 1, Some(32))
        .expect("argon2 params should be valid");
    let mut output = [0_u8; 32];
    Argon2::new(Algorithm::Argon2id, Version::V0x13, params)
        .hash_password_into(password.as_bytes(), b"vibe-learner-stronghold", &mut output)
        .expect("stronghold password derivation should succeed");
    output.to_vec()
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_stronghold::Builder::new(|password| {
            stronghold_key_deriver(password.as_ref())
        }).build())
        .invoke_handler(tauri::generate_handler![desktop_runtime_config])
        .setup(|app| {
            let state = build_desktop_state(&app.handle())
                .map_err(|err| tauri::Error::Anyhow(std::io::Error::other(err).into()))?;
            app.manage(state);
            if let Some(window) = app.get_webview_window("main") {
                let state = app.state::<DesktopAppState>();
                inject_runtime_config_window(&window, state.inner())?;
            }
            Ok(())
        })
        .on_page_load(|window, _| {
            let window_handle = window.window();
            let app_handle = window_handle.app_handle();
            let state = app_handle.state::<DesktopAppState>();
            let _ = inject_runtime_config_webview(window, state.inner());
        })
        .run(tauri::generate_context!())
        .expect("error while running vibe learner desktop shell");
}
