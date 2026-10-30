// Compile the production save adapter and filesystem tests as an integration target.
#[path = "support/json_export_file.rs"]
mod filesystem;
#[path = "../src/json_export.rs"]
mod json_export;

mod tests {
    use super::filesystem::file;
    use super::json_export::*;
    use std::path::PathBuf;

    const MAX_JSON_BYTES: usize = 32 * 1024 * 1024;

    fn must_not_select(_: &str) -> Result<Option<PathBuf>, &'static str> {
        panic!("invalid input must not open a save dialog")
    }

    #[test]
    fn accepts_exact_32_mib_and_rejects_one_byte_more_before_dialog() {
        let root = file::tests::TestDirectory::new();
        let path = root.path().join("maximum.json");
        let mut contents = format!("\"{}\"", "x".repeat(MAX_JSON_BYTES - 2));
        let mut selected = false;
        assert_eq!(
            save("export.json", &contents, |_| {
                selected = true;
                Ok(Some(path.clone()))
            }),
            Ok(true)
        );
        assert!(selected);
        assert_eq!(std::fs::read(&path).unwrap(), contents.as_bytes());
        contents.push(' ');
        assert_eq!(
            save("export.json", &contents, must_not_select),
            Err("export_json_too_large")
        );
        assert_eq!(
            std::fs::metadata(&path).unwrap().len(),
            MAX_JSON_BYTES as u64
        );
        root.assert_only(&path);
    }

    #[test]
    fn byte_budget_counts_utf8_bytes() {
        let contents = format!("\"{}\"", "学".repeat(MAX_JSON_BYTES / 3 + 1));
        assert!(contents.chars().count() < MAX_JSON_BYTES);
        assert!(contents.len() > MAX_JSON_BYTES);
        assert_eq!(
            save("export.json", &contents, must_not_select),
            Err("export_json_too_large")
        );
    }

    #[test]
    fn rejects_invalid_json_and_trailing_data_before_dialog() {
        for contents in [
            "",
            "{",
            "{\"private\":}",
            "{} []",
            "NaN",
            "[1,]",
            "\"unterminated",
            "1e9999",
            r#""\uD800""#,
            r#"{"\uDC00":true}"#,
        ] {
            assert_eq!(
                save("export.json", contents, must_not_select),
                Err("export_json_invalid")
            );
        }
    }

    #[test]
    fn native_cancellation_adapter_returns_false() {
        // Inject the native adapter's None, without opening a Tauri dialog.
        let mut calls = 0;
        assert_eq!(
            save("../../report.json", "{}", |suggested| {
                calls += 1;
                assert_eq!(suggested, "report.json");
                Ok(None)
            }),
            Ok(false)
        );
        assert_eq!(calls, 1);
    }

    #[test]
    fn suggestion_never_supplies_a_destination() {
        for (filename, expected) in [
            ("../../report.json", "report.json"),
            (r"C:\private\report.json", "report.json"),
            ("", "export.json"),
            ("/", "export.json"),
            ("..", "export.json"),
        ] {
            assert_eq!(
                save(filename, "null", |suggested| {
                    assert_eq!(suggested, expected);
                    Ok(None)
                }),
                Ok(false)
            );
        }
    }

    #[test]
    fn rejects_nonlocal_or_relative_selection_with_safe_error() {
        assert_eq!(
            save("export.json", "{}", |_| Err("export_path_invalid")),
            Err("export_path_invalid")
        );
        assert_eq!(
            save("export.json", "{}", |_| Ok(Some(PathBuf::from(
                "relative.json"
            )))),
            Err("export_path_invalid")
        );
    }

    #[test]
    fn selected_destination_saves_original_bytes_and_overwrites_with_readback() {
        let root = file::tests::TestDirectory::new();
        let path = root.path().join("chosen.json");
        let original = "{\n  \"text\": \"学习 🦊\"\n}\n";
        assert_eq!(
            save("suggestion.json", original, |_| Ok(Some(path.clone()))),
            Ok(true)
        );
        assert_eq!(std::fs::read(&path).unwrap(), original.as_bytes());
        assert!(!root.path().join("suggestion.json").exists());
        assert_eq!(
            save("unused.json", "{}", |_| Ok(Some(path.clone()))),
            Ok(true)
        );
        assert_eq!(std::fs::read(&path).unwrap(), b"{}");
        root.assert_only(&path);
    }

    #[test]
    fn above_old_8_mib_limit_saves_and_reads_back() {
        let root = file::tests::TestDirectory::new();
        let path = root.path().join("large.json");
        let contents = format!("\"{}\"", "x".repeat(8 * 1024 * 1024));
        assert_eq!(
            save("export.json", &contents, |_| Ok(Some(path.clone()))),
            Ok(true)
        );
        assert_eq!(std::fs::read(&path).unwrap(), contents.as_bytes());
        root.assert_only(&path);
    }

    #[test]
    fn diagnostic_snapshot_fixture_survives_save_and_readback() {
        let root = file::tests::TestDirectory::new();
        let path = root.path().join("diagnostics.json");
        let contents =
            include_str!("../../../../packages/shared/fixtures/diagnostics/export-sample-v1.json");
        assert_eq!(
            save("diagnostics.json", contents, |_| Ok(Some(path.clone()))),
            Ok(true)
        );
        let bytes = std::fs::read(&path).unwrap();
        assert_eq!(bytes, contents.as_bytes());
        let snapshot: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(snapshot["schema_version"], "diagnostic-export-v1");
        root.assert_only(&path);
    }

    #[test]
    fn io_failure_exposes_only_fixed_error() {
        let root = file::tests::TestDirectory::new();
        let path = root
            .path()
            .join("private-missing-directory")
            .join("private.json");
        assert_eq!(
            save("export.json", "{\"private\":true}", |_| Ok(Some(path))),
            Err("export_write_failed")
        );
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
    }
}
