use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::de::DeserializeOwned;
use serde::Serialize;
use uuid::Uuid;
use vibe_learner_contracts::{CreatePersonaRequest, DocumentRecord, DocumentStatus, PersonaRecord};

#[derive(Debug)]
pub enum StoreError {
    Io(std::io::Error),
    Json(serde_json::Error),
    NotFound(String),
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(f, "{error}"),
            Self::Json(error) => write!(f, "{error}"),
            Self::NotFound(message) => write!(f, "{message}"),
        }
    }
}

impl std::error::Error for StoreError {}

impl From<std::io::Error> for StoreError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for StoreError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

#[derive(Debug)]
pub struct JsonStore {
    root: PathBuf,
    uploads_dir: PathBuf,
    write_lock: Mutex<()>,
}

impl JsonStore {
    pub fn new(root: PathBuf) -> Result<Self, StoreError> {
        let uploads_dir = root.join("uploads");
        fs::create_dir_all(&uploads_dir)?;

        Ok(Self {
            root,
            uploads_dir,
            write_lock: Mutex::new(()),
        })
    }

    pub fn list_documents(&self) -> Result<Vec<DocumentRecord>, StoreError> {
        self.load_list("documents.json")
    }

    pub fn create_document(
        &self,
        original_filename: &str,
        bytes: &[u8],
    ) -> Result<DocumentRecord, StoreError> {
        let _guard = self.write_lock.lock().expect("document store lock");
        let mut documents = self.load_list("documents.json")?;

        let document_id = Uuid::new_v4();
        let sanitized_name = sanitize_filename(original_filename);
        let stored_name = format!("{document_id}-{sanitized_name}");
        let stored_path = self.uploads_dir.join(stored_name);
        fs::write(&stored_path, bytes)?;

        let record = DocumentRecord {
            id: document_id,
            title: derive_title(original_filename),
            original_filename: original_filename.to_string(),
            stored_path: stored_path.to_string_lossy().to_string(),
            status: DocumentStatus::Uploaded,
        };
        documents.push(record.clone());
        self.save_list("documents.json", &documents)?;

        Ok(record)
    }

    pub fn find_document(&self, document_id: Uuid) -> Result<DocumentRecord, StoreError> {
        let documents = self.list_documents()?;
        documents
            .into_iter()
            .find(|document| document.id == document_id)
            .ok_or_else(|| StoreError::NotFound(format!("document {document_id} not found")))
    }

    pub fn read_document_bytes(&self, document_id: Uuid) -> Result<Vec<u8>, StoreError> {
        let document = self.find_document(document_id)?;
        let path = PathBuf::from(document.stored_path);
        if !path.exists() {
            return Err(StoreError::NotFound(format!(
                "document file for {document_id} not found"
            )));
        }
        Ok(fs::read(path)?)
    }

    pub fn list_personas(&self) -> Result<Vec<PersonaRecord>, StoreError> {
        self.load_list("personas.json")
    }

    pub fn create_persona(
        &self,
        payload: CreatePersonaRequest,
    ) -> Result<PersonaRecord, StoreError> {
        let _guard = self.write_lock.lock().expect("persona store lock");
        let mut personas = self.load_list("personas.json")?;
        let record = PersonaRecord {
            id: Uuid::new_v4(),
            name: payload.name.trim().to_string(),
            summary: payload.summary.trim().to_string(),
        };
        personas.push(record.clone());
        self.save_list("personas.json", &personas)?;
        Ok(record)
    }

    fn load_list<T>(&self, file_name: &str) -> Result<Vec<T>, StoreError>
    where
        T: DeserializeOwned,
    {
        let path = self.root.join(file_name);
        if !path.exists() {
            return Ok(Vec::new());
        }
        let raw = fs::read_to_string(path)?;
        Ok(serde_json::from_str(&raw)?)
    }

    fn save_list<T>(&self, file_name: &str, items: &[T]) -> Result<(), StoreError>
    where
        T: Serialize,
    {
        let path = self.root.join(file_name);
        let temp_path = self.root.join(format!("{file_name}.{}.tmp", Uuid::new_v4()));
        let payload = serde_json::to_string_pretty(items)?;
        fs::write(&temp_path, payload)?;
        fs::rename(temp_path, path)?;
        Ok(())
    }
}

fn derive_title(original_filename: &str) -> String {
    let stem = Path::new(original_filename)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("document");
    if stem.trim().is_empty() {
        "document".to_string()
    } else {
        stem.trim().to_string()
    }
}

fn sanitize_filename(original_filename: &str) -> String {
    let sanitized: String = original_filename
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_') {
                ch
            } else {
                '-'
            }
        })
        .collect();

    let trimmed = sanitized.trim_matches('-');
    if trimmed.is_empty() {
        "upload.bin".to_string()
    } else {
        trimmed.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root() -> PathBuf {
        std::env::temp_dir().join(format!("vibe-learner-ai-rs-test-{}", Uuid::new_v4()))
    }

    #[test]
    fn create_and_list_personas() {
        let root = temp_root();
        let store = JsonStore::new(root.clone()).expect("create store");

        let created = store
            .create_persona(CreatePersonaRequest {
                name: "Pilot".to_string(),
                summary: "Minimal persona".to_string(),
            })
            .expect("create persona");

        let personas = store.list_personas().expect("list personas");
        assert_eq!(personas.len(), 1);
        assert_eq!(personas[0], created);

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn create_document_writes_upload() {
        let root = temp_root();
        let store = JsonStore::new(root.clone()).expect("create store");

        let created = store
            .create_document("book.pdf", b"pdf-bytes")
            .expect("create document");

        assert!(PathBuf::from(&created.stored_path).exists());
        let documents = store.list_documents().expect("list documents");
        assert_eq!(documents.len(), 1);
        assert_eq!(documents[0], created);

        let _ = fs::remove_dir_all(root);
    }
}
