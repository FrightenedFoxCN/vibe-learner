# Desktop Vault development-build latency

Measured on the local macOS development machine on 2026-09-10. These are
single before/after observations, not cross-platform percentiles or release gates.

| Operation | Unoptimized dependencies (ms) | Optimized dependencies (ms) |
| --- | ---: | ---: |
| Native existing-Vault unlock action | 45953 | 972 |
| Native secret read-back | 2 | 1 |
| Synthetic Stronghold snapshot save | 51540 | 1011 |
| Synthetic Stronghold snapshot load | 49661 | 934 |
| Synthetic Argon2 key derivation | 1443 | 122 |

The isolated native application used the source sidecar and production Web server
on port 3000. Before the change, session-secret synchronization took 6 ms in the
browser and 1.644 ms on the server. The unlock action wraps plugin loading,
Stronghold loading and client loading; synchronization follows it. The synthetic
probe reproduces the slow operation without any application database or collector.

Stronghold snapshot encryption uses scrypt with work factor 19. Unoptimized
development dependencies made this computation take approximately 50 seconds.
Package-specific `profile.dev` optimization for `scrypt`, `salsa20` and `argon2`
reduces the observed cost while retaining application debug information.
Cryptographic parameters, passwords, snapshot formats and release settings are
unchanged. Existing native Vault unlock succeeded after rebuilding, with no
migration or re-creation. A running application must be rebuilt and restarted to
receive this change.

Native diagnostic event evidence:

- Before: `8f3c4358-c10c-459a-a375-ac977c7b1014`, completed at
  `2026-09-10T12:24:30.997Z`, duration 45953 ms.
- After: `cb6e4640-83ab-4b4a-af1b-c5d0c9963fb4`, completed at
  `2026-09-10T12:34:27.246Z`, duration 972 ms.
- After read-back: `a15d1796-9dbf-4af4-91b8-a7a9a311f1d8`, duration 1 ms.

Reproduce the opt-in synthetic save/load and derivation probes:

```sh
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib vault_performance_probe -- --ignored --nocapture --test-threads=1
```

The probes use an unrelated synthetic password and a temporary snapshot, remove
the snapshot after successful read-back, and never access user Vault contents.
Both probes passed after optimization. All 11 ordinary native library tests passed
(the two expensive probes remain opt-in), and the native development build passed.
Local logs: `/tmp/diagnostic-stronghold-debug.log`,
`/tmp/diagnostic-argon-debug.log`, `/tmp/diagnostic-stronghold-optimized.log`,
`/tmp/diagnostic-vault-native-tests.log`, `/tmp/diagnostic-vault-native-build.log`.
