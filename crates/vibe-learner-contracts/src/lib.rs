use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DocumentStatus {
    Uploaded,
    Processing,
    Processed,
    Failed,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct DocumentRecord {
    pub id: Uuid,
    pub title: String,
    pub original_filename: String,
    pub stored_path: String,
    pub status: DocumentStatus,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct LearningPlanRecord {
    pub id: Uuid,
    pub document_id: Uuid,
    pub persona_id: Uuid,
    pub course_title: String,
    pub objective: String,
    pub study_chapters: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CreateLearningPlanRequest {
    pub document_id: Uuid,
    pub persona_id: Uuid,
    pub course_title: String,
    pub objective: String,
    pub study_chapters: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PersonaRecord {
    pub id: Uuid,
    pub name: String,
    pub summary: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CreatePersonaRequest {
    pub name: String,
    pub summary: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct StudySessionRecord {
    pub id: Uuid,
    pub plan_id: Uuid,
    pub persona_id: Uuid,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RewriteSurface {
    pub id: String,
    pub status: String,
    pub scope: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RewriteStatusResponse {
    pub branch: String,
    pub goal: String,
    pub completed_today: Vec<String>,
    pub next_steps: Vec<String>,
    pub surfaces: Vec<RewriteSurface>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PlanProvider {
    Mock,
    Openai,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeSettingsRecord {
    pub updated_at: String,
    pub plan_provider: PlanProvider,
    pub openai_plan_model: String,
    pub openai_chat_model: String,
    pub show_debug_info: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeSettingsPatch {
    pub plan_provider: Option<PlanProvider>,
    pub openai_plan_model: Option<String>,
    pub openai_chat_model: Option<String>,
    pub show_debug_info: Option<bool>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PlanningStudyUnit {
    pub unit_id: String,
    pub title: String,
    pub summary: String,
    pub page_start: u32,
    pub page_end: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct DocumentPlanningContext {
    pub document_id: Uuid,
    pub course_outline: Vec<String>,
    pub study_units: Vec<PlanningStudyUnit>,
    pub available_tools: Vec<String>,
}
