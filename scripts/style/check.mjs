import { ESLint } from "eslint";
import * as prettier from "prettier";
import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  baselineExpansions,
  digest,
  groupIssues,
  lintRegressions,
} from "./baseline.mjs";
import { sourceKind } from "./scope.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const baselinePath = "scripts/style/baseline.json";
// The embedded, Python-generated Tool Manifest golden is intentionally compact.
const formatIgnored = new Set(["packages/shared/src/tool-manifest.ts"]);

function run(command, args, allowed = [0], input) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    input,
    env: {
      ...process.env,
      UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? "/tmp/vibe-learner-uv-cache",
    },
  });
  if (result.error || !allowed.includes(result.status)) {
    throw new Error(
      `${command} failed: ${result.error?.message ?? result.stderr ?? result.status}`,
    );
  }
  return result.stdout;
}
const git = (...args) => run("git", args);
const filesFrom = (output) => output.split("\0").filter(Boolean);
const normalize = (path) => relative(root, resolve(root, path)).replaceAll("\\", "/");

function options(args) {
  let base = "HEAD",
    all = false,
    writeBaseline = false,
    kind,
    lintOnly = false,
    formatOnly = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--base") base = args[++i];
    else if (arg === "--all") all = true;
    else if (arg === "--write-baseline") writeBaseline = true;
    else if (arg === "--kind") kind = args[++i];
    else if (arg === "--lint-only") lintOnly = true;
    else if (arg === "--format-only") formatOnly = true;
    else throw new Error(`unknown option: ${arg}`);
  }
  if (!base || (kind && !["javascript", "python"].includes(kind)))
    throw new Error("invalid style options");
  if (writeBaseline && kind)
    throw new Error("capture the complete baseline without --kind");
  if ((lintOnly && formatOnly) || (writeBaseline && (lintOnly || formatOnly)))
    throw new Error("incompatible style modes");
  return { base, all, writeBaseline, kind, lintOnly, formatOnly };
}

async function lint(files) {
  const issues = [];
  const sources = new Map(
    await Promise.all(
      files.map(async (path) => [
        path,
        (await readFile(resolve(root, path), "utf8")).split(/\r?\n/u),
      ]),
    ),
  );
  const add = (path, rule, message, line, column, fatal = false) => {
    if (fatal || !rule || message.startsWith("Definition for rule"))
      throw new Error(`syntax/configuration error: ${path}:${line}: ${message}`);
    issues.push({
      path,
      rule,
      message,
      sourceDigest: digest(sources.get(path)[line - 1]?.trim() ?? ""),
      line,
      column,
    });
  };
  const js = files.filter((path) => sourceKind(path) === "javascript");
  if (js.length) {
    const eslint = new ESLint({ cwd: root });
    for (const result of await eslint.lintFiles(js)) {
      for (const issue of result.messages)
        add(
          normalize(result.filePath),
          issue.ruleId ??
            (issue.message.startsWith("Unused eslint-disable")
              ? "eslint/unused-disable"
              : null),
          issue.message,
          issue.line,
          issue.column,
          issue.fatal,
        );
    }
  }
  const python = files.filter((path) => sourceKind(path) === "python");
  if (python.length) {
    const raw = run(
      "uv",
      [
        "run",
        "--project",
        "services/ai",
        "--frozen",
        "--no-sync",
        "ruff",
        "check",
        "--config",
        "services/ai/pyproject.toml",
        "--output-format",
        "json",
        ...python,
      ],
      [0, 1],
    );
    for (const issue of JSON.parse(raw))
      add(
        normalize(issue.filename),
        issue.code,
        issue.message,
        issue.location.row,
        issue.location.column,
      );
  }
  return issues;
}

async function formatted(path) {
  const text = await readFile(resolve(root, path), "utf8");
  if (sourceKind(path) === "python") {
    const expected = run(
      "uv",
      [
        "run",
        "--project",
        "services/ai",
        "--frozen",
        "--no-sync",
        "ruff",
        "format",
        "--config",
        "services/ai/pyproject.toml",
        "--no-cache",
        "--stdin-filename",
        path,
        "-",
      ],
      [0],
      text,
    );
    // Ruff's stdin formatting receives the file contents without a shell.
    return expected === text;
  }
  return prettier.check(text, {
    ...(await prettier.resolveConfig(resolve(root, path))),
    filepath: resolve(root, path),
  });
}

async function main() {
  const opts = options(process.argv.slice(2));
  git("rev-parse", "--verify", `${opts.base}^{commit}`);
  const paths = [
    ...new Set(
      filesFrom(git("ls-files", "--cached", "--others", "--exclude-standard", "-z")),
    ),
  ].sort();
  const files = [];
  for (const path of paths) {
    if (!sourceKind(path) || (opts.kind && sourceKind(path) !== opts.kind)) continue;
    try {
      await readFile(resolve(root, path));
      files.push(path);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  const changes = new Set([
    ...filesFrom(
      git("diff", "--name-only", "--diff-filter=ACMRT", "-z", opts.base, "--"),
    ),
    ...filesFrom(git("ls-files", "--others", "--exclude-standard", "-z")),
  ]);
  const issues = opts.formatOnly ? [] : await lint(files);
  if (opts.writeBaseline) {
    const format = {};
    for (const path of files) {
      if (!formatIgnored.has(path) && !(await formatted(path)))
        format[path] = digest(await readFile(resolve(root, path), "utf8"));
    }
    await writeFile(
      resolve(root, baselinePath),
      JSON.stringify(
        {
          schemaVersion: "style-baseline-v1",
          capturedCommit: git("rev-parse", "HEAD").trim(),
          lint: groupIssues(issues),
          format,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      `Captured ${issues.length} lint findings and ${Object.keys(format).length} formatting files; no source files changed.`,
    );
    return;
  }
  const baseline = JSON.parse(await readFile(resolve(root, baselinePath), "utf8"));
  if (baseline.schemaVersion !== "style-baseline-v1")
    throw new Error("unsupported style baseline");
  const previous = spawnSync("git", ["show", `${opts.base}:${baselinePath}`], {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  if (previous.status === 0) {
    const expanded = baselineExpansions(baseline, JSON.parse(previous.stdout));
    if (expanded.length)
      throw new Error(`baseline may only shrink:\n${expanded.join("\n")}`);
  }
  const regressions = lintRegressions(issues, baseline.lint);
  for (const issue of regressions)
    console.error(
      `${issue.path}:${issue.line}:${issue.column} ${issue.rule}: ${issue.message}`,
    );
  let formatFailures = 0,
    checked = 0;
  for (const path of files) {
    if (opts.lintOnly || formatIgnored.has(path) || (!opts.all && !changes.has(path)))
      continue;
    const text = await readFile(resolve(root, path), "utf8");
    if (opts.all && !changes.has(path) && baseline.format[path] === digest(text))
      continue;
    checked++;
    if (!(await formatted(path))) {
      formatFailures++;
      console.error(
        `${path}: formatting differs; run Prettier or Ruff format on this file`,
      );
    }
  }
  console.log(
    `Style: ${files.length} linted files, ${issues.length - regressions.length} baseline findings, ${checked} format checks, ${regressions.length + formatFailures} regressions.`,
  );
  if (regressions.length || formatFailures) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
