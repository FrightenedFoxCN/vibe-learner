#![allow(non_snake_case)]

use dioxus::prelude::*;
use gloo_net::http::Request;
use vibe_learner_contracts::HealthResponse;

const APP_STYLE: &str = r#"
body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, sans-serif;
  background: #111827;
  color: #f3f4f6;
}

a {
  color: inherit;
  text-decoration: none;
}
"#;

fn main() {
    dioxus::launch(App);
}

fn api_base_url() -> &'static str {
    match option_env!("VIBE_LEARNER_RS_API_BASE_URL") {
        Some(value) => value,
        None => "http://127.0.0.1:9000",
    }
}

#[derive(Routable, Clone, PartialEq)]
enum Route {
    #[route("/")]
    Home {},
    #[route("/plan")]
    Plan {},
    #[route("/persona-spectrum")]
    PersonaSpectrum {},
    #[route("/scene-setup")]
    SceneSetup {},
    #[route("/settings")]
    Settings {},
}

fn App() -> Element {
    rsx! {
        document::Style { "{APP_STYLE}" }
        Router::<Route> {}
    }
}

#[component]
fn Home() -> Element {
    let api_base_url = api_base_url();
    let health = use_resource(move || async move {
        let response = Request::get(&format!("{api_base_url}/health"))
            .send()
            .await
            .ok()?;
        response.json::<HealthResponse>().await.ok()
    });
    let health_label = match &*health.read_unchecked() {
        Some(Some(response)) => format!("Backend reachable: {} {}", response.service, response.version),
        Some(None) => format!("Backend probe failed at {api_base_url}"),
        None => format!("Probing Rust backend at {api_base_url}"),
    };
    let pages = [
        ("Plan", Route::Plan {}, "Document ingest, study-unit cleanup, and learning plan orchestration."),
        ("Persona Spectrum", Route::PersonaSpectrum {}, "Persona editing, card generation, and profile management."),
        ("Scene Setup", Route::SceneSetup {}, "Scene graph editing, reuse nodes, and saved scene libraries."),
        ("Settings", Route::Settings {}, "Model/provider configuration, capabilities, and tool policies."),
    ];

    rsx! {
        main {
            style: "max-width: 1100px; margin: 0 auto; padding: 48px 24px 80px;",
            h1 { style: "margin: 0 0 12px; font-size: 40px;", "Vibe Learner Rust Rewrite" }
            p {
                style: "max-width: 760px; margin: 0 0 32px; color: #cbd5e1; line-height: 1.7;",
                "This frontend is a clean-room Rust entrypoint for replacing the current Next.js UI.
                The route structure mirrors the current product surfaces before feature parity work begins."
            }
            div {
                style: "margin: 0 0 24px; padding: 14px 16px; border: 1px solid #334155; background: #0f172a; border-radius: 14px; color: #cbd5e1;",
                "{health_label}"
            }
            div {
                style: "display: grid; gap: 16px;",
                for (title, route, summary) in pages {
                    LinkCard { title: title, route: route, summary: summary }
                }
            }
        }
    }
}

#[component]
fn LinkCard(title: &'static str, route: Route, summary: &'static str) -> Element {
    rsx! {
        Link {
            to: route,
            style: "display: block; padding: 20px 22px; border: 1px solid #334155; background: #0f172a; border-radius: 16px;",
            strong { style: "display: block; margin-bottom: 8px; font-size: 18px;", "{title}" }
            span { style: "display: block; color: #cbd5e1; line-height: 1.7;", "{summary}" }
        }
    }
}

#[component]
fn Plan() -> Element {
    rsx! {
        SurfacePage {
            title: "Plan",
            summary: "Target replacement for document setup, planning context, plan overview, and study-session entry.",
        }
    }
}

#[component]
fn PersonaSpectrum() -> Element {
    rsx! {
        SurfacePage {
            title: "Persona Spectrum",
            summary: "Target replacement for persona CRUD, persona-card library, assist flows, and import/export.",
        }
    }
}

#[component]
fn SceneSetup() -> Element {
    rsx! {
        SurfacePage {
            title: "Scene Setup",
            summary: "Target replacement for layered scene editing, scene library, reusable nodes, and scene generation.",
        }
    }
}

#[component]
fn Settings() -> Element {
    rsx! {
        SurfacePage {
            title: "Settings",
            summary: "Target replacement for provider settings, model capability probing, and runtime tool switches.",
        }
    }
}

#[component]
fn SurfacePage(title: &'static str, summary: &'static str) -> Element {
    rsx! {
        main {
            style: "max-width: 900px; margin: 0 auto; padding: 48px 24px 80px;",
            Link {
                to: Route::Home {},
                style: "display: inline-block; margin-bottom: 24px; color: #93c5fd;",
                "← Back"
            }
            h1 { style: "margin: 0 0 12px; font-size: 36px;", "{title}" }
            p {
                style: "margin: 0 0 24px; color: #cbd5e1; line-height: 1.7;",
                "{summary}"
            }
            ul {
                style: "display: grid; gap: 10px; padding-left: 20px; color: #e2e8f0; line-height: 1.7;",
                li { "Rust routes should speak in the same product vocabulary as the current app." }
                li { "Shared contracts should be ported before rebuilding complex state flows." }
                li { "Keep local-first behavior: file storage, debug traces, and plan history stay first-class." }
            }
        }
    }
}
