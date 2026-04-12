mod routes;
mod state;
mod store;

use std::env;
use std::net::SocketAddr;
use std::path::PathBuf;

use axum::Router;
use tokio::net::TcpListener;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing::info;

use crate::state::AppState;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            env::var("RUST_LOG")
                .unwrap_or_else(|_| "vibe_learner_ai_rs=debug,tower_http=info".to_string()),
        )
        .init();

    let app_state = AppState::new(default_data_dir()).expect("initialize rust ai state");
    let app = Router::new()
        .merge(routes::router())
        .with_state(app_state)
        .layer(CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any))
        .layer(TraceLayer::new_for_http());

    let port = env::var("VIBE_LEARNER_RS_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(9000);
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = TcpListener::bind(addr)
        .await
        .expect("bind rust ai service");

    info!("vibe-learner-ai-rs listening on http://{}", addr);

    axum::serve(listener, app)
        .await
        .expect("run rust ai service");
}

fn default_data_dir() -> PathBuf {
    env::var("VIBE_LEARNER_RS_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("data-rs"))
}
