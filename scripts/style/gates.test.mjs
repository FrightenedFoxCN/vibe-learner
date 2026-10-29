import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { ESLint } from "eslint";
import * as prettier from "prettier";
import {
  baselineExpansions,
  digest,
  groupIssues,
  lintRegressions,
} from "./baseline.mjs";
import { sourceKind } from "./scope.mjs";

const ruff = (args, input) =>
  spawnSync(
    "uv",
    ["run", "--project", "services/ai", "--frozen", "--no-sync", "ruff", ...args],
    {
      encoding: "utf8",
      input,
      env: {
        ...process.env,
        UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? "/tmp/vibe-learner-uv-cache",
      },
    },
  );

test("real ESLint rules reject unused imports, conditional Hooks and omitted dependencies", async () => {
  const eslint = new ESLint();
  const [result] = await eslint.lintText(
    `
    import { useEffect, useState } from "react";
    import { unused } from "./unused";
    export function Example({ enabled, value }) {
      if (enabled) useState(0);
      useEffect(() => { console.log(value); }, []);
      return null;
    }
  `,
    { filePath: "apps/web/components/style-gate-probe.tsx" },
  );
  const rules = new Set(result.messages.map((issue) => issue.ruleId));
  for (const rule of [
    "@typescript-eslint/no-unused-vars",
    "react-hooks/rules-of-hooks",
    "react-hooks/exhaustive-deps",
  ])
    assert.ok(rules.has(rule), rule);
  assert.equal(result.fatalErrorCount, 0);
});

test("real Ruff rules and both formatters detect bad code without rewriting it", async () => {
  const invalid = "import os\n\ndef example():\n    unused = 1\n";
  const checked = ruff(
    [
      "check",
      "--config",
      "services/ai/pyproject.toml",
      "--output-format",
      "json",
      "--stdin-filename",
      "services/ai/app/style_gate_probe.py",
      "-",
    ],
    invalid,
  );
  assert.equal(checked.status, 1, checked.stderr);
  assert.deepEqual(
    new Set(JSON.parse(checked.stdout).map((issue) => issue.code)),
    new Set(["F401", "F841"]),
  );
  const formatted = ruff(
    [
      "format",
      "--config",
      "services/ai/pyproject.toml",
      "--stdin-filename",
      "probe.py",
      "-",
    ],
    "print(  1 )\n",
  );
  assert.equal(formatted.status, 0, formatted.stderr);
  assert.equal(formatted.stdout, "print(1)\n");
  assert.equal(
    await prettier.check("const value= 1;", { filepath: "probe.ts" }),
    false,
  );
  assert.equal(
    await prettier.check("const value = 1;\n", { filepath: "probe.ts" }),
    true,
  );
});

test("baseline allows only the original finding and multiplicity, regardless of line shifts", () => {
  const issue = {
    path: "apps/web/example.ts",
    rule: "unused",
    message: "unused import",
    sourceDigest: digest("import unused"),
    line: 1,
    column: 1,
  };
  const baseline = groupIssues([issue]);
  assert.deepEqual(lintRegressions([{ ...issue, line: 42 }], baseline), []);
  assert.equal(lintRegressions([issue, issue], baseline).length, 1);
  for (const changed of [
    { ...issue, path: "apps/web/new.ts" },
    { ...issue, sourceDigest: digest("import another") },
    { ...issue, rule: "hooks" },
  ])
    assert.equal(lintRegressions([changed], baseline).length, 1);
  const previous = { lint: baseline, format: { "old.ts": digest("original") } };
  assert.deepEqual(baselineExpansions({ lint: [], format: {} }, previous), []);
  assert.equal(
    baselineExpansions(
      {
        lint: groupIssues([issue, issue]),
        format: { "old.ts": digest("changed"), "new.ts": digest("new") },
      },
      previous,
    ).length,
    3,
  );
});

test("scope includes product, shared, tooling and backend source but excludes generated output", () => {
  for (const path of [
    "apps/web/hooks/example.ts",
    "packages/shared/src/example.ts",
    "apps/desktop/scripts/build.mjs",
    "scripts/style/check.mjs",
  ])
    assert.equal(sourceKind(path), "javascript");
  assert.equal(sourceKind("services/ai/app/example.py"), "python");
  assert.equal(sourceKind("tools/model-quality/tests/example.py"), "python");
  for (const path of [
    "apps/web/next-env.d.ts",
    "apps/web/.next/types/route.ts",
    "services/ai/data/example.py",
    "apps/desktop/src-tauri/target/build.rs",
    "node_modules/package/index.js",
    "README.md",
  ])
    assert.equal(sourceKind(path), null);
});

test("the CLI rejects new lint and formatting defects, then accepts the corrected file", async () => {
  const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
  const directory = await mkdtemp("scripts/style/.gate-probe-");
  const path = `${directory}/probe with spaces.py`;
  const invoke = () =>
    spawnSync(process.execPath, ["scripts/style/check.mjs"], {
      encoding: "utf8",
      timeout: 30_000,
      env: {
        ...process.env,
        UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? "/tmp/vibe-learner-uv-cache",
      },
    });
  try {
    await writeFile(path, "import os\nprint(  1 )\n");
    const rejected = invoke();
    assert.equal(rejected.status, 1, rejected.stderr);
    assert.match(rejected.stderr, /F401/u);
    assert.ok(rejected.stderr.includes(`${path}: formatting differs`), rejected.stderr);
    await writeFile(path, "print(1)\n");
    const accepted = invoke();
    assert.equal(accepted.status, 0, accepted.stderr);
    assert.match(accepted.stdout, /0 regressions/u);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
