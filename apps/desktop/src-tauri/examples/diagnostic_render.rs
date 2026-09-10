//! Opt-in native WebView fixture host. No sidecar, Vault or production app setup.
fn main() {
    let url = std::env::args().nth(1).expect("local benchmark URL required");
    let parsed: tauri::Url = url.parse().expect("valid benchmark URL");
    assert_eq!(parsed.scheme(), "http");
    assert_eq!(parsed.host_str(), Some("127.0.0.1"));
    let mut context = tauri::generate_context!();
    context.config_mut().app.windows.clear();
    context.config_mut().identifier = "com.vibelearner.diagnostic-render-probe".into();
    tauri::Builder::default()
        .setup(move |app| {
            tauri::WebviewWindowBuilder::new(app, "diagnostic-render", tauri::WebviewUrl::External(parsed))
                .title("Vibe Diagnostic Render Probe")
                .inner_size(1280.0, 900.0)
                .build()?;
            Ok(())
        })
        .run(context)
        .expect("native benchmark host failed");
}
