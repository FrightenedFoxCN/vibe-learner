// Compile the production std-only implementation in the test module so failure
// injection can exercise its private staging boundary. This is also a rustc test target.
pub(crate) mod file {
    include!("../../src/json_export_file.rs");

    #[cfg(test)]
    pub(crate) mod tests {
        use super::*;

        pub(crate) struct TestDirectory(PathBuf);

        impl TestDirectory {
            pub(crate) fn new() -> Self {
                let path = std::env::temp_dir().join(temporary_name());
                fs::create_dir(&path).unwrap();
                Self(path)
            }

            pub(crate) fn path(&self) -> &Path {
                &self.0
            }

            pub(crate) fn assert_only(&self, path: &Path) {
                let entries: Vec<_> = fs::read_dir(self.path())
                    .unwrap()
                    .map(|entry| entry.unwrap().path())
                    .collect();
                assert_eq!(entries, vec![path.to_path_buf()]);
            }
        }

        impl Drop for TestDirectory {
            fn drop(&mut self) {
                fs::remove_dir_all(self.path()).unwrap();
            }
        }

        #[test]
        fn creates_and_overwrites_with_exact_readback_and_no_temp_files() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            replace(&path, b"{\"longer\":true}\n").unwrap();
            assert_eq!(fs::read(&path).unwrap(), b"{\"longer\":true}\n");
            replace(&path, b"{}").unwrap();
            assert_eq!(fs::read(&path).unwrap(), b"{}");
            root.assert_only(&path);
        }

        #[test]
        fn partial_write_failure_preserves_original_and_cleans_staging() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            fs::write(&path, b"original").unwrap();
            let result = replace_with(&path, b"replacement", |file, bytes| {
                file.write_all(&bytes[..3])?;
                assert_eq!(fs::read(&path)?, b"original");
                Err(io::Error::other("injected_disk_full"))
            });
            assert!(result.is_err());
            assert_eq!(fs::read(&path).unwrap(), b"original");
            root.assert_only(&path);
        }

        #[test]
        fn sync_failure_preserves_original_and_cleans_staging() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            fs::write(&path, b"original").unwrap();
            let result = replace_with(&path, b"replacement", |file, bytes| {
                file.write_all(bytes)?;
                Err(io::Error::other("injected_sync_failure"))
            });
            assert!(result.is_err());
            assert_eq!(fs::read(&path).unwrap(), b"original");
            root.assert_only(&path);
        }

        #[test]
        fn write_failure_does_not_publish_a_new_destination() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            assert!(replace_with(&path, b"replacement", |file, bytes| {
                file.write_all(&bytes[..3])?;
                Err(io::Error::other("injected_disk_full"))
            })
            .is_err());
            assert!(!path.exists());
            assert_eq!(fs::read_dir(root.path()).unwrap().count(), 0);
        }

        #[test]
        fn real_rename_failure_preserves_destination_and_cleans_staging() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            // A directory arriving after the preflight forces a real OS rename failure.
            let result = replace_with(&path, b"replacement", |file, bytes| {
                file.write_all(bytes)?;
                file.sync_all()?;
                fs::create_dir(&path)?;
                fs::write(path.join("keep"), b"original")
            });
            assert!(result.is_err());
            assert_eq!(fs::read(path.join("keep")).unwrap(), b"original");
            root.assert_only(&path);
        }

        #[test]
        fn target_directory_and_missing_parent_fail_without_damage() {
            let root = TestDirectory::new();
            let path = root.path().join("directory");
            fs::create_dir(&path).unwrap();
            fs::write(path.join("keep"), b"original").unwrap();
            assert!(replace(&path, b"replacement").is_err());
            assert!(replace(&root.path().join("missing/export.json"), b"{}").is_err());
            assert_eq!(fs::read(path.join("keep")).unwrap(), b"original");
            root.assert_only(&path);
        }

        #[test]
        fn temp_collision_never_truncates_or_deletes_someone_elses_file() {
            let root = TestDirectory::new();
            let path = root.path().join("occupied.tmp");
            fs::write(&path, b"keep").unwrap();
            assert!(StagedFile::create(root.path(), || "occupied.tmp".into()).is_err());
            assert_eq!(fs::read(&path).unwrap(), b"keep");
            root.assert_only(&path);
        }

        #[test]
        fn successful_publish_does_not_cleanup_a_reused_temporary_name() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            let mut staged = StagedFile::create(root.path(), temporary_name).unwrap();
            staged.file.as_mut().unwrap().write_all(b"{}").unwrap();
            staged.file.as_ref().unwrap().sync_all().unwrap();
            drop(staged.file.take());
            fs::rename(&staged.path, &path).unwrap();
            staged.published = true;
            let reused = staged.path.clone();
            fs::write(&reused, b"another operation").unwrap();
            drop(staged);
            assert_eq!(fs::read(&path).unwrap(), b"{}");
            assert_eq!(fs::read(&reused).unwrap(), b"another operation");
        }

        #[cfg(unix)]
        #[test]
        fn overwrite_keeps_the_previous_inode_intact() {
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            let previous = root.path().join("previous.json");
            fs::write(&path, b"original").unwrap();
            fs::hard_link(&path, &previous).unwrap();
            replace(&path, b"replacement").unwrap();
            assert_eq!(fs::read(&path).unwrap(), b"replacement");
            assert_eq!(fs::read(&previous).unwrap(), b"original");
        }

        #[cfg(unix)]
        #[test]
        fn real_directory_permission_failure_preserves_original() {
            use std::os::unix::fs::PermissionsExt;
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            fs::write(&path, b"original").unwrap();
            fs::set_permissions(root.path(), fs::Permissions::from_mode(0o500)).unwrap();
            let result = replace(&path, b"replacement");
            fs::set_permissions(root.path(), fs::Permissions::from_mode(0o700)).unwrap();
            // Deliberately require an unprivileged test user; root would bypass this check.
            assert_eq!(result.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
            assert_eq!(fs::read(&path).unwrap(), b"original");
            root.assert_only(&path);
        }

        #[cfg(unix)]
        #[test]
        fn cleanup_permission_failure_leaves_only_staging_and_preserves_original() {
            use std::os::unix::fs::PermissionsExt;
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            fs::write(&path, b"original").unwrap();
            let result = replace_with(&path, b"replacement", |file, bytes| {
                file.write_all(&bytes[..3])?;
                fs::set_permissions(root.path(), fs::Permissions::from_mode(0o500))?;
                Err(io::Error::other("injected_write_failure"))
            });
            fs::set_permissions(root.path(), fs::Permissions::from_mode(0o700)).unwrap();
            assert!(result.is_err());
            assert_eq!(fs::read(&path).unwrap(), b"original");
            let temporary: Vec<_> = fs::read_dir(root.path())
                .unwrap()
                .map(|entry| entry.unwrap().path())
                .filter(|entry| entry != &path)
                .collect();
            assert_eq!(temporary.len(), 1);
            assert!(temporary[0]
                .file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .starts_with(".vibe-export-"));
            assert_eq!(fs::read(&temporary[0]).unwrap(), b"rep");
        }

        #[cfg(unix)]
        #[test]
        fn selected_symlink_is_rejected_without_touching_its_target() {
            let root = TestDirectory::new();
            let target = root.path().join("keep.json");
            fs::write(&target, b"original").unwrap();
            let path = root.path().join("link.json");
            std::os::unix::fs::symlink(&target, &path).unwrap();
            assert!(replace(&path, b"replacement").is_err());
            assert!(fs::symlink_metadata(&path).unwrap().is_symlink());
            assert_eq!(fs::read(&target).unwrap(), b"original");
            assert_eq!(fs::read_dir(root.path()).unwrap().count(), 2);
        }

        #[cfg(unix)]
        #[test]
        fn staging_and_final_file_have_private_permissions() {
            use std::os::unix::fs::PermissionsExt;
            let root = TestDirectory::new();
            let path = root.path().join("export.json");
            replace_with(&path, b"{}", |file, bytes| {
                assert_eq!(file.metadata()?.permissions().mode() & 0o777, 0o600);
                file.write_all(bytes)?;
                file.sync_all()
            })
            .unwrap();
            assert_eq!(
                fs::metadata(path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
    }
}
