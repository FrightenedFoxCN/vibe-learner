import { createHash } from "node:crypto";

export const digest = (text) =>
  createHash("sha256").update(text.replaceAll("\r\n", "\n")).digest("hex");

export function issueKey(issue) {
  return JSON.stringify([issue.path, issue.rule, issue.message, issue.sourceDigest]);
}

export function lintRegressions(issues, baseline) {
  const remaining = new Map(baseline.map((issue) => [issueKey(issue), issue.count]));
  return issues.filter((issue) => {
    const key = issueKey(issue);
    const count = remaining.get(key) ?? 0;
    if (!count) return true;
    remaining.set(key, count - 1);
    return false;
  });
}

export function groupIssues(issues) {
  const grouped = new Map();
  for (const issue of issues) {
    const key = issueKey(issue);
    const { line: _line, column: _column, ...identity } = issue;
    const existing = grouped.get(key);
    if (existing) existing.count++;
    else grouped.set(key, { ...identity, count: 1 });
  }
  return [...grouped.values()].sort((a, b) => issueKey(a).localeCompare(issueKey(b)));
}

export function baselineExpansions(current, previous) {
  const old = new Map(previous.lint.map((issue) => [issueKey(issue), issue.count]));
  const expanded = current.lint
    .filter((issue) => issue.count > (old.get(issueKey(issue)) ?? 0))
    .map((issue) => `${issue.path}: ${issue.rule}`);
  for (const [path, hash] of Object.entries(current.format)) {
    if (previous.format[path] !== hash) expanded.push(`${path}: format`);
  }
  return expanded;
}
