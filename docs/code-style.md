# Code style gates

Formatting and linting have separate commands. TypeScript checking remains `npm run check:web`.

| Command | Scope |
| --- | --- |
| `npm run style:check` | Lint all source against the explicit baseline; format-check added/modified files relative to `HEAD`, including staged and untracked source |
| `npm run style:check -- --base <commit>` | The same gate, with changed-file formatting relative to a branch/PR base |
| `npm run lint:web` | ESLint for JavaScript/TypeScript source in Web, shared contracts, desktop scripts and repository tooling |
| `npm run lint:ai` | Ruff for Python source in the AI service and model-quality tooling |
| `npm run format:check` | Formatting only for added/modified source; no files are rewritten |
| `npm run style:all` | Full lint plus formatting of every file whose bytes do not match a known legacy formatting exemption |
| `npm run test:style` | Real ESLint/Ruff smoke cases and baseline ratchet behavior; no app/provider/database |

Install tools with `npm ci` at the root and `cd services/ai && uv sync --frozen`. CI can install only the Python development group with `uv sync --project services/ai --frozen --only-group dev`. Tool versions are pinned in `package-lock.json` and `services/ai/uv.lock`; Ruff also checks its exact version. The JavaScript parser does not require a TypeScript program, so the lint gate is independent of a production build.

## Rules

- ESLint checks unused variables/imports, `react-hooks/rules-of-hooks` and `react-hooks/exhaustive-deps`. Unused callback arguments and caught exceptions are allowed; deliberately unused variables use an underscore prefix. Types are parsed by `@typescript-eslint/parser`.
- Ruff checks `F401` (unused imports) and `F841` (unused local variables).
- Prettier owns JS/TS formatting; Ruff owns Python formatting. Both use 88-column targets and LF endings. To format a touched file, use `npx prettier --write path/to/file.tsx` or `cd services/ai && uv run ruff format path/to/file.py`.
- Syntax errors and missing lint rule definitions fail the gate and cannot be grandfathered.

The source set comes from Git's tracked and nonignored untracked files, so paths containing spaces and staged changes work. Source under `apps/`, `packages/`, `services/ai/`, `tools/`, `scripts/` and root JS/TS/Python config files is included. Generated/build/dependency/data directories and `next-env.d.ts` are excluded. JSON fixtures, Markdown, Rust and shell files are outside this initial code-style gate. `packages/shared/src/tool-manifest.ts` is linted but not formatted by the gate because its Python-generated embedded golden is intentionally compact.

## Existing-code baseline

`scripts/style/baseline.json` records 234 initial lint findings and 769 unformatted files as of the adoption commit's parent. No mass source rewrite is part of adoption. Each lint exemption binds its path, rule, message, source-line digest and multiplicity. Moving an unchanged source line does not create debt, but a different variable, source line, path or extra occurrence cannot borrow its exemption. Format exemptions bind the exact normalized source digest.

Changed files must be formatted even when their old bytes have a formatting exemption. Unchanged legacy formatting is skipped by the full scan only when its digest matches. Existing lint findings remain visible in the report; they are not represented as a clean-code certification. This lets maintenance remove debt while preventing new findings in unrelated code from being silently added.

`npm run style:baseline` explicitly captures the complete current inventory without editing source. Use it only after reviewing fixes or a deliberate tool/rule migration. Normal checks compare the baseline with `--base` and reject added lint allowances or changed/new formatting exemptions; a normal baseline update can only shrink. CI supplies the PR base or push predecessor. Tool/rule migrations that need a new baseline require a separately reviewed change to this policy, not an automatic snapshot refresh in a feature PR.

## CI

`.github/workflows/style.yml` runs on PRs, pushes to `main` and manual dispatch. It installs locked development tools, runs the five gate smoke tests, and checks the baseline plus changed-file formatting using the authoritative base commit. For a manual/initial run it checks all nonexempt formatting. Release workflows also run `style:all`; `npm run check` includes `style:check` before the existing reliability gates.

Local verification for this change runs only the style gate's own checks and the affected TypeScript boundary. Full backend tests and production builds remain separate commands.
