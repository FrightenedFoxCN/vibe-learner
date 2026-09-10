use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

mod diagnostics;
use diagnostics::{DesktopDiagnostics, DesktopEvent};
use std::thread;
use std::time::{Duration, Instant};

use argon2::{Algorithm, Argon2, Params, Version};
use serde::Serialize;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{Emitter, Manager, Runtime};
use tauri_plugin_dialog::DialogExt;

const DESKTOP_VIEW_MENU_ID: &str = "desktop-view-menu";
const DESKTOP_VIEW_TOGGLE_NAV_ID: &str = "desktop-view-toggle-sidebar";
const DESKTOP_VIEW_TOGGLE_DEBUG_ID: &str = "desktop-view-toggle-debug-overlay";
const DESKTOP_VIEW_TOGGLE_NAV_EVENT: &str = "desktop-view-toggle-sidebar";
const DESKTOP_VIEW_TOGGLE_DEBUG_EVENT: &str = "desktop-view-toggle-debug-overlay";
const SIDECAR_BINARY_NAME: &str = "vibe-learner-sidecar";
const ONNXTR_RESOURCE_DIR: &str = "ocr/onnxtr";
const REQUIRED_ONNXTR_MODEL_FILES: [&str; 3] =
    ["detector.onnx", "recognizer.onnx", "recognizer_vocab.txt"];

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
    startup_error: String,
}

struct ManagedSidecar {
    child: Option<Child>,
    diagnostics: DesktopDiagnostics,
    shutdown_recorded: bool,
    exit_observed: bool,
}

impl ManagedSidecar {
    fn shutdown(&mut self) {
        if self.shutdown_recorded { return; }
        self.shutdown_recorded = true;
        self.diagnostics.emit(DesktopEvent::DesktopShutdownRequested, None, None);
        if let Some(mut child) = self.child.take() {
            // The one-file PyInstaller launcher owns another Python process.
            // Each sidecar is spawned in its own group; killing only the launcher
            // leaves the server and its session credentials alive after exit.
            #[cfg(unix)]
            unsafe {
                libc::killpg(child.id() as libc::pid_t, libc::SIGKILL);
            }
            let _ = child.kill();
            let status = child.wait().ok();
            self.diagnostics.emit(if status.is_some() { DesktopEvent::SidecarStopped } else { DesktopEvent::SidecarShutdownUnknown }, None, status.and_then(|status| status.code()));
        }
        self.diagnostics.emit(DesktopEvent::DesktopStopped, None, None);
    }

    fn observe_exit(&mut self) -> bool {
        if self.exit_observed { return true; }
        if let Some(child) = &mut self.child {
            if let Ok(Some(status)) = child.try_wait() {
                self.diagnostics.emit(DesktopEvent::SidecarExited, None, status.code());
                // Retain the launcher identity so shutdown still fences its process group.
                self.exit_observed = true;
            }
        }
        self.child.is_none() || self.exit_observed
    }
}

impl Drop for ManagedSidecar {
    fn drop(&mut self) {
        self.shutdown();
    }
}

struct DesktopAppState {
    ai_base_url: String,
    storage_root: String,
    vault_path: String,
    vault_state: &'static str,
    startup_error: String,
    _sidecar: Arc<Mutex<ManagedSidecar>>,
}

impl DesktopAppState {
    fn shutdown_sidecar(&self) {
        if let Ok(mut sidecar) = self._sidecar.lock() {
            sidecar.shutdown();
        }
    }
}

#[tauri::command]
fn desktop_runtime_config(state: tauri::State<'_, DesktopAppState>) -> DesktopRuntimeConfig {
    runtime_config_from_state(state.inner())
}

#[tauri::command]
async fn desktop_export_json(app: tauri::AppHandle, filename: String, contents: String) -> Result<bool, String> {
    // The renderer supplies content and a suggestion, never a writable path.
    if contents.len() > 8 * 1024 * 1024 {
        return Err("export_json_too_large".into());
    }
    serde_json::from_str::<serde_json::Value>(&contents).map_err(|_| "export_json_invalid")?;
    let suggested = Path::new(&filename).file_name().and_then(|name| name.to_str()).unwrap_or("export.json").to_owned();
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app.dialog().file().add_filter("JSON", &["json"]).set_file_name(suggested).blocking_save_file();
        let Some(selected) = selected else { return Ok(false); };
        let path = selected.into_path().map_err(|_| "export_path_invalid")?;
        fs::write(path, contents.as_bytes()).map_err(|_| "export_write_failed")?;
        Ok(true)
    }).await.map_err(|_| "export_dialog_failed".to_owned())?
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
        vault_state: current_vault_state(state),
        vault_path: state.vault_path.clone(),
        storage_root: state.storage_root.clone(),
        startup_error: state.startup_error.clone(),
    }
}

fn current_vault_state(state: &DesktopAppState) -> &'static str {
    if state.vault_state == "unconfigured" && Path::new(&state.vault_path).exists() {
        "locked"
    } else {
        state.vault_state
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

    let diagnostics = DesktopDiagnostics::new(&storage_root);
    let startup_started = Instant::now();
    diagnostics.emit(DesktopEvent::DesktopStarted, None, None);
    let vault_path = app_data_dir.join("vibe-learner.secrets.hold");
    let vault_state = if vault_path.exists() {
        "locked"
    } else {
        "unconfigured"
    };

    let port = available_port().map_err(|err| format!("desktop_port_allocation_failed:{err}"))?;
    let ai_base_url = format!("http://127.0.0.1:{port}");
    let mut startup_error = String::new();
    let mut managed_sidecar = ManagedSidecar { child: None, diagnostics: diagnostics.clone(), shutdown_recorded: false, exit_observed: false };

    match spawn_sidecar_process(app, port, &storage_root) {
        Ok(child) => {
            managed_sidecar.child = Some(child);
            diagnostics.emit(DesktopEvent::SidecarSpawned, Some(startup_started.elapsed().as_millis() as u64), None);
            if let Err(err) = wait_for_sidecar_health(port) {
                startup_error = err;
            }
        }
        Err(err) => {
            startup_error = err;
        }
    }

    diagnostics.emit(if startup_error.is_empty() { DesktopEvent::SidecarReady } else { DesktopEvent::SidecarStartupFailed }, Some(startup_started.elapsed().as_millis() as u64), None);
    if !startup_error.is_empty() {
        eprintln!("desktop_startup_error:{startup_error}");
    }

    Ok(DesktopAppState {
        ai_base_url,
        storage_root: storage_root.to_string_lossy().into_owned(),
        vault_path: vault_path.to_string_lossy().into_owned(),
        vault_state,
        startup_error,
        _sidecar: Arc::new(Mutex::new(managed_sidecar)),
    })
}

fn available_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn spawn_sidecar_process(
    app: &tauri::AppHandle,
    port: u16,
    storage_root: &Path,
) -> Result<Child, String> {
    let bundled_sidecar = bundled_sidecar_path(app);
    let services_ai_dir = repo_root().join("services").join("ai");
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

    let mut command = if let Some(sidecar_path) = bundled_sidecar {
        Command::new(sidecar_path)
    } else {
        if !services_ai_dir.exists() {
            return Err(format!(
                "desktop_sidecar_source_missing:{}",
                services_ai_dir.display()
            ));
        }

        let mut source_command = Command::new("uv");
        source_command
            .current_dir(&services_ai_dir)
            .arg("run")
            .arg("python")
            .arg("-m")
            .arg("app.sidecar");
        source_command
    };

    command
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .env("DATABASE_URL", database_url)
        .env("VIBE_LEARNER_STORAGE_ROOT", storage_root)
        .env("VIBE_LEARNER_DESKTOP_MODE", "true")
        .env("VIBE_LEARNER_ALLOWED_ORIGINS", allowed_origins)
        .env("VIBE_LEARNER_OCR_ENGINE", "onnxtr");

    if let Some(model_dir) = bundled_onnxtr_model_dir(app) {
        command.env("VIBE_LEARNER_ONNXTR_MODEL_DIR", model_dir);
    }

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }

    command
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

fn sidecar_binary_file_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "vibe-learner-sidecar.exe"
    } else {
        SIDECAR_BINARY_NAME
    }
}

fn bundled_sidecar_path(app: &tauri::AppHandle) -> Option<PathBuf> {
    let executable_name = sidecar_binary_file_name();

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            let candidate = parent.join(executable_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    let resource_dir = app.path().resource_dir().ok()?;
    let candidate = resource_dir.join(executable_name);
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

fn bundled_onnxtr_model_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let candidate = resource_dir.join(ONNXTR_RESOURCE_DIR);
    if REQUIRED_ONNXTR_MODEL_FILES
        .iter()
        .all(|file_name| candidate.join(file_name).exists())
    {
        Some(candidate)
    } else {
        None
    }
}

fn stronghold_key_deriver(password: &str) -> Vec<u8> {
    let params = Params::new(64 * 1024, 3, 1, Some(32)).expect("argon2 params should be valid");
    let mut output = [0_u8; 32];
    Argon2::new(Algorithm::Argon2id, Version::V0x13, params)
        .hash_password_into(password.as_bytes(), b"vibe-learner-stronghold", &mut output)
        .expect("stronghold password derivation should succeed");
    output.to_vec()
}

fn build_desktop_view_submenu<R: Runtime>(app: &tauri::AppHandle<R>) -> tauri::Result<Submenu<R>> {
    let toggle_nav = MenuItem::with_id(
        app,
        DESKTOP_VIEW_TOGGLE_NAV_ID,
        "切换导航侧栏",
        true,
        Some("CmdOrCtrl+Alt+1"),
    )?;
    let toggle_debug = MenuItem::with_id(
        app,
        DESKTOP_VIEW_TOGGLE_DEBUG_ID,
        "切换调试浮窗",
        true,
        Some("CmdOrCtrl+Alt+D"),
    )?;
    Submenu::with_id_and_items(
        app,
        DESKTOP_VIEW_MENU_ID,
        "View",
        true,
        &[&toggle_nav, &toggle_debug],
    )
}

fn append_desktop_view_items<R: Runtime>(
    submenu: &Submenu<R>,
    app: &tauri::AppHandle<R>,
) -> tauri::Result<()> {
    let separator = PredefinedMenuItem::separator(app)?;
    let toggle_nav = MenuItem::with_id(
        app,
        DESKTOP_VIEW_TOGGLE_NAV_ID,
        "切换导航侧栏",
        true,
        Some("CmdOrCtrl+Alt+1"),
    )?;
    let toggle_debug = MenuItem::with_id(
        app,
        DESKTOP_VIEW_TOGGLE_DEBUG_ID,
        "切换调试浮窗",
        true,
        Some("CmdOrCtrl+Alt+D"),
    )?;
    submenu.append(&separator)?;
    submenu.append(&toggle_nav)?;
    submenu.append(&toggle_debug)?;
    Ok(())
}

fn install_desktop_menu<R: Runtime>(app: &tauri::AppHandle<R>) -> tauri::Result<()> {
    let menu = Menu::default(app)?;

    #[cfg(target_os = "macos")]
    {
        let existing_view_menu = menu.items()?.into_iter().find_map(|item| {
            let submenu = item.as_submenu()?.clone();
            match submenu.text() {
                Ok(text) if text == "View" => Some(submenu),
                _ => None,
            }
        });

        if let Some(view_menu) = existing_view_menu {
            append_desktop_view_items(&view_menu, app)?;
        } else {
            let view_menu = build_desktop_view_submenu(app)?;
            menu.insert(&view_menu, 2)?;
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        let view_menu = build_desktop_view_submenu(app)?;
        menu.insert(&view_menu, 2)?;
    }

    app.set_menu(menu)?;
    Ok(())
}

fn emit_desktop_view_event<R: Runtime>(app: &tauri::AppHandle<R>, event_name: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit(event_name, ());
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_stronghold::Builder::new(|password| {
                stronghold_key_deriver(password.as_ref())
            })
            .build(),
        )
        .invoke_handler(tauri::generate_handler![desktop_runtime_config, desktop_export_json])
        .setup(|app| {
            install_desktop_menu(&app.handle())?;
            let state = build_desktop_state(&app.handle())
                .map_err(|err| tauri::Error::Anyhow(std::io::Error::other(err).into()))?;
            let monitored = state._sidecar.clone();
            if thread::Builder::new().name("sidecar-diagnostics".into()).spawn(move || loop {
                match monitored.lock() {
                    Ok(mut sidecar) => { if sidecar.observe_exit() { break; } },
                    Err(_) => break,
                }
                thread::sleep(Duration::from_millis(250));
            }).is_err() {
                eprintln!("desktop_diagnostic_monitor_start_failed");
            }
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
        .on_menu_event(|app, event| {
            if event.id() == DESKTOP_VIEW_TOGGLE_NAV_ID {
                emit_desktop_view_event(app, DESKTOP_VIEW_TOGGLE_NAV_EVENT);
            } else if event.id() == DESKTOP_VIEW_TOGGLE_DEBUG_ID {
                emit_desktop_view_event(app, DESKTOP_VIEW_TOGGLE_DEBUG_EVENT);
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building vibe learner desktop shell")
        .run(|app, event| match event {
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                if let Some(state) = app.try_state::<DesktopAppState>() {
                    state.shutdown_sidecar();
                }
            }
            _ => {}
        });
}

#[cfg(all(test, unix))]
mod sidecar_diagnostic_tests {
    use super::*;
    use std::os::unix::process::CommandExt;
    fn root() -> PathBuf {
        std::env::temp_dir().join(format!("sidecar-diagnostic-test-{}-{}", std::process::id(), std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()))
    }
    fn records(root: &Path) -> Vec<serde_json::Value> {
        fs::read_dir(root.join("diagnostics/desktop-spool")).unwrap().filter_map(Result::ok)
            .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "json"))
            .map(|entry| serde_json::from_slice(&fs::read(entry.path()).unwrap()).unwrap()).collect()
    }
    #[test]
    fn records_real_unexpected_exit_once() {
        let root = root();
        let child = Command::new("sh").args(["-c", "exit 7"]).process_group(0).spawn().unwrap();
        let mut sidecar = ManagedSidecar { child: Some(child), diagnostics: DesktopDiagnostics::new(&root), shutdown_recorded: false, exit_observed: false };
        let deadline = Instant::now() + Duration::from_secs(3);
        while !sidecar.observe_exit() && Instant::now() < deadline { thread::sleep(Duration::from_millis(10)); }
        assert!(sidecar.observe_exit());
        assert!(sidecar.child.is_some()); // Keep process-group cleanup possible after launcher exit.
        let events = records(&root);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["name"], "sidecar_exited");
        assert_eq!(events[0]["exit_code"], 7);
        sidecar.shutdown();
        drop(sidecar);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn records_real_normal_shutdown_without_duplicate_drop_events() {
        let root = root();
        let child = Command::new("sh").args(["-c", "sleep 30"]).process_group(0).spawn().unwrap();
        let mut sidecar = ManagedSidecar { child: Some(child), diagnostics: DesktopDiagnostics::new(&root), shutdown_recorded: false, exit_observed: false };
        sidecar.shutdown();
        sidecar.shutdown();
        drop(sidecar);
        let events = records(&root);
        assert_eq!(events.len(), 3);
        assert_eq!(events.iter().filter(|event| event["name"] == "sidecar_stopped").count(), 1);
        assert_eq!(events.iter().filter(|event| event["name"] == "desktop_stopped").count(), 1);
        fs::remove_dir_all(root).unwrap();
    }
}
