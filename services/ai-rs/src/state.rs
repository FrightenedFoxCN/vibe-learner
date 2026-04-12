use std::path::PathBuf;
use std::sync::Arc;

use crate::store::{JsonStore, StoreError};

#[derive(Clone, Debug)]
pub struct AppState {
    pub data_dir: PathBuf,
    pub store: Arc<JsonStore>,
}

impl AppState {
    pub fn new(data_dir: PathBuf) -> Result<Self, StoreError> {
        let store = Arc::new(JsonStore::new(data_dir.clone())?);
        Ok(Self { data_dir, store })
    }
}
