use axum::extract::{Multipart, Path, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde_json::json;
use uuid::Uuid;
use vibe_learner_contracts::{
    CreatePersonaRequest, DocumentRecord, HealthResponse, PersonaRecord, RewriteStatusResponse,
    RewriteSurface,
};

use crate::state::AppState;
use crate::store::StoreError;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/health", get(healthcheck))
        .route("/api/rewrite-status", get(rewrite_status))
        .route("/api/documents", get(list_documents).post(create_document))
        .route("/api/documents/{document_id}/file", get(get_document_file))
        .route("/api/personas", get(list_personas).post(create_persona))
}

async fn healthcheck() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok".to_string(),
        service: "vibe-learner-ai-rs".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

async fn rewrite_status(State(state): State<AppState>) -> Json<RewriteStatusResponse> {
    let data_dir = state.data_dir.to_string_lossy().to_string();

    Json(RewriteStatusResponse {
        branch: "rust-rewrite-spike".to_string(),
        goal: "Replace the current Next.js + FastAPI stack with Rust services and a Rust UI."
            .to_string(),
        completed_today: vec![
            "Created a top-level Cargo workspace.".to_string(),
            "Added a shared contracts crate for core records.".to_string(),
            "Added an Axum backend entrypoint with local JSON-backed document and persona persistence."
                .to_string(),
            "Reserved a separate data root for the Rust rewrite path.".to_string(),
        ],
        next_steps: vec![
            "Port document upload, parse orchestration, and plan generation routes.".to_string(),
            format!("Expand the JSON/file persistence rooted at {}.", data_dir),
            "Replace placeholder contracts with parity-checked API/domain models.".to_string(),
            "Connect the Rust frontend to the Axum API.".to_string(),
        ],
        surfaces: vec![
            RewriteSurface {
                id: "learning_workspace".to_string(),
                status: "in_progress".to_string(),
                scope: "Plan generation, plan history, study workflow shell".to_string(),
            },
            RewriteSurface {
                id: "persona_spectrum".to_string(),
                status: "in_progress".to_string(),
                scope: "Persona editing, persona card generation, import/export".to_string(),
            },
            RewriteSurface {
                id: "scene_setup".to_string(),
                status: "pending".to_string(),
                scope: "Scene tree editing, reusable nodes, library persistence".to_string(),
            },
            RewriteSurface {
                id: "runtime_settings".to_string(),
                status: "pending".to_string(),
                scope: "Provider settings, model capability probes, tool toggles".to_string(),
            },
            RewriteSurface {
                id: "document_pipeline".to_string(),
                status: "in_progress".to_string(),
                scope: "PDF upload, OCR fallback, study-unit cleanup, debug traces".to_string(),
            },
        ],
    })
}

async fn list_documents(State(state): State<AppState>) -> Result<Json<Vec<DocumentRecord>>, AppError> {
    state.store.list_documents().map(Json).map_err(map_store_error)
}

async fn create_document(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<DocumentRecord>, AppError> {
    let mut upload: Option<(String, Vec<u8>)> = None;

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|error| AppError::bad_request(format!("invalid multipart payload: {error}")))?
    {
        if field.name() != Some("file") {
            continue;
        }

        let file_name = field
            .file_name()
            .map(|value| value.to_string())
            .unwrap_or_else(|| "document.pdf".to_string());
        let bytes = field
            .bytes()
            .await
            .map_err(|error| AppError::bad_request(format!("cannot read uploaded file: {error}")))?;

        upload = Some((file_name, bytes.to_vec()));
        break;
    }

    let (file_name, bytes) =
        upload.ok_or_else(|| AppError::bad_request("multipart field `file` is required"))?;

    state
        .store
        .create_document(&file_name, &bytes)
        .map(Json)
        .map_err(map_store_error)
}

async fn get_document_file(
    State(state): State<AppState>,
    Path(document_id): Path<Uuid>,
) -> Result<Response, AppError> {
    let document = state.store.find_document(document_id).map_err(map_store_error)?;
    let bytes = state
        .store
        .read_document_bytes(document_id)
        .map_err(map_store_error)?;

    let media_type = if document.original_filename.to_ascii_lowercase().ends_with(".pdf") {
        "application/pdf"
    } else {
        "application/octet-stream"
    };
    let mut headers = HeaderMap::new();
    headers.insert(
        header::CONTENT_TYPE,
        media_type
            .parse()
            .expect("valid content type for uploaded document"),
    );
    headers.insert(
        header::CONTENT_DISPOSITION,
        format!("inline; filename=\"{}\"", document.original_filename)
            .parse()
            .expect("valid content disposition"),
    );

    Ok((headers, bytes).into_response())
}

async fn list_personas(State(state): State<AppState>) -> Result<Json<Vec<PersonaRecord>>, AppError> {
    state.store.list_personas().map(Json).map_err(map_store_error)
}

async fn create_persona(
    State(state): State<AppState>,
    Json(payload): Json<CreatePersonaRequest>,
) -> Result<Json<PersonaRecord>, AppError> {
    if payload.name.trim().is_empty() {
        return Err(AppError::bad_request("persona name is required"));
    }
    if payload.summary.trim().is_empty() {
        return Err(AppError::bad_request("persona summary is required"));
    }

    state
        .store
        .create_persona(payload)
        .map(Json)
        .map_err(map_store_error)
}

#[derive(Debug)]
struct AppError {
    status: StatusCode,
    message: String,
}

impl AppError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn internal(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: message.into(),
        }
    }

    fn not_found(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            message: message.into(),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({ "error": self.message }))).into_response()
    }
}

fn map_store_error(error: StoreError) -> AppError {
    match error {
        StoreError::NotFound(message) => AppError::not_found(message),
        other => AppError::internal(other.to_string()),
    }
}
