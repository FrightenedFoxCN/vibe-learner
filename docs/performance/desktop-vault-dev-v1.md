# Desktop Vault development-build latency

Stronghold snapshot encryption uses scrypt with work factor 19. Unoptimized
development dependencies can make unlock/save/load expensive. Package-specific
`profile.dev` optimization for `scrypt`, `salsa20` and `argon2` retains application
debug information and the existing cryptographic parameters and snapshot format.
The application must be rebuilt and restarted after changing this profile.

Local macOS single observations provide an indicative before/after comparison,
not cross-platform percentiles or release gates:

| Operation | Unoptimized dependencies ms | Optimized dependencies ms |
| --- | ---: | ---: |
| Existing-Vault unlock | 45953 | 972 |
| Secret read-back | 2 | 1 |
| Synthetic Stronghold save | 51540 | 1011 |
| Synthetic Stronghold load | 49661 | 934 |
| Synthetic Argon2 derivation | 1443 | 122 |

Reproduce with a synthetic password and temporary snapshot:

```bash
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib vault_performance_probe -- --ignored --nocapture --test-threads=1
```

The opt-in probe removes its temporary snapshot after read-back and does not
access user Vault contents. Native unlock timing includes plugin, Stronghold
and client loading; browser/server secret synchronization is a separate operation.
