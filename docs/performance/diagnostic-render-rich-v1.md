# Wide nested diagnostic-event rendering

The existing production-React Chromium probe now accepts `--rich`. It uses a
Python-validated synthetic event with provider, tool, Harness, resource and desktop
nested sections populated. A pattern-valid synthetic tool label is filled to the
frontend decoder's 4096-character fallback ceiling. This label is stress data,
not a registered Tool Manifest entry or production adoption evidence. No private
content or provider credentials are used. Each row has its own deep-cloned nested
objects, preventing fill operations from multiplying a shared label.

The response remains below the 2 MiB query transport limit. The final largest page
is 725,309 UTF-8 bytes for 100 events. Because the strict decoder bounds individual
strings, this population does not claim to attain 2 MiB or exhaust every possible
schema combination. It fills all five nested event sections and one maximum
fallback-length label. Python validates the base fixture; the actual frontend
strict decoder validates every expanded response during the browser run.

Three warmups precede 30 samples. Each mounts 100 rows, appends through the 500-row
UI cap, expands the first event and unmounts. All population counts, cap behavior
and browser error checks remain active. Each measurement includes layout and two
animation boundaries, not proof of GPU completion. The production React bundle
and real query decoder are used with local synthetic fetch responses. Next shell,
backend/network, native WebView and separate index/association views are excluded.

| Phase | P50 ms | P95 ms | Max ms | Budget ms |
| --- | ---: | ---: | ---: | ---: |
| Mount 100 rows | 50.0 | 50.5 | 50.7 | 150 |
| Append through 500 rows (last page) | 50.0 | 50.7 | 50.9 | 150 |
| Expand nested event | 30.2 | 30.9 | 31.0 | 100 |
| Unmount 500 rows | 33.3 | 34.0 | 34.1 | 100 |

All gates passed unchanged. Initial fixture construction attempts hit strict enum
validation, and the first browser iterations rejected overlong labels (including
an accidental shared nested-object append). Those probe errors were corrected
before the complete sample set; no application decoder limit was relaxed.

```sh
node apps/web/tests/diagnostic-render-benchmark.mjs /tmp/diagnostic-render-rich.json --rich
```

[Raw report](diagnostic-render-rich-v1.json) includes all observations, bundle
hash/inputs, response bytes and environment. Log: `/tmp/diagnostic-render-rich.log`.
The original small-event profile is also rerun as compatibility verification;
its prior archived performance evidence remains unchanged. Native saturated-spool
and remaining native acceptance are separate, still-open requirements.
