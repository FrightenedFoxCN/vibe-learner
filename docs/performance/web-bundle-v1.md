# Web production bundle budget v1

This gate measures the compressed first response plus the first party JavaScript
and CSS assets referenced by the production HTML for `/`, `/settings`,
`/model-usage` and `/tavern`. It uses a production Next build and an isolated
loopback `next start` process. The route total is the sum of the raw gzip bytes
returned for those requests; it is a transfer-size baseline, not a browser cache
or full interaction performance measurement.

Run from the repository root after `npm run build:web`:

```bash
npm --workspace @vibe-learner/web run start -- --hostname 127.0.0.1 --port 3417
npm run bench:web-bundle -- \
  --base-url http://127.0.0.1:3417 \
  --baseline docs/performance/web-bundle-v1.json
```

The command writes a machine-readable report with `--output <path>`. It fails
when any measured route exceeds its baseline by more than 5%. The baseline is
route-specific and includes the HTML, JS and CSS asset paths, so an asset shared
by several routes is counted once in each route's first-load total. The command
does not follow external assets or contact the backend/provider.

## Reference baseline

Measured from the `0.3.7` production build (`BUILD_ID=s5WP-VCwvu1dXgApeV90E`) on
macOS arm64 with Node 26.13.0. All four responses returned `Content-Encoding:
gzip` and HTTP 200.

| Route          | HTML gzip bytes | JS/CSS gzip bytes | First-load total | 5% ceiling |
| -------------- | --------------: | ----------------: | ---------------: | ---------: |
| `/`            |           6,707 |           306,313 |          313,020 |    328,672 |
| `/settings`    |           2,348 |           316,669 |          319,017 |    334,968 |
| `/model-usage` |           4,562 |           310,831 |          315,393 |    331,163 |
| `/tavern`      |           5,242 |           448,809 |          454,051 |    476,754 |

The raw asset list is [web-bundle-v1.json](web-bundle-v1.json). This gate does
not certify runtime API latency, browser rendering, cache hit behavior, or the
desktop WebView bundle.
