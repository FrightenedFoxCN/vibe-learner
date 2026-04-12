use axum::extract::{Multipart, Path, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde_json::json;
use uuid::Uuid;
use vibe_learner_contracts::{
    CreateLearningPlanRequest, CreatePersonaRequest, DocumentPlanningContext, DocumentRecord,
    HealthResponse, LearningPlanRecord, PersonaRecord, PlanningStudyUnit, RewriteStatusResponse,
    RewriteSurface, RuntimeSettingsPatch, RuntimeSettingsRecord,
};

use crate::state::AppState;
use crate::store::StoreError;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/health", get(healthcheck))
        .route("/api/rewrite-status", get(rewrite_status))
        .route("/api/documents", get(list_documents).post(create_document))
        .route("/api/documents/{document_id}/file", get(get_document_file))
        .route(
            "/api/documents/{document_id}/planning-context",
            get(get_document_planning_context),
        )
        .route(
            "/api/learning-plans",
            get(list_learning_plans).post(create_learning_plan),
        )
        .route(
            "/api/runtime-settings",
            get(get_runtime_settings).patch(patch_runtime_settings),
        )
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

async fn list_documents(
    State(state): State<AppState>,
) -> Result<Json<Vec<DocumentRecord>>, AppError> {
    state
        .store
        .list_documents()
        .map(Json)
        .map_err(map_store_error)
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
        let bytes = field.bytes().await.map_err(|error| {
            AppError::bad_request(format!("cannot read uploaded file: {error}"))
        })?;

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
    let document = state
        .store
        .find_document(document_id)
        .map_err(map_store_error)?;
    let bytes = state
        .store
        .read_document_bytes(document_id)
        .map_err(map_store_error)?;

    let media_type = if document
        .original_filename
        .to_ascii_lowercase()
        .ends_with(".pdf")
    {
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

async fn get_document_planning_context(
    State(state): State<AppState>,
    Path(document_id): Path<Uuid>,
) -> Result<Json<DocumentPlanningContext>, AppError> {
    let document = state
        .store
        .find_document(document_id)
        .map_err(map_store_error)?;
    let related_plans = state
        .store
        .list_learning_plans()
        .map_err(map_store_error)?
        .into_iter()
        .filter(|plan| plan.document_id == document_id)
        .collect::<Vec<_>>();

    let outline = related_plans
        .iter()
        .flat_map(|plan| plan.study_chapters.iter().cloned())
        .collect::<Vec<_>>();

    let study_units = if outline.is_empty() {
        vec![PlanningStudyUnit {
            unit_id: format!("{}-overview", document_id),
            title: document.title,
            summary: "Initial planning context generated from uploaded document metadata."
                .to_string(),
            page_start: 1,
            page_end: 1,
        }]
    } else {
        outline
            .iter()
            .enumerate()
            .map(|(index, chapter)| PlanningStudyUnit {
                unit_id: format!("{}-{}", document_id, index + 1),
                title: chapter.clone(),
                summary: format!("Study unit scaffold for chapter `{chapter}`."),
                page_start: (index as u32) + 1,
                page_end: (index as u32) + 1,
            })
            .collect()
    };

    Ok(Json(DocumentPlanningContext {
        document_id,
        course_outline: outline,
        study_units,
        available_tools: vec![
            "get_study_unit_detail".to_string(),
            "read_page_range_content".to_string(),
        ],
    }))
}

async fn list_personas(
    State(state): State<AppState>,
) -> Result<Json<Vec<PersonaRecord>>, AppError> {
    state
        .store
        .list_personas()
        .map(Json)
        .map_err(map_store_error)
}

async fn list_learning_plans(
    State(state): State<AppState>,
) -> Result<Json<Vec<LearningPlanRecord>>, AppError> {
    state
        .store
        .list_learning_plans()
        .map(Json)
        .map_err(map_store_error)
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

async fn create_learning_plan(
    State(state): State<AppState>,
    Json(payload): Json<CreateLearningPlanRequest>,
) -> Result<Json<LearningPlanRecord>, AppError> {
    if payload.course_title.trim().is_empty() {
        return Err(AppError::bad_request("course title is required"));
    }
    if payload.objective.trim().is_empty() {
        return Err(AppError::bad_request("learning objective is required"));
    }

    state
        .store
        .create_learning_plan(payload)
        .map(Json)
        .map_err(map_store_error)
}

async fn get_runtime_settings(
    State(state): State<AppState>,
) -> Result<Json<RuntimeSettingsRecord>, AppError> {
    state
        .store
        .get_runtime_settings()
        .map(Json)
        .map_err(map_store_error)
}

async fn patch_runtime_settings(
    State(state): State<AppState>,
    Json(payload): Json<RuntimeSettingsPatch>,
) -> Result<Json<RuntimeSettingsRecord>, AppError> {
    if payload
        .openai_plan_model
        .as_ref()
        .is_some_and(|value| value.trim().is_empty())
    {
        return Err(AppError::bad_request("openai plan model cannot be empty"));
    }
    if payload
        .openai_chat_model
        .as_ref()
        .is_some_and(|value| value.trim().is_empty())
    {
        return Err(AppError::bad_request("openai chat model cannot be empty"));
    }

    state
        .store
        .update_runtime_settings(payload)
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
