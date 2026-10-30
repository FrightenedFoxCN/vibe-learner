//! JSON-only save adapter. Only the native dialog can supply the destination.
use std::path::PathBuf;

#[path = "json_export_file.rs"]
mod file;

// diagnostic-export-v1: backend serialized output and browser transport budget.
const MAX_JSON_BYTES: usize = 32 * 1024 * 1024;

pub(super) fn save(
    filename: &str,
    contents: &str,
    select: impl FnOnce(&str) -> Result<Option<PathBuf>, &'static str>,
) -> Result<bool, &'static str> {
    if contents.len() > MAX_JSON_BYTES {
        return Err("export_json_too_large");
    }
    // Preserve the existing strict JSON parser and write the original bytes.
    serde_json::from_str::<serde_json::Value>(contents).map_err(|_| "export_json_invalid")?;
    let suggested = filename
        .rsplit(['/', '\\'])
        .next()
        .filter(|name| !name.is_empty() && *name != "." && *name != "..")
        .unwrap_or("export.json");
    let Some(path) = select(suggested)? else {
        return Ok(false);
    };
    if !path.is_absolute() || path.file_name().is_none() {
        return Err("export_path_invalid");
    }
    file::replace(&path, contents.as_bytes()).map_err(|_| "export_write_failed")?;
    Ok(true)
}
