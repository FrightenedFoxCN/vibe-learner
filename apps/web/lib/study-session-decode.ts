import type {
  ChatToolCallTrace,
  Citation,
  DialogueTurnRecord,
  LearningPlan,
  ModelRecovery,
  ProjectedPdfOverlay,
  SceneObjectSnapshot,
  SceneProfile,
  SceneTreeNode,
  SessionAffinityState,
  SessionFollowUp,
  SessionMemoryEntry,
  SessionPlanConfirmation,
  SessionProjectedPdf,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";

import { compactPreviewString } from "./preview.ts";
import { StrictResponseDecoder } from "./strict-response-decode.ts";

const SESSION_STATUSES = ["active"] as const;
const LEARNER_MESSAGE_KINDS = [
  "learner", "session_prelude", "scheduled_follow_up", "interactive_callback",
] as const;
const FOLLOW_UP_STATUSES = ["pending", "completed", "canceled"] as const;
const PLAN_CONFIRMATION_STATUSES = ["pending", "approved", "rejected"] as const;
const AFFINITY_LEVELS = [
  "neutral", "warm", "trusted", "guarded", "strained", "cold", "hostile",
] as const;
const CITATION_SOURCE_KINDS = [
  "document", "attachment_pdf", "attachment_image", "generated_image",
] as const;
const ATTACHMENT_KINDS = ["image", "pdf", "text"] as const;
const CHARACTER_TIMING_HINTS = ["instant", "linger", "after_text"] as const;
const MEMORY_TRACE_SOURCES = ["retriever", "tool_call"] as const;
const QUESTION_TYPES = ["multiple_choice", "fill_blank"] as const;
const QUESTION_DIFFICULTIES = ["easy", "medium", "hard"] as const;
const PROJECTED_SOURCE_KINDS = [
  "document", "attachment_pdf", "attachment_image", "generated_image",
] as const;
const PROJECTED_OVERLAY_KINDS = ["text_highlight", "region_box"] as const;
const CHAT_TOOL_NAMES = [
  "ask_multiple_choice_question", "ask_fill_blank_question", "retrieve_memory_context",
  "read_session_memory", "write_session_memory", "read_system_time",
  "schedule_session_follow_up", "read_affinity_state", "update_affinity_state",
  "read_learning_plan_progress", "update_learning_plan", "update_learning_plan_progress",
  "read_page_range_content", "read_page_range_images", "project_uploaded_pdf",
  "project_uploaded_image", "generate_projected_image", "read_projected_pdf_content",
  "read_projected_pdf_images", "focus_projected_pdf_page", "highlight_projected_pdf_text",
  "annotate_projected_pdf_region", "clear_projected_pdf_overlays",
  "annotate_projected_image_region", "clear_projected_image_overlays",
  "read_scene_overview", "add_scene", "move_to_scene", "add_object",
  "update_object_description", "delete_object",
] as const;

const SCENE_MAX_DEPTH = 8;
const SCENE_MAX_LAYER_COUNT = 64;
const SCENE_MAX_OBJECT_COUNT = 128;
const SCENE_MAX_TEXT_BUDGET = 60_000;

export class StudySessionDecodeError extends Error {
  readonly code = "study_session_response_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "StudySessionDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  throw new StudySessionDecodeError(path, reason);
});

export function isStudySessionDecodeError(error: unknown): error is StudySessionDecodeError {
  return error instanceof StudySessionDecodeError || (
    typeof error === "object" && error !== null && "code" in error &&
    error.code === "study_session_response_decode_error"
  );
}

export type StudySessionDecodeNoticeContext = "history" | "response" | "update";

const STUDY_SESSION_DECODE_NOTICES: Record<StudySessionDecodeNoticeContext, string> = {
  history: "历史学习会话格式异常，已停止载入以保护记录。请刷新；若仍出现，请查看调试信息。",
  response: "回复校验失败，已停止更新页面以保护会话记录。请先刷新恢复最新会话，不要重复发送本次消息；详细原因已记录到调试信息。",
  update: "会话更新结果校验失败，已停止更新页面以保护记录。请先刷新确认最新状态，不要重复操作；详细原因已记录到调试信息。",
};

export function resolveStudySessionErrorNotice(
  error: unknown,
  fallback: string,
  context: StudySessionDecodeNoticeContext,
): string {
  return isStudySessionDecodeError(error) ? STUDY_SESSION_DECODE_NOTICES[context] : fallback;
}

export interface StudyChatFailurePresentation {
  detail: string;
  retryAllowed: boolean;
}

export function resolveStudyChatFailurePresentation(error: unknown): StudyChatFailurePresentation | null {
  if (isStudySessionDecodeError(error)) return null;
  return { detail: String(error), retryAllowed: true };
}

function textValue(
  raw: unknown,
  path: string,
  options: { allowEmpty?: boolean; maximum?: number } = {},
): string {
  const allowEmpty = options.allowEmpty ?? false;
  const value = decoder.string(raw, path, allowEmpty);
  if (!allowEmpty && !value.trim()) {
    throw new StudySessionDecodeError(path, "expected_non_empty_string");
  }
  const maximum = options.maximum ?? Number.MAX_SAFE_INTEGER;
  if (value.length > maximum) {
    throw new StudySessionDecodeError(path, `string_length_exceeds_${maximum}`);
  }
  return value;
}

function identity(raw: unknown, path: string, maximum = 160): string {
  const value = textValue(raw, path, { maximum });
  if (value !== value.trim()) {
    throw new StudySessionDecodeError(path, "identity_must_be_trimmed");
  }
  return value;
}

function timestamp(raw: unknown, path: string): string {
  const value = textValue(raw, path, { maximum: 64 });
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match || !Number.isFinite(Date.parse(value))) {
    throw new StudySessionDecodeError(path, "expected_rfc3339_timestamp");
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const daysInMonth = month >= 1 && month <= 12
    ? [31, leapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]!
    : 0;
  if (
    day < 1 || day > daysInMonth || Number(match[4]) > 23 || Number(match[5]) > 59 ||
    Number(match[6]) > 59 || (match[7] !== "Z" && (Number(match[9]) > 23 || Number(match[10]) > 59))
  ) {
    throw new StudySessionDecodeError(path, "expected_rfc3339_timestamp");
  }
  return value;
}

function leapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function optionalTimestamp(raw: unknown, path: string): string | undefined {
  const value = decoder.string(raw, path, true);
  return value ? timestamp(value, path) : undefined;
}

function assertTimestampOrder(earlier: string, later: string, path: string): void {
  if (Date.parse(later) < Date.parse(earlier)) {
    throw new StudySessionDecodeError(path, "timestamp_before_prior_state");
  }
}

function jsonObjectString(raw: string, path: string): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new StudySessionDecodeError(path, "expected_json_object_string");
  }
  decoder.record(parsed, path);
}

function decodeRecovery(raw: unknown, path: string): ModelRecovery {
  const value = decoder.record(raw, path);
  let schemaVersion: "model-recovery-v1" | undefined;
  if (Object.prototype.hasOwnProperty.call(value, "schema_version")) {
    const version = textValue(decoder.field(value, "schema_version", path), `${path}.schema_version`);
    if (version !== "model-recovery-v1") {
      throw new StudySessionDecodeError(`${path}.schema_version`, "unsupported_model_recovery_schema");
    }
    schemaVersion = version;
  }
  return {
    ...(schemaVersion ? { schemaVersion } : {}),
    recoveryId: identity(decoder.field(value, "recovery_id", path), `${path}.recovery_id`, 64),
    category: textValue(decoder.field(value, "category", path), `${path}.category`, { maximum: 128 }),
    reason: textValue(decoder.field(value, "reason", path), `${path}.reason`, { maximum: 2_000 }),
    strategy: textValue(decoder.field(value, "strategy", path), `${path}.strategy`, { maximum: 500 }),
    attempts: decoder.integer(decoder.field(value, "attempts", path), `${path}.attempts`, 1, 100),
    note: textValue(decoder.field(value, "note", path), `${path}.note`, { allowEmpty: true, maximum: 4_000 }),
    createdAt: timestamp(decoder.field(value, "created_at", path), `${path}.created_at`),
  };
}

function decodeRecoveries(raw: unknown, path: string): ModelRecovery[] {
  const items = decoder.array(raw, path, decodeRecovery);
  decoder.unique(items.map((item) => item.recoveryId), `${path}.recovery_id`);
  return items;
}

interface StudySceneState {
  ids: Set<string>;
  layers: number;
  objects: number;
  text: number;
}

function decodeStudySceneObject(raw: unknown, path: string, state: StudySceneState): SceneObjectSnapshot {
  const value = decoder.record(raw, path);
  const item: SceneObjectSnapshot = {
    id: identity(decoder.field(value, "id", path), `${path}.id`, 128),
    name: textValue(decoder.field(value, "name", path), `${path}.name`, { maximum: 500 }),
    description: textValue(decoder.field(value, "description", path), `${path}.description`, { allowEmpty: true, maximum: 4_000 }),
    interaction: textValue(decoder.field(value, "interaction", path), `${path}.interaction`, { allowEmpty: true, maximum: 4_000 }),
    tags: textValue(decoder.field(value, "tags", path), `${path}.tags`, { allowEmpty: true, maximum: 1_000 }),
    reuseId: textValue(decoder.field(value, "reuse_id", path), `${path}.reuse_id`, { allowEmpty: true, maximum: 128 }),
    reuseHint: textValue(decoder.field(value, "reuse_hint", path), `${path}.reuse_hint`, { allowEmpty: true, maximum: 1_000 }),
  };
  registerSceneIdentity(state, item.id, path);
  state.objects += 1;
  if (state.objects > SCENE_MAX_OBJECT_COUNT) {
    throw new StudySessionDecodeError(path, "scene_object_budget_exceeded");
  }
  state.text += item.name.length + item.description.length + item.interaction.length +
    item.tags.length + item.reuseId.length + item.reuseHint.length;
  return item;
}

function registerSceneIdentity(state: StudySceneState, id: string, path: string): void {
  if (state.ids.has(id)) {
    throw new StudySessionDecodeError(`${path}.id`, "duplicate_scene_identity");
  }
  state.ids.add(id);
}

function decodeStudySceneNode(
  raw: unknown,
  path: string,
  state: StudySceneState,
  depth: number,
): SceneTreeNode {
  if (depth > SCENE_MAX_DEPTH) {
    throw new StudySessionDecodeError(path, "scene_depth_budget_exceeded");
  }
  const value = decoder.record(raw, path);
  const id = identity(decoder.field(value, "id", path), `${path}.id`, 128);
  registerSceneIdentity(state, id, path);
  state.layers += 1;
  if (state.layers > SCENE_MAX_LAYER_COUNT) {
    throw new StudySessionDecodeError(path, "scene_layer_budget_exceeded");
  }
  const objects = decoder.array(
    decoder.field(value, "objects", path), `${path}.objects`,
    (item, itemPath) => decodeStudySceneObject(item, itemPath, state),
  );
  const children = decoder.array(
    decoder.field(value, "children", path), `${path}.children`,
    (item, itemPath) => decodeStudySceneNode(item, itemPath, state, depth + 1),
  );
  if (objects.length > 16 || children.length > 8) {
    throw new StudySessionDecodeError(path, "scene_child_budget_exceeded");
  }
  const node: SceneTreeNode = {
    id,
    title: textValue(decoder.field(value, "title", path), `${path}.title`, { maximum: 500 }),
    scopeLabel: textValue(decoder.field(value, "scope_label", path), `${path}.scope_label`, { allowEmpty: true, maximum: 500 }),
    summary: textValue(decoder.field(value, "summary", path), `${path}.summary`, { allowEmpty: true, maximum: 4_000 }),
    atmosphere: textValue(decoder.field(value, "atmosphere", path), `${path}.atmosphere`, { allowEmpty: true, maximum: 4_000 }),
    rules: textValue(decoder.field(value, "rules", path), `${path}.rules`, { allowEmpty: true, maximum: 4_000 }),
    entrance: textValue(decoder.field(value, "entrance", path), `${path}.entrance`, { allowEmpty: true, maximum: 4_000 }),
    tags: textValue(decoder.field(value, "tags", path), `${path}.tags`, { allowEmpty: true, maximum: 1_000 }),
    reuseId: textValue(decoder.field(value, "reuse_id", path), `${path}.reuse_id`, { allowEmpty: true, maximum: 128 }),
    reuseHint: textValue(decoder.field(value, "reuse_hint", path), `${path}.reuse_hint`, { allowEmpty: true, maximum: 1_000 }),
    objects,
    children,
  };
  state.text += node.title.length + node.scopeLabel.length + node.summary.length +
    node.atmosphere.length + node.rules.length + node.entrance.length + node.tags.length +
    node.reuseId.length + node.reuseHint.length;
  return node;
}

function findSceneLayer(
  tree: SceneTreeNode[],
  targetId: string,
  parentPath: string[] = [],
): { node: SceneTreeNode; titlePath: string[] } | undefined {
  for (const node of tree) {
    const titlePath = [...parentPath, node.title];
    if (node.id === targetId) return { node, titlePath };
    const child = findSceneLayer(node.children, targetId, titlePath);
    if (child) return child;
  }
  return undefined;
}

function sceneObjectTags(objects: SceneObjectSnapshot[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const object of objects) {
    for (const rawTag of object.tags.split(",")) {
      const tag = rawTag.trim();
      if (!tag || seen.has(tag)) continue;
      seen.add(tag);
      result.push(tag);
      if (result.length === 8) return result;
    }
  }
  return result;
}

function arraysEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

/** Study Session scenes allow empty trees and tool-created members with empty
 * reuse IDs, so the stricter Scene Setup committed decoder is not reusable. */
export function decodeStudySceneProfile(raw: unknown, path = "study_scene_profile"): SceneProfile {
  const value = decoder.record(raw, path);
  const sceneName = textValue(decoder.field(value, "scene_name", path), `${path}.scene_name`, { allowEmpty: true, maximum: 500 });
  const sceneId = identity(decoder.field(value, "scene_id", path), `${path}.scene_id`, 128);
  const title = textValue(decoder.field(value, "title", path), `${path}.title`, { maximum: 500 });
  const summary = textValue(decoder.field(value, "summary", path), `${path}.summary`, { maximum: 4_000 });
  const tags = decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`);
  const selectedPath = decoder.stringArray(decoder.field(value, "selected_path", path), `${path}.selected_path`);
  const focusObjectNames = decoder.stringArray(decoder.field(value, "focus_object_names", path), `${path}.focus_object_names`);
  decoder.unique(tags, `${path}.tags`);
  decoder.unique(focusObjectNames, `${path}.focus_object_names`);
  const state: StudySceneState = {
    ids: new Set(), layers: 0, objects: 0,
    text: sceneName.length + title.length + summary.length + tags.join("").length +
      selectedPath.join("").length + focusObjectNames.join("").length,
  };
  const sceneTree = decoder.array(
    decoder.field(value, "scene_tree", path), `${path}.scene_tree`,
    (item, itemPath) => decodeStudySceneNode(item, itemPath, state, 1),
  );
  if (sceneTree.length > 8 || state.text > SCENE_MAX_TEXT_BUDGET) {
    throw new StudySessionDecodeError(`${path}.scene_tree`, "scene_budget_exceeded");
  }
  if (sceneTree.length === 0) {
    const fallbackTitle = sceneName || "未命名场景";
    if (
      sceneId !== "scene-empty" || title !== fallbackTitle ||
      !arraysEqual(selectedPath, [fallbackTitle]) || tags.length || focusObjectNames.length
    ) {
      throw new StudySessionDecodeError(path, "invalid_empty_study_scene_profile");
    }
  } else {
    const selected = findSceneLayer(sceneTree, sceneId);
    if (!selected) {
      throw new StudySessionDecodeError(`${path}.scene_id`, "selected_scene_layer_missing");
    }
    if (title !== selected.node.title || !arraysEqual(selectedPath, selected.titlePath)) {
      throw new StudySessionDecodeError(path, "study_scene_selected_projection_mismatch");
    }
    const expectedFocus = selected.node.objects.slice(0, 4).map((item) => item.name).filter(Boolean);
    if (!arraysEqual(focusObjectNames, expectedFocus) || !arraysEqual(tags, sceneObjectTags(selected.node.objects))) {
      throw new StudySessionDecodeError(path, "study_scene_object_projection_mismatch");
    }
  }
  return { sceneName, sceneId, title, summary, tags, selectedPath, focusObjectNames, sceneTree };
}

function nullableScene(raw: unknown, path: string): SceneProfile | undefined {
  return decoder.nullable(raw, path, decodeStudySceneProfile) ?? undefined;
}

function decodeAttachment(raw: unknown, path: string) {
  const value = decoder.record(raw, path);
  if (Object.prototype.hasOwnProperty.call(value, "stored_path")) {
    throw new StudySessionDecodeError(`${path}.stored_path`, "private_storage_path_exposed");
  }
  const kind = decoder.enumeration(decoder.field(value, "kind", path), ATTACHMENT_KINDS, `${path}.kind`);
  const imageUrl = textValue(decoder.field(value, "image_url", path), `${path}.image_url`, { allowEmpty: true, maximum: 2_000_000 });
  const textExcerpt = textValue(decoder.field(value, "text_excerpt", path), `${path}.text_excerpt`, { allowEmpty: true, maximum: 20_000 });
  const pageCount = decoder.integer(decoder.field(value, "page_count", path), `${path}.page_count`, 0, 100_000);
  const previewable = decoder.boolean(decoder.field(value, "previewable", path), `${path}.previewable`);
  if (
    (kind === "image" && (!imageUrl || textExcerpt || pageCount !== 1 || !previewable)) ||
    (kind === "pdf" && (imageUrl || !textExcerpt || pageCount < 1 || !previewable)) ||
    (kind === "text" && (imageUrl || !textExcerpt || pageCount !== 0 || previewable))
  ) {
    throw new StudySessionDecodeError(path, `invalid_${kind}_attachment_projection`);
  }
  const source = textValue(decoder.field(value, "source", path), `${path}.source`, { maximum: 64 });
  if (source !== "learner_upload") {
    throw new StudySessionDecodeError(`${path}.source`, "unexpected_attachment_source");
  }
  return {
    attachmentId: identity(decoder.field(value, "attachment_id", path), `${path}.attachment_id`),
    name: textValue(decoder.field(value, "name", path), `${path}.name`, { maximum: 500 }),
    mimeType: textValue(decoder.field(value, "mime_type", path), `${path}.mime_type`, { maximum: 255 }),
    kind,
    sizeBytes: decoder.integer(decoder.field(value, "size_bytes", path), `${path}.size_bytes`, 0, 100_000_000),
    ...(imageUrl ? { imageUrl } : {}),
    ...(textExcerpt ? { textExcerpt: compactPreviewString(textExcerpt, 240) } : {}),
    source,
    pageCount,
    previewable,
  };
}

function decodeCitation(raw: unknown, path: string): Citation {
  const value = decoder.record(raw, path);
  const sourceKind = decoder.enumeration(
    decoder.field(value, "source_kind", path), CITATION_SOURCE_KINDS, `${path}.source_kind`,
  );
  const sectionId = textValue(decoder.field(value, "section_id", path), `${path}.section_id`, { allowEmpty: true, maximum: 160 });
  const sourceId = textValue(decoder.field(value, "source_id", path), `${path}.source_id`, { allowEmpty: true, maximum: 160 });
  if ((sourceKind === "document" && !sectionId) || (sourceKind !== "document" && (!sourceId || sectionId !== sourceId))) {
    throw new StudySessionDecodeError(path, "citation_source_identity_invalid");
  }
  const pageStart = decoder.integer(decoder.field(value, "page_start", path), `${path}.page_start`, 1, 100_000);
  const pageEnd = decoder.integer(decoder.field(value, "page_end", path), `${path}.page_end`, 1, 100_000);
  decoder.range(pageStart, pageEnd, `${path}.page_range`);
  return {
    sectionId,
    title: textValue(decoder.field(value, "title", path), `${path}.title`, { maximum: 1_000 }),
    pageStart,
    pageEnd,
    sourceKind,
    ...(sourceId ? { sourceId } : {}),
  };
}

function decodeCitations(raw: unknown, path: string): Citation[] {
  const items = decoder.array(raw, path, decodeCitation);
  decoder.unique(items.map((item) => [
    item.sourceKind ?? "document", item.sourceId ?? "", item.sectionId,
    item.pageStart, item.pageEnd, item.title,
  ].join("\u0000")), path);
  return items;
}

function decodeToolCalls(raw: unknown, path: string): ChatToolCallTrace[] {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    const argumentsJson = textValue(decoder.field(value, "arguments_json", itemPath), `${itemPath}.arguments_json`, { maximum: 100_000 });
    const resultJson = textValue(decoder.field(value, "result_json", itemPath), `${itemPath}.result_json`, { maximum: 500_000 });
    jsonObjectString(argumentsJson, `${itemPath}.arguments_json`);
    jsonObjectString(resultJson, `${itemPath}.result_json`);
    return {
      toolCallId: identity(decoder.field(value, "tool_call_id", itemPath), `${itemPath}.tool_call_id`),
      toolName: decoder.enumeration(decoder.field(value, "tool_name", itemPath), CHAT_TOOL_NAMES, `${itemPath}.tool_name`),
      argumentsJson: compactPreviewString(argumentsJson, 800),
      resultSummary: compactPreviewString(
        textValue(decoder.field(value, "result_summary", itemPath), `${itemPath}.result_summary`, { allowEmpty: true, maximum: 10_000 }), 240,
      ),
      resultJson: compactPreviewString(resultJson, 1_200),
    };
  });
  decoder.unique(items.map((item) => item.toolCallId), `${path}.tool_call_id`);
  return items;
}

function decodeCharacterEvents(raw: unknown, path: string, toolCalls: ChatToolCallTrace[]) {
  const toolNames = new Set(toolCalls.map((item) => item.toolName));
  return decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    const toolName = textValue(decoder.field(value, "tool_name", itemPath), `${itemPath}.tool_name`, { allowEmpty: true, maximum: 128 });
    const toolSummary = textValue(decoder.field(value, "tool_summary", itemPath), `${itemPath}.tool_summary`, { allowEmpty: true, maximum: 10_000 });
    if (Boolean(toolName) !== Boolean(toolSummary) || (toolName && !toolNames.has(toolName))) {
      throw new StudySessionDecodeError(itemPath, "character_event_tool_reference_invalid");
    }
    const deliveryCue = textValue(decoder.field(value, "delivery_cue", itemPath), `${itemPath}.delivery_cue`, { allowEmpty: true, maximum: 2_000 });
    const commentary = textValue(decoder.field(value, "commentary", itemPath), `${itemPath}.commentary`, { allowEmpty: true, maximum: 4_000 });
    return {
      emotion: textValue(decoder.field(value, "emotion", itemPath), `${itemPath}.emotion`, { maximum: 128 }),
      action: textValue(decoder.field(value, "action", itemPath), `${itemPath}.action`, { maximum: 2_000 }),
      speechStyle: textValue(decoder.field(value, "speech_style", itemPath), `${itemPath}.speech_style`, { maximum: 500 }),
      sceneHint: textValue(decoder.field(value, "scene_hint", itemPath), `${itemPath}.scene_hint`, { allowEmpty: true, maximum: 2_000 }),
      lineSegmentId: identity(decoder.field(value, "line_segment_id", itemPath), `${itemPath}.line_segment_id`, 500),
      timingHint: decoder.enumeration(decoder.field(value, "timing_hint", itemPath), CHARACTER_TIMING_HINTS, `${itemPath}.timing_hint`),
      ...(toolName ? { toolName } : {}),
      ...(toolSummary ? { toolSummary: compactPreviewString(toolSummary, 240) } : {}),
      ...(deliveryCue ? { deliveryCue: compactPreviewString(deliveryCue, 160) } : {}),
      ...(commentary ? { commentary: compactPreviewString(commentary, 280) } : {}),
    };
  });
}

function decodeRichBlocks(raw: unknown, path: string) {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    return {
      kind: textValue(decoder.field(value, "kind", itemPath), `${itemPath}.kind`, { maximum: 64 }).trim(),
      content: textValue(decoder.field(value, "content", itemPath), `${itemPath}.content`, { maximum: 100_000 }).trim(),
    };
  });
  decoder.unique(items.map((item) => `${item.kind.toLowerCase()}:${item.content}`), path);
  return items;
}

function decodeQuestionResult(raw: unknown, path: string) {
  const value = decoder.record(raw, path);
  if (decoder.field(value, "schema_version", path) !== "study-question-result-v1") {
    throw new StudySessionDecodeError(`${path}.schema_version`, "unsupported_question_result_schema");
  }
  const attemptId = decoder.nullable(decoder.field(value, "attempt_id", path), `${path}.attempt_id`, identity);
  const clientAttemptId = decoder.nullable(decoder.field(value, "client_attempt_id", path), `${path}.client_attempt_id`, identity);
  const beforeRevision = decoder.nullable(
    decoder.field(value, "before_revision", path), `${path}.before_revision`,
    (item, itemPath) => decoder.integer(item, itemPath, 0),
  );
  const committedRevision = decoder.nullable(
    decoder.field(value, "committed_revision", path), `${path}.committed_revision`,
    (item, itemPath) => decoder.integer(item, itemPath, 1),
  );
  const committedAt = decoder.nullable(decoder.field(value, "committed_at", path), `${path}.committed_at`, timestamp);
  const terminal = [attemptId, clientAttemptId, beforeRevision, committedRevision, committedAt];
  const count = terminal.filter((item) => item !== null).length;
  if ((count !== 0 && count !== terminal.length) || (beforeRevision !== null && committedRevision !== beforeRevision + 1)) {
    throw new StudySessionDecodeError(path, "question_result_commit_evidence_invalid");
  }
  return {
    schemaVersion: "study-question-result-v1" as const,
    attemptId,
    clientAttemptId,
    submittedAnswer: textValue(decoder.field(value, "submitted_answer", path), `${path}.submitted_answer`, { maximum: 8_000 }),
    isCorrect: decoder.boolean(decoder.field(value, "is_correct", path), `${path}.is_correct`),
    feedbackText: textValue(decoder.field(value, "feedback_text", path), `${path}.feedback_text`, { maximum: 10_000 }),
    explanation: textValue(decoder.field(value, "explanation", path), `${path}.explanation`, { allowEmpty: true, maximum: 8_000 }),
    beforeRevision,
    committedRevision,
    committedAt,
  };
}

function decodeQuestion(raw: unknown, path: string, sessionRevision: number) {
  if (raw === null) return undefined;
  const value = decoder.record(raw, path);
  for (const field of [
    "grading_spec", "answer_key", "accepted_answers", "explanation", "submitted_answer",
    "is_correct", "feedback_text", "normalized_answer",
  ]) {
    if (Object.prototype.hasOwnProperty.call(value, field)) {
      throw new StudySessionDecodeError(`${path}.${field}`, "private_question_material_exposed");
    }
  }
  if (decoder.field(value, "schema_version", path) !== "study-interactive-question-v2") {
    throw new StudySessionDecodeError(`${path}.schema_version`, "unsupported_question_schema");
  }
  const questionType = decoder.enumeration(decoder.field(value, "question_type", path), QUESTION_TYPES, `${path}.question_type`);
  const options = decoder.array(decoder.field(value, "options", path), `${path}.options`, (item, itemPath) => {
    const option = decoder.record(item, itemPath);
    return {
      key: textValue(decoder.field(option, "key", itemPath), `${itemPath}.key`, { maximum: 16 }),
      text: textValue(decoder.field(option, "text", itemPath), `${itemPath}.text`, { maximum: 2_000 }),
    };
  });
  decoder.unique(options.map((item) => item.key), `${path}.options.key`);
  if (
    (questionType === "fill_blank" && options.length !== 0) ||
    (questionType === "multiple_choice" && options.length !== 0 && options.length < 2) ||
    options.length > 8
  ) {
    throw new StudySessionDecodeError(`${path}.options`, `invalid_${questionType}_options`);
  }
  const result = decoder.nullable(decoder.field(value, "result", path), `${path}.result`, decodeQuestionResult);
  if (result?.committedRevision !== null && result?.committedRevision !== undefined && result.committedRevision > sessionRevision) {
    throw new StudySessionDecodeError(`${path}.result.committed_revision`, "question_result_after_session_revision");
  }
  return {
    schemaVersion: "study-interactive-question-v2" as const,
    questionType,
    prompt: textValue(decoder.field(value, "prompt", path), `${path}.prompt`, { maximum: 8_000 }),
    difficulty: decoder.enumeration(decoder.field(value, "difficulty", path), QUESTION_DIFFICULTIES, `${path}.difficulty`),
    topic: textValue(decoder.field(value, "topic", path), `${path}.topic`, { allowEmpty: true, maximum: 500 }),
    options,
    callBack: decoder.boolean(decoder.field(value, "call_back", path), `${path}.call_back`),
    result,
  };
}

function decodePersonaTrace(raw: unknown, path: string) {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    return {
      kind: textValue(decoder.field(value, "kind", itemPath), `${itemPath}.kind`, { maximum: 128 }),
      label: textValue(decoder.field(value, "label", itemPath), `${itemPath}.label`, { allowEmpty: true, maximum: 500 }),
      contentExcerpt: compactPreviewString(textValue(decoder.field(value, "content_excerpt", itemPath), `${itemPath}.content_excerpt`, { allowEmpty: true, maximum: 4_000 }), 280),
      reason: textValue(decoder.field(value, "reason", itemPath), `${itemPath}.reason`, { allowEmpty: true, maximum: 2_000 }),
    };
  });
  decoder.unique(items.map((item) => item.kind), `${path}.kind`);
  return items;
}

function decodeMemoryTrace(raw: unknown, path: string) {
  return decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    return {
      sessionId: identity(decoder.field(value, "session_id", itemPath), `${itemPath}.session_id`),
      studyUnitId: identity(decoder.field(value, "study_unit_id", itemPath), `${itemPath}.study_unit_id`),
      sceneTitle: textValue(decoder.field(value, "scene_title", itemPath), `${itemPath}.scene_title`, { allowEmpty: true, maximum: 1_000 }),
      score: decoder.finiteNumber(decoder.field(value, "score", itemPath), `${itemPath}.score`, 0, 2),
      snippet: compactPreviewString(textValue(decoder.field(value, "snippet", itemPath), `${itemPath}.snippet`, { allowEmpty: true, maximum: 20_000 }), 240),
      createdAt: timestamp(decoder.field(value, "created_at", itemPath), `${itemPath}.created_at`),
      source: decoder.enumeration(decoder.field(value, "source", itemPath), MEMORY_TRACE_SOURCES, `${itemPath}.source`),
    };
  });
}

interface DecodedChatFields extends StudyChatResponse {}

function decodeChatFields(raw: Record<string, unknown>, path: string, sessionRevision: number): DecodedChatFields {
  const reply = textValue(decoder.field(raw, "reply", path), `${path}.reply`, { maximum: 100_000 });
  const richBlocks = decodeRichBlocks(decoder.field(raw, "rich_blocks", path), `${path}.rich_blocks`);
  const repaired = repairLegacyRichReply(reply, richBlocks);
  const toolCalls = decodeToolCalls(decoder.field(raw, "tool_calls", path), `${path}.tool_calls`);
  return {
    reply: repaired.reply,
    citations: decodeCitations(decoder.field(raw, "citations", path), `${path}.citations`),
    characterEvents: decodeCharacterEvents(decoder.field(raw, "character_events", path), `${path}.character_events`, toolCalls),
    richBlocks: repaired.richBlocks,
    interactiveQuestion: decodeQuestion(decoder.field(raw, "interactive_question", path), `${path}.interactive_question`, sessionRevision),
    personaSlotTrace: decodePersonaTrace(decoder.field(raw, "persona_slot_trace", path), `${path}.persona_slot_trace`),
    memoryTrace: decodeMemoryTrace(decoder.field(raw, "memory_trace", path), `${path}.memory_trace`),
    toolCalls,
    sceneProfile: nullableScene(decoder.field(raw, "scene_profile", path), `${path}.scene_profile`),
    modelRecoveries: decodeRecoveries(decoder.field(raw, "model_recoveries", path), `${path}.model_recoveries`),
  };
}

function decodeTurn(raw: unknown, index: number, path: string, sessionRevision: number): DialogueTurnRecord {
  const value = decoder.record(raw, path);
  const sequence = decoder.integer(decoder.field(value, "sequence", path), `${path}.sequence`, 1);
  if (sequence !== index + 1) {
    throw new StudySessionDecodeError(`${path}.sequence`, `expected_contiguous_sequence_${index + 1}`);
  }
  const attachments = decoder.array(decoder.field(value, "learner_attachments", path), `${path}.learner_attachments`, decodeAttachment);
  decoder.unique(attachments.map((item) => item.attachmentId), `${path}.learner_attachments.attachment_id`);
  const chat = decodeChatFields({
    reply: decoder.field(value, "assistant_reply", path),
    citations: decoder.field(value, "citations", path),
    character_events: decoder.field(value, "character_events", path),
    rich_blocks: decoder.field(value, "rich_blocks", path),
    interactive_question: decoder.field(value, "interactive_question", path),
    persona_slot_trace: decoder.field(value, "persona_slot_trace", path),
    memory_trace: decoder.field(value, "memory_trace", path),
    tool_calls: decoder.field(value, "tool_calls", path),
    scene_profile: decoder.field(value, "scene_profile", path),
    model_recoveries: decoder.field(value, "model_recoveries", path),
  }, path, sessionRevision);
  return {
    id: identity(decoder.field(value, "id", path), `${path}.id`),
    sequence,
    learnerMessage: textValue(decoder.field(value, "learner_message", path), `${path}.learner_message`, { allowEmpty: true, maximum: 100_000 }),
    learnerMessageKind: decoder.enumeration(decoder.field(value, "learner_message_kind", path), LEARNER_MESSAGE_KINDS, `${path}.learner_message_kind`),
    learnerAttachments: attachments,
    assistantReply: chat.reply,
    citations: chat.citations,
    characterEvents: chat.characterEvents,
    richBlocks: chat.richBlocks,
    interactiveQuestion: chat.interactiveQuestion,
    personaSlotTrace: chat.personaSlotTrace,
    memoryTrace: chat.memoryTrace,
    toolCalls: chat.toolCalls,
    sceneProfile: chat.sceneProfile,
    modelRecoveries: chat.modelRecoveries,
    createdAt: timestamp(decoder.field(value, "created_at", path), `${path}.created_at`),
  };
}

function decodeFollowUps(raw: unknown, path: string): SessionFollowUp[] {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    const status = decoder.enumeration(
      decoder.field(value, "status", itemPath), FOLLOW_UP_STATUSES, `${itemPath}.status`,
    );
    const completedAt = optionalTimestamp(decoder.field(value, "completed_at", itemPath), `${itemPath}.completed_at`);
    const canceledAt = optionalTimestamp(decoder.field(value, "canceled_at", itemPath), `${itemPath}.canceled_at`);
    if (
      (status === "pending" && (completedAt || canceledAt)) ||
      (status === "completed" && (!completedAt || canceledAt)) ||
      (status === "canceled" && (completedAt || !canceledAt))
    ) {
      throw new StudySessionDecodeError(itemPath, `invalid_${status}_follow_up_terminal_state`);
    }
    const createdAt = timestamp(decoder.field(value, "created_at", itemPath), `${itemPath}.created_at`);
    const dueAt = timestamp(decoder.field(value, "due_at", itemPath), `${itemPath}.due_at`);
    assertTimestampOrder(createdAt, dueAt, `${itemPath}.due_at`);
    if (completedAt) assertTimestampOrder(createdAt, completedAt, `${itemPath}.completed_at`);
    if (canceledAt) assertTimestampOrder(createdAt, canceledAt, `${itemPath}.canceled_at`);
    return {
      id: identity(decoder.field(value, "id", itemPath), `${itemPath}.id`),
      triggerKind: decoder.enumeration(
        decoder.field(value, "trigger_kind", itemPath), ["scheduled_reply"] as const, `${itemPath}.trigger_kind`,
      ),
      status,
      delaySeconds: decoder.integer(decoder.field(value, "delay_seconds", itemPath), `${itemPath}.delay_seconds`, 0, 1_800),
      dueAt,
      hiddenMessage: textValue(decoder.field(value, "hidden_message", itemPath), `${itemPath}.hidden_message`, { maximum: 20_000 }),
      reason: textValue(decoder.field(value, "reason", itemPath), `${itemPath}.reason`, { allowEmpty: true, maximum: 1_200 }),
      createdAt,
      ...(completedAt ? { completedAt } : {}),
      ...(canceledAt ? { canceledAt } : {}),
    };
  });
  decoder.unique(items.map((item) => item.id), `${path}.id`);
  return items;
}

function decodeSessionMemory(raw: unknown, path: string): SessionMemoryEntry[] {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    const createdAt = timestamp(decoder.field(value, "created_at", itemPath), `${itemPath}.created_at`);
    const updatedAt = timestamp(decoder.field(value, "updated_at", itemPath), `${itemPath}.updated_at`);
    assertTimestampOrder(createdAt, updatedAt, `${itemPath}.updated_at`);
    return {
      id: identity(decoder.field(value, "id", itemPath), `${itemPath}.id`),
      key: textValue(decoder.field(value, "key", itemPath), `${itemPath}.key`, { maximum: 200 }),
      content: compactPreviewString(
        textValue(decoder.field(value, "content", itemPath), `${itemPath}.content`, { maximum: 20_000 }), 280,
      ),
      source: textValue(decoder.field(value, "source", itemPath), `${itemPath}.source`, { maximum: 128 }),
      createdAt,
      updatedAt,
    };
  });
  decoder.unique(items.map((item) => item.id), `${path}.id`);
  decoder.unique(items.map((item) => item.key), `${path}.key`);
  return items;
}

function decodeAffinity(raw: unknown, path: string): SessionAffinityState {
  const value = decoder.record(raw, path);
  const score = decoder.integer(decoder.field(value, "score", path), `${path}.score`, -100, 100);
  const level = decoder.enumeration(decoder.field(value, "level", path), AFFINITY_LEVELS, `${path}.level`);
  const summary = textValue(decoder.field(value, "summary", path), `${path}.summary`, { allowEmpty: true, maximum: 1_200 });
  const updatedAt = optionalTimestamp(decoder.field(value, "updated_at", path), `${path}.updated_at`);
  const events = decoder.array(decoder.field(value, "events", path), `${path}.events`, (item, itemPath) => {
    const event = decoder.record(item, itemPath);
    return {
      id: identity(decoder.field(event, "id", itemPath), `${itemPath}.id`),
      delta: decoder.integer(decoder.field(event, "delta", itemPath), `${itemPath}.delta`, -100, 100),
      reason: textValue(decoder.field(event, "reason", itemPath), `${itemPath}.reason`, { allowEmpty: true, maximum: 1_200 }),
      source: textValue(decoder.field(event, "source", itemPath), `${itemPath}.source`, { maximum: 128 }),
      createdAt: timestamp(decoder.field(event, "created_at", itemPath), `${itemPath}.created_at`),
    };
  });
  decoder.unique(events.map((item) => item.id), `${path}.events.id`);
  const mutated = events.length > 0 || score !== 0 || level !== "neutral" || Boolean(summary);
  if (mutated !== Boolean(updatedAt)) {
    throw new StudySessionDecodeError(`${path}.updated_at`, "affinity_state_timestamp_mismatch");
  }
  if (updatedAt && events.length) {
    for (const [index, event] of events.entries()) {
      assertTimestampOrder(event.createdAt, updatedAt, `${path}.events[${index}].created_at`);
    }
  }
  return { score, level, summary, updatedAt: updatedAt ?? "", events };
}

function decodeConfirmationPayload(
  raw: unknown,
  path: string,
  action: "update_plan" | "update_plan_progress",
): Record<string, unknown> {
  const value = decoder.record(raw, path);
  if (action === "update_plan") {
    textValue(decoder.field(value, "course_title", path), `${path}.course_title`, { maximum: 1_000 });
    textValue(decoder.field(value, "note", path), `${path}.note`, { allowEmpty: true, maximum: 2_000 });
  } else {
    const ids = decoder.stringArray(decoder.field(value, "schedule_ids", path), `${path}.schedule_ids`);
    if (!ids.length) throw new StudySessionDecodeError(`${path}.schedule_ids`, "expected_non_empty_array");
    decoder.unique(ids, `${path}.schedule_ids`);
    decoder.enumeration(
      decoder.field(value, "status", path),
      ["planned", "in_progress", "completed", "blocked", "skipped"] as const,
      `${path}.status`,
    );
    textValue(decoder.field(value, "note", path), `${path}.note`, { allowEmpty: true, maximum: 2_000 });
  }
  return value;
}

function decodeConfirmations(
  raw: unknown,
  path: string,
  sessionPlanId: string | null,
): SessionPlanConfirmation[] {
  const items = decoder.array(raw, path, (item, itemPath) => {
    const value = decoder.record(item, itemPath);
    const actionType = decoder.enumeration(
      decoder.field(value, "action_type", itemPath),
      ["update_plan", "update_plan_progress"] as const,
      `${itemPath}.action_type`,
    );
    const toolName = decoder.enumeration(
      decoder.field(value, "tool_name", itemPath),
      ["update_learning_plan", "update_learning_plan_progress"] as const,
      `${itemPath}.tool_name`,
    );
    const expectedTool = actionType === "update_plan" ? "update_learning_plan" : "update_learning_plan_progress";
    if (toolName !== expectedTool) {
      throw new StudySessionDecodeError(`${itemPath}.tool_name`, "confirmation_tool_action_mismatch");
    }
    const planId = identity(decoder.field(value, "plan_id", itemPath), `${itemPath}.plan_id`);
    if (!sessionPlanId || planId !== sessionPlanId) {
      throw new StudySessionDecodeError(`${itemPath}.plan_id`, "confirmation_session_plan_mismatch");
    }
    const status = decoder.enumeration(
      decoder.field(value, "status", itemPath), PLAN_CONFIRMATION_STATUSES, `${itemPath}.status`,
    );
    const resolvedAt = optionalTimestamp(decoder.field(value, "resolved_at", itemPath), `${itemPath}.resolved_at`);
    const resolutionNote = textValue(
      decoder.field(value, "resolution_note", itemPath), `${itemPath}.resolution_note`,
      { allowEmpty: true, maximum: 2_000 },
    );
    if ((status === "pending") === Boolean(resolvedAt)) {
      throw new StudySessionDecodeError(`${itemPath}.resolved_at`, `invalid_${status}_confirmation_terminal_state`);
    }
    const createdAt = timestamp(decoder.field(value, "created_at", itemPath), `${itemPath}.created_at`);
    if (resolvedAt) assertTimestampOrder(createdAt, resolvedAt, `${itemPath}.resolved_at`);
    return {
      id: identity(decoder.field(value, "id", itemPath), `${itemPath}.id`),
      toolName,
      actionType,
      planId,
      title: textValue(decoder.field(value, "title", itemPath), `${itemPath}.title`, { maximum: 1_000 }),
      summary: textValue(decoder.field(value, "summary", itemPath), `${itemPath}.summary`, { allowEmpty: true, maximum: 4_000 }),
      previewLines: decoder.stringArray(decoder.field(value, "preview_lines", itemPath), `${itemPath}.preview_lines`, true),
      payload: decodeConfirmationPayload(decoder.field(value, "payload", itemPath), `${itemPath}.payload`, actionType),
      status,
      createdAt,
      ...(resolvedAt ? { resolvedAt } : {}),
      ...(resolutionNote ? { resolutionNote } : {}),
    };
  });
  decoder.unique(items.map((item) => item.id), `${path}.id`);
  return items;
}

function decodeRect(raw: unknown, path: string) {
  const value = decoder.record(raw, path);
  return {
    x: decoder.finiteNumber(decoder.field(value, "x", path), `${path}.x`, 0, 1),
    y: decoder.finiteNumber(decoder.field(value, "y", path), `${path}.y`, 0, 1),
    width: decoder.finiteNumber(decoder.field(value, "width", path), `${path}.width`, 0, 1),
    height: decoder.finiteNumber(decoder.field(value, "height", path), `${path}.height`, 0, 1),
  };
}

function decodeProjectedPdf(raw: unknown, path: string): SessionProjectedPdf | null {
  if (raw === null) return null;
  const value = decoder.record(raw, path);
  const sourceKind = decoder.enumeration(
    decoder.field(value, "source_kind", path), PROJECTED_SOURCE_KINDS, `${path}.source_kind`,
  );
  const pageCount = decoder.integer(decoder.field(value, "page_count", path), `${path}.page_count`, 1, 100_000);
  const pageNumber = decoder.integer(decoder.field(value, "page_number", path), `${path}.page_number`, 1, pageCount);
  const imageUrl = textValue(decoder.field(value, "image_url", path), `${path}.image_url`, { allowEmpty: true, maximum: 2_000_000 });
  if (
    ((sourceKind === "attachment_image" || sourceKind === "generated_image") && (pageCount !== 1 || pageNumber !== 1)) ||
    (sourceKind === "generated_image" && !imageUrl)
  ) {
    throw new StudySessionDecodeError(path, "invalid_projected_source_projection");
  }
  const overlays = decoder.array(
    decoder.field(value, "overlays", path), `${path}.overlays`,
    (item, itemPath): ProjectedPdfOverlay => {
      const overlay = decoder.record(item, itemPath);
      const kind = decoder.enumeration(
        decoder.field(overlay, "kind", itemPath), PROJECTED_OVERLAY_KINDS, `${itemPath}.kind`,
      );
      const rects = decoder.array(decoder.field(overlay, "rects", itemPath), `${itemPath}.rects`, decodeRect);
      if (!rects.length || rects.length > 128) {
        throw new StudySessionDecodeError(`${itemPath}.rects`, "invalid_overlay_rect_count");
      }
      const quoteText = textValue(
        decoder.field(overlay, "quote_text", itemPath), `${itemPath}.quote_text`,
        { allowEmpty: true, maximum: 8_000 },
      );
      if ((kind === "text_highlight") !== Boolean(quoteText)) {
        throw new StudySessionDecodeError(`${itemPath}.quote_text`, `invalid_${kind}_quote_projection`);
      }
      return {
        id: identity(decoder.field(overlay, "id", itemPath), `${itemPath}.id`),
        kind,
        pageNumber: decoder.integer(decoder.field(overlay, "page_number", itemPath), `${itemPath}.page_number`, 1, pageCount),
        rects,
        label: textValue(decoder.field(overlay, "label", itemPath), `${itemPath}.label`, { allowEmpty: true, maximum: 1_200 }),
        ...(quoteText ? { quoteText } : {}),
        color: textValue(decoder.field(overlay, "color", itemPath), `${itemPath}.color`, { maximum: 32 }),
        createdAt: timestamp(decoder.field(overlay, "created_at", itemPath), `${itemPath}.created_at`),
      };
    },
  );
  decoder.unique(overlays.map((item) => item.id), `${path}.overlays.id`);
  return {
    sourceKind,
    sourceId: identity(decoder.field(value, "source_id", path), `${path}.source_id`),
    title: textValue(decoder.field(value, "title", path), `${path}.title`, { maximum: 1_000 }),
    pageNumber,
    pageCount,
    ...(imageUrl ? { imageUrl } : {}),
    overlays,
    updatedAt: timestamp(decoder.field(value, "updated_at", path), `${path}.updated_at`),
  };
}

type DecodedAttachment = NonNullable<DialogueTurnRecord["learnerAttachments"]>[number];

function validateCitationReferences(
  citations: Citation[],
  attachments: Map<string, DecodedAttachment>,
  projectedPdf: SessionProjectedPdf | null,
  path: string,
): void {
  for (const [index, citation] of citations.entries()) {
    if (citation.sourceKind === "attachment_pdf" || citation.sourceKind === "attachment_image") {
      const attachment = attachments.get(citation.sourceId ?? "");
      const expectedKind = citation.sourceKind === "attachment_pdf" ? "pdf" : "image";
      if (!attachment || attachment.kind !== expectedKind) {
        throw new StudySessionDecodeError(`${path}[${index}].source_id`, "citation_attachment_reference_missing");
      }
      if (citation.pageEnd > (attachment.pageCount ?? 0)) {
        throw new StudySessionDecodeError(`${path}[${index}].page_end`, "citation_exceeds_attachment_pages");
      }
    }
    if (
      citation.sourceKind === "generated_image" &&
      (projectedPdf?.sourceKind !== "generated_image" || projectedPdf.sourceId !== citation.sourceId)
    ) {
      throw new StudySessionDecodeError(`${path}[${index}].source_id`, "generated_image_citation_reference_missing");
    }
  }
}

export interface DecodeStudySessionOptions {
  path?: string;
  expectedSessionId?: string;
  expectedDocumentId?: string;
  expectedPersonaId?: string;
  expectedPlanId?: string | null;
  expectedStudyUnitId?: string;
  requireNoPendingFollowUps?: boolean;
}

export function decodeStudySession(
  raw: unknown,
  options: DecodeStudySessionOptions = {},
): StudySessionRecord {
  const path = options.path ?? "study_session";
  const value = decoder.record(raw, path);
  const id = identity(decoder.field(value, "id", path), `${path}.id`);
  const documentId = textValue(
    decoder.field(value, "document_id", path), `${path}.document_id`,
    { allowEmpty: true, maximum: 160 },
  );
  const personaId = identity(decoder.field(value, "persona_id", path), `${path}.persona_id`);
  const planId = decoder.nullable(decoder.field(value, "plan_id", path), `${path}.plan_id`, identity);
  const studyUnitId = identity(decoder.field(value, "study_unit_id", path), `${path}.study_unit_id`);
  const revision = decoder.integer(decoder.field(value, "revision", path), `${path}.revision`, 0);
  const lastTurnSequence = decoder.integer(
    decoder.field(value, "last_turn_sequence", path), `${path}.last_turn_sequence`, 0,
  );
  if (options.expectedSessionId !== undefined) decoder.equal(id, options.expectedSessionId, `${path}.id`);
  if (options.expectedDocumentId !== undefined) decoder.equal(documentId, options.expectedDocumentId, `${path}.document_id`);
  if (options.expectedPersonaId !== undefined) decoder.equal(personaId, options.expectedPersonaId, `${path}.persona_id`);
  if (options.expectedPlanId !== undefined && planId !== options.expectedPlanId) {
    throw new StudySessionDecodeError(`${path}.plan_id`, `identity_mismatch_expected_${String(options.expectedPlanId)}`);
  }
  if (options.expectedStudyUnitId !== undefined) decoder.equal(studyUnitId, options.expectedStudyUnitId, `${path}.study_unit_id`);

  const turns = decoder.array(
    decoder.field(value, "turns", path), `${path}.turns`,
    (item, itemPath, index) => decodeTurn(item, index, itemPath, revision),
  );
  decoder.unique(turns.map((turn) => turn.id), `${path}.turns.id`);
  if (lastTurnSequence !== turns.length) {
    throw new StudySessionDecodeError(`${path}.last_turn_sequence`, `expected_turn_count_${turns.length}`);
  }
  if (revision < lastTurnSequence) {
    throw new StudySessionDecodeError(`${path}.revision`, "revision_before_turn_watermark");
  }

  const sceneInstanceId = textValue(
    decoder.field(value, "scene_instance_id", path), `${path}.scene_instance_id`,
    { allowEmpty: true, maximum: 160 },
  );
  const sceneProfile = nullableScene(decoder.field(value, "scene_profile", path), `${path}.scene_profile`);
  if (Boolean(sceneInstanceId) !== Boolean(sceneProfile)) {
    throw new StudySessionDecodeError(`${path}.scene_instance_id`, "session_scene_binding_incomplete");
  }
  const preparedStudyUnitIds = decoder.stringArray(
    decoder.field(value, "prepared_study_unit_ids", path), `${path}.prepared_study_unit_ids`,
  );
  decoder.unique(preparedStudyUnitIds, `${path}.prepared_study_unit_ids`);
  const pendingFollowUps = decodeFollowUps(
    decoder.field(value, "pending_follow_ups", path), `${path}.pending_follow_ups`,
  );
  if (options.requireNoPendingFollowUps && pendingFollowUps.some((item) => item.status === "pending")) {
    throw new StudySessionDecodeError(`${path}.pending_follow_ups`, "pending_follow_up_remains_after_cancel");
  }
  const planConfirmations = decodeConfirmations(
    decoder.field(value, "plan_confirmations", path), `${path}.plan_confirmations`, planId,
  );
  const projectedPdf = decodeProjectedPdf(
    decoder.field(value, "projected_pdf", path), `${path}.projected_pdf`,
  );

  const attachments = new Map<string, DecodedAttachment>();
  let priorTurnAt: string | undefined;
  for (const [turnIndex, turn] of turns.entries()) {
    if (priorTurnAt) {
      assertTimestampOrder(priorTurnAt, turn.createdAt, `${path}.turns[${turnIndex}].created_at`);
    }
    priorTurnAt = turn.createdAt;
    for (const attachment of turn.learnerAttachments ?? []) {
      if (attachments.has(attachment.attachmentId)) {
        throw new StudySessionDecodeError(
          `${path}.turns[${turnIndex}].learner_attachments`, "duplicate_session_attachment_id",
        );
      }
      attachments.set(attachment.attachmentId, attachment);
    }
    validateCitationReferences(
      turn.citations, attachments, projectedPdf, `${path}.turns[${turnIndex}].citations`,
    );
  }
  if (projectedPdf?.sourceKind === "attachment_pdf" || projectedPdf?.sourceKind === "attachment_image") {
    const attachment = attachments.get(projectedPdf.sourceId);
    const expectedKind = projectedPdf.sourceKind === "attachment_pdf" ? "pdf" : "image";
    if (!attachment || attachment.kind !== expectedKind || projectedPdf.pageCount !== attachment.pageCount) {
      throw new StudySessionDecodeError(`${path}.projected_pdf.source_id`, "projected_attachment_reference_missing");
    }
  }

  const createdAt = timestamp(decoder.field(value, "created_at", path), `${path}.created_at`);
  const updatedAt = timestamp(decoder.field(value, "updated_at", path), `${path}.updated_at`);
  assertTimestampOrder(createdAt, updatedAt, `${path}.updated_at`);
  if (priorTurnAt) assertTimestampOrder(priorTurnAt, updatedAt, `${path}.updated_at`);
  return {
    id,
    documentId,
    personaId,
    planId,
    ...(sceneInstanceId ? { sceneInstanceId } : {}),
    ...(sceneProfile ? { sceneProfile } : {}),
    studyUnitId,
    studyUnitTitle: textValue(decoder.field(value, "study_unit_title", path), `${path}.study_unit_title`, { allowEmpty: true, maximum: 1_000 }),
    themeHint: textValue(decoder.field(value, "theme_hint", path), `${path}.theme_hint`, { allowEmpty: true, maximum: 4_000 }),
    sessionSystemPrompt: compactPreviewString(
      textValue(decoder.field(value, "session_system_prompt", path), `${path}.session_system_prompt`, { allowEmpty: true, maximum: 100_000 }), 1_200,
    ),
    status: decoder.enumeration(decoder.field(value, "status", path), SESSION_STATUSES, `${path}.status`),
    revision,
    lastTurnSequence,
    turns,
    preparedStudyUnitIds,
    pendingFollowUps,
    sessionMemory: decodeSessionMemory(decoder.field(value, "session_memory", path), `${path}.session_memory`),
    affinityState: decodeAffinity(decoder.field(value, "affinity_state", path), `${path}.affinity_state`),
    planConfirmations,
    projectedPdf,
    createdAt,
    updatedAt,
  };
}

export function decodeStudySessionList(
  raw: unknown,
  options: Omit<DecodeStudySessionOptions, "path" | "expectedSessionId" | "requireNoPendingFollowUps"> = {},
): StudySessionRecord[] {
  const path = "study_sessions";
  const value = decoder.record(raw, path);
  const items = decoder.array(
    decoder.field(value, "items", path), `${path}.items`,
    (item, itemPath) => decodeStudySession(item, { ...options, path: itemPath }),
  );
  decoder.unique(items.map((item) => item.id), `${path}.items.id`);
  return items;
}

export interface StudyChatCommittedEvidence {
  sessionId: string;
  admittedSessionRevision: number;
  committedSessionRevision: number;
  committedTurnId: string;
  committedTurnSequence: number;
}

export interface DecodedStudyChatExchange extends StudyChatResponse {
  session: StudySessionRecord;
}

export function decodeStudyChatExchange(
  raw: unknown,
  options: {
    path?: string;
    expectedSessionId: string;
    evidence?: StudyChatCommittedEvidence;
  },
): DecodedStudyChatExchange {
  const path = options.path ?? "study_chat_exchange";
  const value = decoder.record(raw, path);
  const session = decodeStudySession(decoder.field(value, "session", path), {
    path: `${path}.session`, expectedSessionId: options.expectedSessionId,
  });
  const fields = decodeChatFields(value, path, session.revision);
  const attachmentEntries = session.turns.flatMap((turn) =>
    (turn.learnerAttachments ?? []).map((item) => [item.attachmentId, item] as const)
  );
  validateCitationReferences(
    fields.citations, new Map(attachmentEntries), session.projectedPdf ?? null, `${path}.citations`,
  );
  const lastTurn = session.turns.at(-1);
  if (!lastTurn) {
    throw new StudySessionDecodeError(`${path}.session.turns`, "committed_chat_turn_missing");
  }
  if (options.evidence) {
    const evidence = options.evidence;
    if (
      evidence.sessionId !== session.id || evidence.committedSessionRevision !== session.revision ||
      evidence.committedTurnId !== lastTurn.id || evidence.committedTurnSequence !== lastTurn.sequence ||
      evidence.committedSessionRevision !== evidence.admittedSessionRevision + 1
    ) {
      throw new StudySessionDecodeError(`${path}.session`, "committed_chat_evidence_mismatch");
    }
  }
  const turnFields: DecodedChatFields = {
    reply: lastTurn.assistantReply,
    citations: lastTurn.citations,
    characterEvents: lastTurn.characterEvents,
    richBlocks: lastTurn.richBlocks,
    interactiveQuestion: lastTurn.interactiveQuestion,
    personaSlotTrace: lastTurn.personaSlotTrace,
    memoryTrace: lastTurn.memoryTrace,
    toolCalls: lastTurn.toolCalls,
    sceneProfile: lastTurn.sceneProfile,
    modelRecoveries: lastTurn.modelRecoveries,
  };
  if (!sameProjection(fields, turnFields)) {
    throw new StudySessionDecodeError(path, "chat_exchange_committed_turn_projection_mismatch");
  }
  return { ...fields, session };
}

export function decodeStudyPlanConfirmationDecisionResponse<TPlan extends LearningPlan>(
  raw: unknown,
  options: {
    expectedSessionId: string;
    expectedConfirmationId: string;
    expectedDecision: "approve" | "reject";
    decodePlan: (
      rawPlan: unknown,
      path: string,
      expectedPlanId: string,
      expectedDocumentId: string,
    ) => TPlan;
    path?: string;
  },
): { session: StudySessionRecord; plan: TPlan | null } {
  const path = options.path ?? "study_plan_confirmation_decision";
  const value = decoder.record(raw, path);
  const session = decodeStudySession(decoder.field(value, "session", path), {
    path: `${path}.session`, expectedSessionId: options.expectedSessionId,
  });
  const confirmation = session.planConfirmations?.find(
    (item) => item.id === options.expectedConfirmationId,
  );
  const expectedStatus = options.expectedDecision === "approve" ? "approved" : "rejected";
  if (!confirmation || confirmation.status !== expectedStatus || !confirmation.resolvedAt) {
    throw new StudySessionDecodeError(
      `${path}.session.plan_confirmations`, "confirmation_decision_read_back_mismatch",
    );
  }
  const rawPlan = decoder.field(value, "plan", path);
  if (options.expectedDecision === "reject") {
    if (rawPlan !== null) {
      throw new StudySessionDecodeError(`${path}.plan`, "rejected_confirmation_must_not_return_plan");
    }
    return { session, plan: null };
  }
  if (rawPlan === null) {
    throw new StudySessionDecodeError(`${path}.plan`, "approved_confirmation_plan_required");
  }
  return {
    session,
    plan: options.decodePlan(rawPlan, `${path}.plan`, confirmation.planId, session.documentId),
  };
}

function sameProjection(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function repairLegacyRichReply(
  reply: string,
  existingBlocks: Array<{ kind: string; content: string }>,
) {
  const normalizedBlocks = dedupeRichBlocks(existingBlocks);
  if (!reply.trimStart().startsWith("```json")) {
    const extracted = extractMermaidBlocks(reply);
    return {
      reply: extracted.reply,
      richBlocks: dedupeRichBlocks([...normalizedBlocks, ...extracted.richBlocks]),
    };
  }
  const textKey = '"text": "';
  const textStart = reply.indexOf(textKey);
  if (textStart === -1) return { reply, richBlocks: normalizedBlocks };
  try {
    const rawStart = textStart + textKey.length;
    const rawEnd = reply.indexOf('",\n  "mood"', rawStart);
    const rawText = rawEnd === -1
      ? reply.slice(rawStart).replace(/\r\n/g, "\n").replace(/\r/g, "\n")
        .replace(/"\s*}\s*```?\s*$/g, "").replace(/`+\s*$/g, "").trimEnd()
      : reply.slice(rawStart, rawEnd);
    const source = rawText.replace(/\\"/g, "__ESCAPED_QUOTE__")
      .replace(/"/g, '\\"').replace(/__ESCAPED_QUOTE__/g, '\\"').replace(/\r?\n/g, "\\n");
    const recovered = JSON.parse(`"${source}"`) as string;
    const extracted = extractMermaidBlocks(recovered);
    return {
      reply: extracted.reply,
      richBlocks: dedupeRichBlocks([...normalizedBlocks, ...extracted.richBlocks]),
    };
  } catch {
    return { reply, richBlocks: normalizedBlocks };
  }
}

function extractMermaidBlocks(reply: string) {
  const richBlocks: Array<{ kind: string; content: string }> = [];
  const cleaned = reply.replace(
    /```mermaid\s*\n([\s\S]*?)```|```\s*\nmermaid\s*\n([\s\S]*?)```/gi,
    (_, first, second) => {
      const content = String(first ?? second ?? "").trim();
      if (content) richBlocks.push({ kind: "mermaid", content });
      return "\n\n";
    },
  ).replace(/\n{3,}/g, "\n\n").trim();
  return { reply: cleaned, richBlocks: dedupeRichBlocks(richBlocks) };
}

function dedupeRichBlocks(items: Array<{ kind: string; content: string }>) {
  const result: Array<{ kind: string; content: string }> = [];
  const seen = new Set<string>();
  for (const item of items) {
    const kind = item.kind.trim();
    const content = item.content.trim();
    const key = `${kind.toLowerCase()}:${content}`;
    if (!kind || !content || seen.has(key)) continue;
    seen.add(key);
    result.push({ kind, content });
  }
  return result;
}

function decodeTurnIdentity(
  raw: unknown,
  index: number,
  path: string,
): Pick<DialogueTurnRecord, "id" | "sequence"> {
  const value = decoder.record(raw, path);
  const sequence = decoder.integer(decoder.field(value, "sequence", path), `${path}.sequence`, 1);
  if (sequence !== index + 1) {
    throw new StudySessionDecodeError(`${path}.sequence`, `expected_contiguous_sequence_${index + 1}`);
  }
  return { id: identity(decoder.field(value, "id", path), `${path}.id`), sequence };
}

export interface StudySessionCommittedIdentity {
  revision: number;
  lastTurnSequence: number;
  turns: Array<Pick<DialogueTurnRecord, "id" | "sequence">>;
}

export function decodeStudySessionCommittedIdentity(
  raw: unknown,
  path = "study_session",
): StudySessionCommittedIdentity {
  const value = decoder.record(raw, path);
  const revision = decoder.integer(decoder.field(value, "revision", path), `${path}.revision`, 0);
  const lastTurnSequence = decoder.integer(
    decoder.field(value, "last_turn_sequence", path), `${path}.last_turn_sequence`, 0,
  );
  const turns = decoder.array(
    decoder.field(value, "turns", path), `${path}.turns`,
    (turn, turnPath, index) => decodeTurnIdentity(turn, index, turnPath),
  );
  decoder.unique(turns.map((turn) => turn.id), `${path}.turns`);
  if (lastTurnSequence !== turns.length) {
    throw new StudySessionDecodeError(`${path}.last_turn_sequence`, `expected_turn_count_${turns.length}`);
  }
  return { revision, lastTurnSequence, turns };
}

export function orderStudySessionTurns(
  turns: StudySessionRecord["turns"],
): StudySessionRecord["turns"] {
  return [...turns].sort((left, right) => left.sequence - right.sequence);
}
