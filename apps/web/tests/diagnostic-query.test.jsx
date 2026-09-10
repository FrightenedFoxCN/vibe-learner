import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decodeDiagnosticWriters, decodeDiagnosticEvents, decodeDiagnosticIndex, decodeDiagnosticLinks, queryDiagnosticEvents, DiagnosticQueryError } from "../lib/diagnostic-query.ts";
import { diagnosticSnapshot } from "../lib/diagnostics.ts";
const fixture = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/query-pages-v1.json", import.meta.url), "utf8"));
const copy = name => structuredClone(fixture[name]);
const operation = fixture.links.items[0].operation_id;

test("Python-produced event/index/link pages pass strict browser decoding", () => {
  assert.deepEqual(decodeDiagnosticEvents(copy("events")), fixture.events);
  assert.deepEqual(decodeDiagnosticIndex(copy("index")), fixture.index);
  assert.deepEqual(decodeDiagnosticLinks(copy("links"), operation), fixture.links);
});

test("nested content, classification drift and incoherent pagination fail closed", () => {
  for (const mutate of [
    page => { page.PRIVATE = "secret"; },
    page => { page.items[0].event.prompt = "PRIVATE"; },
    page => { page.items[0].event.outcome = "failed"; },
    page => { page.items[0].event.provider_metric = { secret: "PRIVATE" }; },
    page => { page.items[0].event.desktop_metric = { instance_id: "desktop-abc", exit_code: 0, dropped_before: -1, write_failures_before: 0 }; },
    page => { page.items.push({ ...page.items[0], sequence: 2 }); page.next_cursor = 2; },
    page => { page.next_cursor = 2; },
    page => { page.health.queued = NaN; },
    page => { page.items[0].sequence = 0; },
  ]) {
    const page = copy("events"); mutate(page);
    assert.throws(() => decodeDiagnosticEvents(page), error => error instanceof DiagnosticQueryError && !error.message.includes("PRIVATE"));
  }
  const index = copy("index"); index.items[0].attempts = [{ attempt_id: "a", attempt_index: 0, phase: "invented", status: "passed", duration_ms: 0 }];
  assert.throws(() => decodeDiagnosticIndex(index), DiagnosticQueryError);
  const links = copy("links"); links.items[0].operation_id = "harness-operation-" + "b".repeat(32);
  assert.throws(() => decodeDiagnosticLinks(links, operation), DiagnosticQueryError);
});

test("empty results retain cursors and distinguish unavailable index/link responses", () => {
  const events = copy("events"); events.items = []; events.next_cursor = 23;
  assert.equal(decodeDiagnosticEvents(events, 23).next_cursor, 23);
  events.has_more = true;
  assert.throws(() => decodeDiagnosticEvents(events, 23), DiagnosticQueryError);
  assert.equal(decodeDiagnosticIndex({ items: [], next_cursor: "last", has_more: false, coverage: { failures: 1, freshness: "unavailable", canonical_read_back_required: true } }, "last").coverage.freshness, "unavailable");
  assert.equal(decodeDiagnosticLinks({ items: [], next_cursor: "", gap: "diagnostic_store_unavailable" }, operation).gap, "diagnostic_store_unavailable");
});

test("queries stay nonrecursive, encode filters and cancel oversized responses", async () => {
  const original = globalThis.fetch;
  const before = diagnosticSnapshot();
  const controller = new AbortController();
  try {
    globalThis.fetch = async (url, init) => {
      const parsed = new URL(url);
      assert.equal(parsed.searchParams.get("page_path"), "/plan");
      assert.equal(parsed.searchParams.get("since"), "2026-09-10T08:00:00+08:00");
      assert.equal(init.signal.aborted, controller.signal.aborted);
      return Response.json(copy("events"));
    };
    await queryDiagnosticEvents({ page_path: "/plan", since: "2026-09-10T08:00:00+08:00" }, 0, controller.signal);
    assert.deepEqual(diagnosticSnapshot(), before);
    globalThis.fetch = async () => new Response("PRIVATE_SERVER_ERROR", { status: 503 });
    await assert.rejects(queryDiagnosticEvents(), error => error.code === "unavailable" && !error.message.includes("PRIVATE"));
    globalThis.fetch = async () => { throw new Error("PRIVATE_NETWORK_ERROR"); };
    await assert.rejects(queryDiagnosticEvents(), error => error.code === "unavailable" && !error.message.includes("PRIVATE"));
    let cancelled = false;
    globalThis.fetch = async () => new Response(new ReadableStream({ start(c) { c.enqueue(new Uint8Array(2 * 1024 * 1024 + 1)); }, cancel() { cancelled = true; } }));
    await assert.rejects(queryDiagnosticEvents(), error => error.code === "response_too_large");
    assert.equal(cancelled, true);
  } finally { globalThis.fetch = original; }
});

test("actual Python provider/tool/attempt/desktop DTOs retain reviewed nested metrics", () => {
  for (const event of fixture.metrics) {
    const page = copy("events"); page.items[0].event = event;
    assert.deepEqual(decodeDiagnosticEvents(page).items[0].event, event);
  }
});


test("caller abort cancels the combined timeout signal and remains distinguishable", async () => {
  const original = globalThis.fetch;
  const controller = new AbortController();
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    controller.abort();
  });
  try { await assert.rejects(queryDiagnosticEvents({}, 0, controller.signal), error => error.name === "AbortError"); }
  finally { globalThis.fetch = original; }
});

test("retention coverage cannot falsify gaps or report fewer rows than its page", () => {
  for (const mutate of [
    page => { page.retention.removed_through_sequence = 2; },
    page => { page.retention.retained_events = 0; },
    page => { page.retention.disk_size_limit_certified = true; },
    page => { page.retention.retained_payload_bytes = -1; },
  ]) {
    const page = copy("events"); mutate(page);
    assert.throws(() => decodeDiagnosticEvents(page), DiagnosticQueryError);
  }
});


test("writer coverage keeps lower-bound and unclosed semantics strict", () => {
  assert.deepEqual(decodeDiagnosticWriters(copy("writers")), fixture.writers);
  for (const mutate of [
    page => { page.complete_collection_claim = true; },
    page => { page.unpersisted_queue_gap = false; },
    page => { page.totals.unclosed_epochs = page.totals.retained_epochs + 1; },
    page => { page.items[0].epoch_id = "PRIVATE_SECRET"; },
    page => { page.next_cursor += 1; },
  ]) {
    const page = copy("writers"); mutate(page);
    assert.throws(() => decodeDiagnosticWriters(page), DiagnosticQueryError);
  }
});

test("export decodes Python snapshot and rejects nested secrets, drift and incomplete coverage", async () => {
  const { decodeDiagnosticExport } = await import("../lib/diagnostic-export.ts");
  const sample = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/export-sample-v1.json", import.meta.url), "utf8"));
  assert.deepEqual(decodeDiagnosticExport(sample, {}), sample);
  for (const mutate of [
    x => { x.audit.observations[0].prompt = "PRIVATE"; },
    x => { x.events[0].event.outcome = "failed"; },
    x => { x.events[1].sequence = x.events[0].sequence; },
    x => { x.audit.input_event_count++; },
    x => { x.audit.groups[0].sample_count++; },
    x => { x.writer_pages[0].has_more = true; },
    x => { x.index.push(x.index[0]); },
    x => { x.created_at = "2026-09-10"; },
    x => { delete x.audit.groups[0].key.model; },
    x => { x.filters.source = "browser"; },
    x => { x.link_retention.retained_rows = 0; },
    x => { x.index_retention = null; },
    x => { x.link_retention.table = "projections"; },
    x => { x.index_retention.private = "PRIVATE"; },
  ]) {
    const value = structuredClone(sample); mutate(value);
    assert.throws(() => decodeDiagnosticExport(value, {}), DiagnosticQueryError);
  }
});

test("export POST uses bounded nonrecursive transport and caller abort", async () => {
  const { queryDiagnosticExport } = await import("../lib/diagnostic-export.ts");
  const sample = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/export-sample-v1.json", import.meta.url), "utf8"));
  const previous = globalThis.fetch;
  const before = diagnosticSnapshot();
  try {
    globalThis.fetch = async (url, init) => {
      assert.ok(url.includes("/diagnostics/export")); assert.equal(init.method, "POST"); assert.equal(init.body, "{}");
      return Response.json(sample);
    };
    assert.deepEqual(await queryDiagnosticExport({}), sample);
    assert.deepEqual(diagnosticSnapshot(), before);
    globalThis.fetch = async () => new Response("PRIVATE", { status: 413 });
    await assert.rejects(queryDiagnosticExport({}), error => error.code === "response_too_large" && !error.message.includes("PRIVATE"));
    const controller = new AbortController(); controller.abort();
    globalThis.fetch = async () => Response.json(sample);
    await assert.rejects(queryDiagnosticExport({}, controller.signal));
    let cancelled = false;
    globalThis.fetch = async () => new Response(new ReadableStream({ start(c) { c.enqueue(new Uint8Array(32 * 1024 * 1024 + 1)); }, cancel() { cancelled = true; } }));
    await assert.rejects(queryDiagnosticExport({}), error => error.code === "response_too_large");
    assert.equal(cancelled, true);
  } finally { globalThis.fetch = previous; }
});

test("storage observations retain gaps and reject fake totals or admission claims", async () => {
  const { decodeDiagnosticStorage, queryDiagnosticStorage } = await import("../lib/diagnostic-storage.ts");
  const sample = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/storage-sample-v1.json", import.meta.url), "utf8"));
  assert.deepEqual(decodeDiagnosticStorage(sample), sample);
  const directoryObserved = structuredClone(sample);
  Object.assign(directoryObserved.directory, { status: "observed", gaps: [], budget_state: "within_observed_limit", database_bytes: 10, database_files: 1, other_bytes: 3, other_files: 1, total_bytes: 13, scanned_entries: 2, visited_directories: 1 });
  assert.deepEqual(decodeDiagnosticStorage(directoryObserved), directoryObserved);
  const directoryPartial = structuredClone(directoryObserved);
  Object.assign(directoryPartial.directory, { status: "incomplete", gaps: ["depth_limit"], budget_state: "unknown" });
  assert.deepEqual(decodeDiagnosticStorage(directoryPartial), directoryPartial);
  Object.assign(directoryPartial.directory, { other_bytes: 210000000, total_bytes: 210000010, budget_state: "over_observed_limit" });
  assert.deepEqual(decodeDiagnosticStorage(directoryPartial), directoryPartial);
  const observed = structuredClone(sample);
  Object.assign(observed.desktop_spool, { status: "observed", gap: null, event_files: 2, event_bytes: 9, metadata_bytes: 2, other_files: 1, other_bytes: 3, total_bytes: 14 });
  assert.deepEqual(decodeDiagnosticStorage(observed), observed);
  const partial = structuredClone(observed);
  Object.assign(partial.desktop_spool, { status: "incomplete", gap: "unsupported_entry", skipped_entries: 1 });
  assert.deepEqual(decodeDiagnosticStorage(partial), partial);
  for (const mutate of [
    x => { x.admission_guarantee = true; },
    x => { x.databases[0].files.total_bytes++; },
    x => { x.databases[0].name = "index"; },
    x => { x.databases[0].status = "over_observed_limit"; },
    x => { x.databases[0].recovery = null; },
    x => { x.databases[0].recovery.temporary_overage_possible = false; },
    x => { x.databases[0].counters.path = "PRIVATE"; },
    x => { x.directory.total_bytes++; },
    x => { x.directory.budget_state = "within_observed_limit"; },
    x => { x.directory.gaps.push(x.directory.gaps[0]); },
    x => { x.directory.path = "PRIVATE"; },
    x => { x.directory.database_files = 1; },
    x => { x.desktop_spool.total_bytes++; },
    x => { x.desktop_spool.status = "observed"; },
    x => { x.desktop_spool.path = "PRIVATE"; },
    x => { x.desktop_spool.event_files = 1025; },
    x => { x.unmeasured[1] = x.unmeasured[0]; },
  ]) { const value = structuredClone(sample); mutate(value); assert.throws(() => decodeDiagnosticStorage(value), DiagnosticQueryError); }
  const before = globalThis.fetch;
  try {
    globalThis.fetch = async url => { assert.ok(url.includes("/diagnostics/storage")); return Response.json(sample); };
    assert.deepEqual(await queryDiagnosticStorage(), sample);
  } finally { globalThis.fetch = before; }
});


test("canonical resource roles retain nullable revisions and reject unreviewed fields", () => {
  const page = copy("index");
  page.items[0].resources_gap = null;
  page.items[0].resources = {
    context_subjects: [{ resource_type: "document", resource_id: "doc", revision: null }],
    attempted_outputs: [{ resource_type: "learning_plan", resource_id: "plan", revision: null }],
    committed_outputs: [{ resource_type: "learning_plan", resource_id: "plan", expected_revision: null, committed_revision: null, first_sequence: null, last_sequence: null }],
    scope: "historical_canonical_projection_requires_read_back",
  };
  assert.deepEqual(decodeDiagnosticIndex(page), page);
  for (const mutate of [
    resource => { resource.committed_outputs[0].payload_digest = "a".repeat(64); },
    resource => { resource.context_subjects[0].revision = -1; },
    resource => { resource.attempted_outputs[0].resource_type = "invented"; },
    resource => { resource.context_subjects = Array(65).fill(resource.context_subjects[0]); },
  ]) {
    const invalid = structuredClone(page); mutate(invalid.items[0].resources);
    assert.throws(() => decodeDiagnosticIndex(invalid), DiagnosticQueryError);
  }
});


test("saved-resource events reject invented revisions and unscoped message sequences", () => {
  const page = copy("events");
  Object.assign(page.items[0].event, { name: "resource_reference", category: "resource", severity: "info", outcome: "observed", error_code: null,
    resource: { resource_type: "tavern_message", resource_id: "message", revision: null, sequence: 12, parent_resource_id: "room" } });
  assert.deepEqual(decodeDiagnosticEvents(page), page);
  for (const patch of [{ revision: 0 }, { sequence: null }, { parent_resource_id: null }, { resource_type: "document" }]) {
    const bad = structuredClone(page); Object.assign(bad.items[0].event.resource, patch);
    assert.throws(() => decodeDiagnosticEvents(bad), DiagnosticQueryError);
  }
});
