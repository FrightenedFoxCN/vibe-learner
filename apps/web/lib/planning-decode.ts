import type {
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentRecord,
  LearningPlan,
  ModelRecovery,
  PlanGenerationRoundTrace,
  PlanGenerationTrace,
  PlanningChunkExcerpt,
  PlanningOutlineNode,
  PlanningSectionRef,
  PlanningStudyUnitContext,
  SceneObjectSnapshot,
  SceneProfile,
  SceneTreeNode,
  ScheduleChapter,
  ScheduleChapterContentSlice,
  StudyScheduleItem,
  StudyUnit,
  StudyUnitPlanningDetail,
  HarnessTraceV3,
} from "@vibe-learner/shared";

import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { decodeDocumentRecord } from "./document-decode.ts";
import { decodeHarnessTraceV3 } from "./harness-trace-decode.ts";

const STUDY_UNIT_KINDS = [
  "chapter",
  "front_matter",
  "solutions",
  "back_matter",
] as const;
const SCHEDULE_STATUSES = [
  "planned",
  "in_progress",
  "completed",
  "blocked",
  "skipped",
] as const;
const STUDY_UNIT_PROGRESS_STATUSES = [
  "planned",
  "in_progress",
  "completed",
  "blocked",
] as const;
const PLANNING_QUESTION_STATUSES = ["pending", "answered"] as const;
const ACTIVITY_TYPES = ["learn", "review"] as const;
const PLANNING_TOOL_NAMES = [
  "get_study_unit_detail",
  "ask_planning_question",
  "estimate_plan_completion",
  "revise_study_units",
  "read_page_range_content",
  "read_page_range_images",
] as const;
const MODEL_RECOVERY_SCHEMA_VERSIONS = ["model-recovery-v1"] as const;
const TOOL_ARGUMENT_CONTRACT_VERSIONS = ["", "planning-tool-arguments-v1"] as const;
const TOOL_RESULT_CONTRACT_VERSIONS = ["", "planning-tool-result-v1"] as const;

export class PlanningDecodeError extends Error {
  readonly code = "planning_response_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "PlanningDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  throw new PlanningDecodeError(path, reason);
});

function assertKnownReferences(
  refs: string[],
  allowed: ReadonlySet<string>,
  path: string,
  reason: string,
): void {
  decoder.unique(refs, path);
  for (const [index, ref] of refs.entries()) {
    if (!allowed.has(ref)) {
      throw new PlanningDecodeError(`${path}[${index}]`, reason);
    }
  }
}

function decodePlanningSection(raw: unknown, path: string): PlanningSectionRef {
  const value = decoder.record(raw, path);
  const section: PlanningSectionRef = {
    sectionId: decoder.string(
      decoder.field(value, "section_id", path),
      `${path}.section_id`,
    ),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    level: decoder.integer(decoder.field(value, "level", path), `${path}.level`, 1),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
  };
  decoder.range(section.pageStart, section.pageEnd, `${path}.page_range`);
  return section;
}

function decodeOutlineNode(raw: unknown, path: string): PlanningOutlineNode {
  const value = decoder.record(raw, path);
  const section = decodePlanningSection(raw, path);
  const children = decoder.array(
    decoder.field(value, "children", path),
    `${path}.children`,
    decodePlanningSection,
  );
  decoder.unique(children.map((child) => child.sectionId), `${path}.children.section_id`);
  decoder.nonDecreasing(children.map((child) => child.pageStart), `${path}.children.page_start`);
  for (const [index, child] of children.entries()) {
    if (
      child.level <= section.level ||
      child.pageStart < section.pageStart ||
      child.pageEnd > section.pageEnd
    ) {
      throw new PlanningDecodeError(
        `${path}.children[${index}]`,
        "child_section_outside_parent",
      );
    }
  }
  return { ...section, children };
}

function decodePlanningStudyUnit(raw: unknown, path: string): PlanningStudyUnitContext {
  const value = decoder.record(raw, path);
  const unit: PlanningStudyUnitContext = {
    unitId: decoder.string(decoder.field(value, "unit_id", path), `${path}.unit_id`),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    unitKind: decoder.enumeration(
      decoder.field(value, "unit_kind", path),
      STUDY_UNIT_KINDS,
      `${path}.unit_kind`,
    ),
    includeInPlan: decoder.boolean(
      decoder.field(value, "include_in_plan", path),
      `${path}.include_in_plan`,
    ),
    subsectionTitles: decoder.stringArray(
      decoder.field(value, "subsection_titles", path),
      `${path}.subsection_titles`,
      true,
    ),
    relatedSectionIds: decoder.stringArray(
      decoder.field(value, "related_section_ids", path),
      `${path}.related_section_ids`,
    ),
    detailToolTargetId: decoder.string(
      decoder.field(value, "detail_tool_target_id", path),
      `${path}.detail_tool_target_id`,
    ),
  };
  decoder.range(unit.pageStart, unit.pageEnd, `${path}.page_range`);
  decoder.unique(unit.relatedSectionIds, `${path}.related_section_ids`);
  decoder.equal(unit.detailToolTargetId, unit.unitId, `${path}.detail_tool_target_id`);
  return unit;
}

function decodeChunkExcerpt(raw: unknown, path: string): PlanningChunkExcerpt {
  const value = decoder.record(raw, path);
  const chunk: PlanningChunkExcerpt = {
    chunkId: decoder.string(decoder.field(value, "chunk_id", path), `${path}.chunk_id`),
    sectionId: decoder.string(
      decoder.field(value, "section_id", path),
      `${path}.section_id`,
    ),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    charCount: decoder.integer(
      decoder.field(value, "char_count", path),
      `${path}.char_count`,
    ),
    content: decoder.string(decoder.field(value, "content", path), `${path}.content`, true),
  };
  decoder.range(chunk.pageStart, chunk.pageEnd, `${path}.page_range`);
  return chunk;
}

function decodeStudyUnitDetail(raw: unknown, path: string): StudyUnitPlanningDetail {
  const value = decoder.record(raw, path);
  const relatedSections = decoder.array(
    decoder.field(value, "related_sections", path),
    `${path}.related_sections`,
    decodePlanningSection,
  );
  decoder.unique(
    relatedSections.map((section) => section.sectionId),
    `${path}.related_sections.section_id`,
  );
  decoder.nonDecreasing(
    relatedSections.map((section) => section.pageStart),
    `${path}.related_sections.page_start`,
  );
  const relatedSectionIds = decoder.stringArray(
    decoder.field(value, "related_section_ids", path),
    `${path}.related_section_ids`,
  );
  decoder.unique(relatedSectionIds, `${path}.related_section_ids`);
  if (
    relatedSectionIds.length !== relatedSections.length ||
    relatedSectionIds.some((id, index) => id !== relatedSections[index]?.sectionId)
  ) {
    throw new PlanningDecodeError(
      `${path}.related_section_ids`,
      "related_section_projection_mismatch",
    );
  }
  const chunkExcerpts = decoder.array(
    decoder.field(value, "chunk_excerpts", path),
    `${path}.chunk_excerpts`,
    decodeChunkExcerpt,
  );
  decoder.unique(chunkExcerpts.map((chunk) => chunk.chunkId), `${path}.chunk_excerpts.chunk_id`);
  decoder.nonDecreasing(
    chunkExcerpts.map((chunk) => chunk.pageStart),
    `${path}.chunk_excerpts.page_start`,
  );
  const relatedIds = new Set(relatedSectionIds);
  for (const [index, chunk] of chunkExcerpts.entries()) {
    if (!relatedIds.has(chunk.sectionId)) {
      throw new PlanningDecodeError(
        `${path}.chunk_excerpts[${index}].section_id`,
        "unknown_related_section_reference",
      );
    }
  }
  const detail: StudyUnitPlanningDetail = {
    unitId: decoder.string(decoder.field(value, "unit_id", path), `${path}.unit_id`),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    unitKind: decoder.enumeration(
      decoder.field(value, "unit_kind", path),
      STUDY_UNIT_KINDS,
      `${path}.unit_kind`,
    ),
    includeInPlan: decoder.boolean(
      decoder.field(value, "include_in_plan", path),
      `${path}.include_in_plan`,
    ),
    relatedSectionIds,
    subsectionTitles: decoder.stringArray(
      decoder.field(value, "subsection_titles", path),
      `${path}.subsection_titles`,
      true,
    ),
    relatedSections,
    chunkCount: decoder.integer(
      decoder.field(value, "chunk_count", path),
      `${path}.chunk_count`,
    ),
    chunkExcerpts,
  };
  decoder.range(detail.pageStart, detail.pageEnd, `${path}.page_range`);
  if (detail.chunkCount < detail.chunkExcerpts.length) {
    throw new PlanningDecodeError(`${path}.chunk_count`, "chunk_count_below_excerpt_count");
  }
  return detail;
}

export function decodeDocumentPlanningContext(
  raw: unknown,
  expectedDocumentId?: string,
  path = "planning_context",
): DocumentPlanningContext {
  const value = decoder.record(raw, path);
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
  );
  if (expectedDocumentId !== undefined) {
    decoder.equal(documentId, expectedDocumentId, `${path}.document_id`);
  }
  const courseOutline = decoder.array(
    decoder.field(value, "course_outline", path),
    `${path}.course_outline`,
    decodeOutlineNode,
  );
  decoder.nonDecreasing(
    courseOutline.map((section) => section.pageStart),
    `${path}.course_outline.page_start`,
  );
  const outlineIds = courseOutline.flatMap((section) => [
    section.sectionId,
    ...section.children.map((child) => child.sectionId),
  ]);
  decoder.unique(outlineIds, `${path}.course_outline.section_id`);

  const studyUnits = decoder.array(
    decoder.field(value, "study_units", path),
    `${path}.study_units`,
    decodePlanningStudyUnit,
  );
  decoder.unique(studyUnits.map((unit) => unit.unitId), `${path}.study_units.unit_id`);
  decoder.nonDecreasing(
    studyUnits.map((unit) => unit.pageStart),
    `${path}.study_units.page_start`,
  );

  const rawDetailMap = decoder.record(
    decoder.field(value, "detail_map", path),
    `${path}.detail_map`,
  );
  const detailEntries = Object.entries(rawDetailMap).map(([key, rawDetail]) => {
    if (!key) {
      throw new PlanningDecodeError(`${path}.detail_map`, "empty_detail_key");
    }
    const detail = decodeStudyUnitDetail(rawDetail, `${path}.detail_map.${key}`);
    decoder.equal(detail.unitId, key, `${path}.detail_map.${key}.unit_id`);
    return [key, detail] as const;
  });
  decoder.unique(detailEntries.map(([key]) => key), `${path}.detail_map.keys`);
  const detailMap = Object.fromEntries(detailEntries);
  const unitIds = studyUnits.map((unit) => unit.unitId);
  const detailIds = detailEntries.map(([key]) => key);
  if (
    unitIds.length !== detailIds.length ||
    unitIds.some((unitId) => !Object.prototype.hasOwnProperty.call(detailMap, unitId))
  ) {
    throw new PlanningDecodeError(`${path}.detail_map`, "study_unit_detail_set_mismatch");
  }
  for (const [index, unit] of studyUnits.entries()) {
    const detail = detailMap[unit.unitId];
    if (
      !detail ||
      detail.title !== unit.title ||
      detail.pageStart !== unit.pageStart ||
      detail.pageEnd !== unit.pageEnd ||
      detail.summary !== unit.summary ||
      detail.unitKind !== unit.unitKind ||
      detail.includeInPlan !== unit.includeInPlan ||
      detail.relatedSectionIds.length !== unit.relatedSectionIds.length ||
      detail.relatedSectionIds.some((id, refIndex) => id !== unit.relatedSectionIds[refIndex]) ||
      detail.subsectionTitles.length !== unit.subsectionTitles.length ||
      detail.subsectionTitles.some((title, titleIndex) => title !== unit.subsectionTitles[titleIndex])
    ) {
      throw new PlanningDecodeError(
        `${path}.study_units[${index}]`,
        "study_unit_detail_projection_mismatch",
      );
    }
  }

  const availableTools = decoder.array(
    decoder.field(value, "available_tools", path),
    `${path}.available_tools`,
    (item, itemPath) => {
      const tool = decoder.record(item, itemPath);
      return {
        name: decoder.enumeration(
          decoder.field(tool, "name", itemPath),
          PLANNING_TOOL_NAMES,
          `${itemPath}.name`,
        ),
        description: decoder.string(
          decoder.field(tool, "description", itemPath),
          `${itemPath}.description`,
          true,
        ),
      };
    },
  );
  decoder.unique(availableTools.map((tool) => tool.name), `${path}.available_tools.name`);
  return { documentId, courseOutline, studyUnits, detailMap, availableTools };
}

function decodePlanStudyUnit(
  raw: unknown,
  path: string,
): StudyUnit {
  const value = decoder.record(raw, path);
  const unit: StudyUnit = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    documentId: decoder.string(
      decoder.field(value, "document_id", path),
      `${path}.document_id`,
      true,
    ),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    unitKind: decoder.enumeration(
      decoder.field(value, "unit_kind", path),
      STUDY_UNIT_KINDS,
      `${path}.unit_kind`,
    ),
    includeInPlan: decoder.boolean(
      decoder.field(value, "include_in_plan", path),
      `${path}.include_in_plan`,
    ),
    sourceSectionIds: decoder.stringArray(
      decoder.field(value, "source_section_ids", path),
      `${path}.source_section_ids`,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    confidence: decoder.finiteNumber(
      decoder.field(value, "confidence", path),
      `${path}.confidence`,
      0,
      1,
    ),
  };
  decoder.range(unit.pageStart, unit.pageEnd, `${path}.page_range`);
  decoder.unique(unit.sourceSectionIds, `${path}.source_section_ids`);
  return unit;
}

function validatePlanStudyUnitIdentity(
  studyUnits: StudyUnit[],
  creationMode: "document" | "goal_only",
  documentId: string,
  path: string,
): void {
  if (creationMode === "document") {
    for (const [index, unit] of studyUnits.entries()) {
      decoder.equal(unit.documentId, documentId, `${path}[${index}].document_id`);
    }
    return;
  }

  if (studyUnits.length === 0) return;
  const syntheticDocumentId = studyUnits[0]?.documentId ?? "";
  if (!/^goal-only:[^:\s]+$/.test(syntheticDocumentId)) {
    throw new PlanningDecodeError(
      `${path}[0].document_id`,
      "invalid_goal_only_study_unit_scope",
    );
  }
  for (const [index, unit] of studyUnits.entries()) {
    decoder.equal(
      unit.documentId,
      syntheticDocumentId,
      `${path}[${index}].document_id`,
    );
    if (!unit.id.startsWith(`${syntheticDocumentId}:study-unit:`)) {
      throw new PlanningDecodeError(
        `${path}[${index}].id`,
        "goal_only_study_unit_scope_mismatch",
      );
    }
  }
}

function decodeContentSlice(
  raw: unknown,
  path: string,
  chapterStart: number,
  chapterEnd: number,
  allowedSectionIds: ReadonlySet<string>,
): ScheduleChapterContentSlice {
  const value = decoder.record(raw, path);
  const slice: ScheduleChapterContentSlice = {
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    sourceSectionIds: decoder.stringArray(
      decoder.field(value, "source_section_ids", path),
      `${path}.source_section_ids`,
    ),
  };
  decoder.range(slice.pageStart, slice.pageEnd, `${path}.page_range`);
  if (slice.pageStart < chapterStart || slice.pageEnd > chapterEnd) {
    throw new PlanningDecodeError(path, "content_slice_outside_chapter");
  }
  assertKnownReferences(
    slice.sourceSectionIds,
    allowedSectionIds,
    `${path}.source_section_ids`,
    "unknown_study_unit_section_reference",
  );
  return slice;
}

function decodeScheduleChapter(
  raw: unknown,
  path: string,
  unit: StudyUnit,
): ScheduleChapter {
  const value = decoder.record(raw, path);
  const anchorPageStart = decoder.integer(
    decoder.field(value, "anchor_page_start", path),
    `${path}.anchor_page_start`,
    1,
  );
  const anchorPageEnd = decoder.integer(
    decoder.field(value, "anchor_page_end", path),
    `${path}.anchor_page_end`,
    1,
  );
  decoder.range(anchorPageStart, anchorPageEnd, `${path}.anchor_page_range`);
  if (anchorPageStart < unit.pageStart || anchorPageEnd > unit.pageEnd) {
    throw new PlanningDecodeError(path, "schedule_chapter_outside_study_unit");
  }
  const allowedSectionIds = new Set(unit.sourceSectionIds);
  const sourceSectionIds = decoder.stringArray(
    decoder.field(value, "source_section_ids", path),
    `${path}.source_section_ids`,
  );
  assertKnownReferences(
    sourceSectionIds,
    allowedSectionIds,
    `${path}.source_section_ids`,
    "unknown_study_unit_section_reference",
  );
  const contentSlices = decoder.array(
    decoder.field(value, "content_slices", path),
    `${path}.content_slices`,
    (item, itemPath) =>
      decodeContentSlice(item, itemPath, anchorPageStart, anchorPageEnd, allowedSectionIds),
  );
  if (contentSlices.length === 0) {
    throw new PlanningDecodeError(`${path}.content_slices`, "expected_non_empty_array");
  }
  decoder.nonDecreasing(
    contentSlices.map((slice) => slice.pageStart),
    `${path}.content_slices.page_start`,
  );
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    anchorPageStart,
    anchorPageEnd,
    sourceSectionIds,
    contentSlices,
  };
}

function decodeScheduleItem(
  raw: unknown,
  path: string,
  unitMap: ReadonlyMap<string, StudyUnit>,
): StudyScheduleItem {
  const value = decoder.record(raw, path);
  const unitId = decoder.string(decoder.field(value, "unit_id", path), `${path}.unit_id`);
  const unit = unitMap.get(unitId);
  if (!unit) {
    throw new PlanningDecodeError(`${path}.unit_id`, "unknown_study_unit_reference");
  }
  if (!unit.includeInPlan) {
    throw new PlanningDecodeError(`${path}.unit_id`, "excluded_study_unit_reference");
  }
  const scheduleChapters = decoder.array(
    decoder.field(value, "schedule_chapters", path),
    `${path}.schedule_chapters`,
    (item, itemPath) => decodeScheduleChapter(item, itemPath, unit),
  );
  if (scheduleChapters.length === 0) {
    throw new PlanningDecodeError(`${path}.schedule_chapters`, "expected_non_empty_array");
  }
  decoder.unique(scheduleChapters.map((chapter) => chapter.id), `${path}.schedule_chapters.id`);
  decoder.nonDecreasing(
    scheduleChapters.map((chapter) => chapter.anchorPageStart),
    `${path}.schedule_chapters.anchor_page_start`,
  );
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    unitId,
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    focus: decoder.string(decoder.field(value, "focus", path), `${path}.focus`, true),
    activityType: decoder.enumeration(
      decoder.field(value, "activity_type", path),
      ACTIVITY_TYPES,
      `${path}.activity_type`,
    ),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      SCHEDULE_STATUSES,
      `${path}.status`,
    ),
    scheduleChapters,
  };
}

interface SceneDecodeState {
  layerIds: Set<string>;
  objectIds: Set<string>;
  layerCount: number;
  objectCount: number;
}

function decodeSceneObject(
  raw: unknown,
  path: string,
  state: SceneDecodeState,
): SceneObjectSnapshot {
  const value = decoder.record(raw, path);
  const id = decoder.string(decoder.field(value, "id", path), `${path}.id`);
  if (state.objectIds.has(id)) {
    throw new PlanningDecodeError(`${path}.id`, "duplicate_scene_object_id");
  }
  state.objectIds.add(id);
  state.objectCount += 1;
  if (state.objectCount > 128) {
    throw new PlanningDecodeError(path, "scene_object_budget_exceeded");
  }
  return {
    id,
    name: decoder.string(decoder.field(value, "name", path), `${path}.name`, true),
    description: decoder.string(
      decoder.field(value, "description", path),
      `${path}.description`,
      true,
    ),
    interaction: decoder.string(
      decoder.field(value, "interaction", path),
      `${path}.interaction`,
      true,
    ),
    tags: decoder.string(decoder.field(value, "tags", path), `${path}.tags`, true),
    reuseId: decoder.string(decoder.field(value, "reuse_id", path), `${path}.reuse_id`, true),
    reuseHint: decoder.string(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      true,
    ),
  };
}

function decodeSceneNode(
  raw: unknown,
  path: string,
  state: SceneDecodeState,
  depth: number,
): SceneTreeNode {
  if (depth > 8) {
    throw new PlanningDecodeError(path, "scene_depth_budget_exceeded");
  }
  const value = decoder.record(raw, path);
  const id = decoder.string(decoder.field(value, "id", path), `${path}.id`);
  if (state.layerIds.has(id)) {
    throw new PlanningDecodeError(`${path}.id`, "duplicate_scene_layer_id");
  }
  state.layerIds.add(id);
  state.layerCount += 1;
  if (state.layerCount > 64) {
    throw new PlanningDecodeError(path, "scene_layer_budget_exceeded");
  }
  return {
    id,
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    scopeLabel: decoder.string(
      decoder.field(value, "scope_label", path),
      `${path}.scope_label`,
      true,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    atmosphere: decoder.string(
      decoder.field(value, "atmosphere", path),
      `${path}.atmosphere`,
      true,
    ),
    rules: decoder.string(decoder.field(value, "rules", path), `${path}.rules`, true),
    entrance: decoder.string(decoder.field(value, "entrance", path), `${path}.entrance`, true),
    tags: decoder.string(decoder.field(value, "tags", path), `${path}.tags`, true),
    reuseId: decoder.string(decoder.field(value, "reuse_id", path), `${path}.reuse_id`, true),
    reuseHint: decoder.string(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      true,
    ),
    objects: decoder.array(
      decoder.field(value, "objects", path),
      `${path}.objects`,
      (item, itemPath) => decodeSceneObject(item, itemPath, state),
    ),
    children: decoder.array(
      decoder.field(value, "children", path),
      `${path}.children`,
      (item, itemPath) => decodeSceneNode(item, itemPath, state, depth + 1),
    ),
  };
}

function resolveSelectedScenePath(tree: SceneTreeNode[], selectedPath: string[]): boolean {
  if (selectedPath.length === 0) return tree.length === 0;
  let nodes = tree;
  for (const title of selectedPath) {
    const node = nodes.find((candidate) => candidate.title === title);
    if (!node) return false;
    nodes = node.children;
  }
  return true;
}

function decodeSceneProfile(raw: unknown, path: string): SceneProfile {
  const value = decoder.record(raw, path);
  const state: SceneDecodeState = {
    layerIds: new Set(),
    objectIds: new Set(),
    layerCount: 0,
    objectCount: 0,
  };
  const sceneTree = decoder.array(
    decoder.field(value, "scene_tree", path),
    `${path}.scene_tree`,
    (item, itemPath) => decodeSceneNode(item, itemPath, state, 1),
  );
  const selectedPath = decoder.stringArray(
    decoder.field(value, "selected_path", path),
    `${path}.selected_path`,
  );
  if (sceneTree.length > 0 && !resolveSelectedScenePath(sceneTree, selectedPath)) {
    throw new PlanningDecodeError(`${path}.selected_path`, "invalid_scene_selected_path");
  }
  return {
    sceneName: decoder.string(
      decoder.field(value, "scene_name", path),
      `${path}.scene_name`,
      true,
    ),
    sceneId: decoder.string(decoder.field(value, "scene_id", path), `${path}.scene_id`),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    tags: decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`, true),
    selectedPath,
    focusObjectNames: decoder.stringArray(
      decoder.field(value, "focus_object_names", path),
      `${path}.focus_object_names`,
      true,
    ),
    sceneTree,
  };
}

function validateCompletionPercent(
  completionPercent: number,
  completed: number,
  total: number,
  path: string,
): void {
  const exact = total === 0 ? 0 : (completed / total) * 100;
  if (Math.abs(completionPercent - exact) > 0.5000001) {
    throw new PlanningDecodeError(path, "completion_percent_projection_mismatch");
  }
}

export interface LearningPlanDecodeOptions {
  expectedPlanId?: string;
  expectedDocumentId?: string;
  path?: string;
  requireHarnessTrace?: boolean;
}

export function decodeLearningPlan(
  raw: unknown,
  options: LearningPlanDecodeOptions = {},
): LearningPlan {
  const path = options.path ?? "learning_plan";
  const value = decoder.record(raw, path);
  let harnessTrace: HarnessTraceV3 | undefined;
  const rawHarnessTrace = value.harness_trace;
  if (
    options.requireHarnessTrace ||
    (rawHarnessTrace !== undefined && rawHarnessTrace !== null)
  ) {
    const decodedTrace = decodeHarnessTraceV3(
      decoder.field(value, "harness_trace", path),
      `${path}.harness_trace`,
      (tracePath, reason) => { throw new PlanningDecodeError(tracePath, reason); },
    );
    if (decodedTrace.workflow !== "planning" || decodedTrace.stage !== "plan_generation" || !["passed", "repaired"].includes(decodedTrace.status) || decodedTrace.commitEvidence.status !== "committed") {
      throw new PlanningDecodeError(
        `${path}.harness_trace`,
        "learning_plan_harness_trace_invalid",
      );
    }
    harnessTrace = decodedTrace;
  }
  const id = decoder.string(decoder.field(value, "id", path), `${path}.id`);
  if (options.expectedPlanId !== undefined) {
    decoder.equal(id, options.expectedPlanId, `${path}.id`);
  }
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
    true,
  );
  if (options.expectedDocumentId !== undefined) {
    decoder.equal(documentId, options.expectedDocumentId, `${path}.document_id`);
  }
  const creationMode = decoder.enumeration(
    decoder.field(value, "creation_mode", path),
    ["document", "goal_only"] as const,
    `${path}.creation_mode`,
  );
  if ((creationMode === "document") !== Boolean(documentId)) {
    throw new PlanningDecodeError(`${path}.document_id`, "creation_mode_document_identity_mismatch");
  }
  const studyUnits = decoder.array(
    decoder.field(value, "study_units", path),
    `${path}.study_units`,
    (item, itemPath) => decodePlanStudyUnit(item, itemPath),
  );
  validatePlanStudyUnitIdentity(
    studyUnits,
    creationMode,
    documentId,
    `${path}.study_units`,
  );
  decoder.unique(studyUnits.map((unit) => unit.id), `${path}.study_units.id`);
  decoder.nonDecreasing(studyUnits.map((unit) => unit.pageStart), `${path}.study_units.page_start`);
  const unitMap = new Map(studyUnits.map((unit) => [unit.id, unit]));
  const schedule = decoder.array(
    decoder.field(value, "schedule", path),
    `${path}.schedule`,
    (item, itemPath) => decodeScheduleItem(item, itemPath, unitMap),
  );
  decoder.unique(schedule.map((item) => item.id), `${path}.schedule.id`);
  decoder.unique(schedule.map((item) => item.unitId), `${path}.schedule.unit_id`);
  decoder.unique(
    schedule.flatMap((item) => item.scheduleChapters.map((chapter) => chapter.id)),
    `${path}.schedule.schedule_chapters.id`,
  );
  const scheduleMap = new Map(schedule.map((item) => [item.id, item]));

  const progressSummaryValue = decoder.record(
    decoder.field(value, "progress_summary", path),
    `${path}.progress_summary`,
  );
  const progressSummary = {
    totalScheduleCount: decoder.integer(
      decoder.field(progressSummaryValue, "total_schedule_count", `${path}.progress_summary`),
      `${path}.progress_summary.total_schedule_count`,
    ),
    completedScheduleCount: decoder.integer(
      decoder.field(progressSummaryValue, "completed_schedule_count", `${path}.progress_summary`),
      `${path}.progress_summary.completed_schedule_count`,
    ),
    inProgressScheduleCount: decoder.integer(
      decoder.field(progressSummaryValue, "in_progress_schedule_count", `${path}.progress_summary`),
      `${path}.progress_summary.in_progress_schedule_count`,
    ),
    pendingScheduleCount: decoder.integer(
      decoder.field(progressSummaryValue, "pending_schedule_count", `${path}.progress_summary`),
      `${path}.progress_summary.pending_schedule_count`,
    ),
    blockedScheduleCount: decoder.integer(
      decoder.field(progressSummaryValue, "blocked_schedule_count", `${path}.progress_summary`),
      `${path}.progress_summary.blocked_schedule_count`,
    ),
    completionPercent: decoder.integer(
      decoder.field(progressSummaryValue, "completion_percent", `${path}.progress_summary`),
      `${path}.progress_summary.completion_percent`,
      0,
      100,
    ),
  };
  const completedScheduleCount = schedule.filter((item) => item.status === "completed").length;
  const inProgressScheduleCount = schedule.filter((item) => item.status === "in_progress").length;
  const blockedScheduleCount = schedule.filter((item) => item.status === "blocked").length;
  const pendingScheduleCount =
    schedule.length - completedScheduleCount - inProgressScheduleCount - blockedScheduleCount;
  if (
    progressSummary.totalScheduleCount !== schedule.length ||
    progressSummary.completedScheduleCount !== completedScheduleCount ||
    progressSummary.inProgressScheduleCount !== inProgressScheduleCount ||
    progressSummary.pendingScheduleCount !== pendingScheduleCount ||
    progressSummary.blockedScheduleCount !== blockedScheduleCount
  ) {
    throw new PlanningDecodeError(`${path}.progress_summary`, "schedule_count_projection_mismatch");
  }
  validateCompletionPercent(
    progressSummary.completionPercent,
    completedScheduleCount,
    schedule.length,
    `${path}.progress_summary.completion_percent`,
  );

  const studyUnitProgress = decoder.array(
    decoder.field(value, "study_unit_progress", path),
    `${path}.study_unit_progress`,
    (item, itemPath) => {
      const progress = decoder.record(item, itemPath);
      const unitId = decoder.string(
        decoder.field(progress, "unit_id", itemPath),
        `${itemPath}.unit_id`,
      );
      if (!unitMap.has(unitId)) {
        throw new PlanningDecodeError(`${itemPath}.unit_id`, "unknown_study_unit_reference");
      }
      const scheduleIds = decoder.stringArray(
        decoder.field(progress, "schedule_ids", itemPath),
        `${itemPath}.schedule_ids`,
      );
      assertKnownReferences(
        scheduleIds,
        new Set(scheduleMap.keys()),
        `${itemPath}.schedule_ids`,
        "unknown_schedule_reference",
      );
      if (scheduleIds.some((scheduleId) => scheduleMap.get(scheduleId)?.unitId !== unitId)) {
        throw new PlanningDecodeError(`${itemPath}.schedule_ids`, "cross_study_unit_schedule_reference");
      }
      const totalScheduleCount = decoder.integer(
        decoder.field(progress, "total_schedule_count", itemPath),
        `${itemPath}.total_schedule_count`,
      );
      const completedCount = decoder.integer(
        decoder.field(progress, "completed_schedule_count", itemPath),
        `${itemPath}.completed_schedule_count`,
      );
      const inProgressCount = decoder.integer(
        decoder.field(progress, "in_progress_schedule_count", itemPath),
        `${itemPath}.in_progress_schedule_count`,
      );
      const pendingCount = decoder.integer(
        decoder.field(progress, "pending_schedule_count", itemPath),
        `${itemPath}.pending_schedule_count`,
      );
      const blockedCount = decoder.integer(
        decoder.field(progress, "blocked_schedule_count", itemPath),
        `${itemPath}.blocked_schedule_count`,
      );
      const completionPercent = decoder.integer(
        decoder.field(progress, "completion_percent", itemPath),
        `${itemPath}.completion_percent`,
        0,
        100,
      );
      const relatedSchedule = scheduleIds.map((scheduleId) => scheduleMap.get(scheduleId)!);
      const projectedCompleted = relatedSchedule.filter((entry) => entry.status === "completed").length;
      const projectedInProgress = relatedSchedule.filter((entry) => entry.status === "in_progress").length;
      const projectedBlocked = relatedSchedule.filter((entry) => entry.status === "blocked").length;
      const projectedPending =
        relatedSchedule.length - projectedCompleted - projectedInProgress - projectedBlocked;
      if (
        totalScheduleCount !== relatedSchedule.length ||
        completedCount !== projectedCompleted ||
        inProgressCount !== projectedInProgress ||
        pendingCount !== projectedPending ||
        blockedCount !== projectedBlocked
      ) {
        throw new PlanningDecodeError(itemPath, "study_unit_progress_count_mismatch");
      }
      validateCompletionPercent(
        completionPercent,
        completedCount,
        totalScheduleCount,
        `${itemPath}.completion_percent`,
      );
      const status = decoder.enumeration(
        decoder.field(progress, "status", itemPath),
        STUDY_UNIT_PROGRESS_STATUSES,
        `${itemPath}.status`,
      );
      const expectedStatus = totalScheduleCount > 0 && completedCount === totalScheduleCount
        ? "completed"
        : inProgressCount > 0 || completedCount > 0
          ? "in_progress"
          : blockedCount > 0 && pendingCount === 0
            ? "blocked"
            : "planned";
      decoder.equal(status, expectedStatus, `${itemPath}.status`);
      return {
        unitId,
        title: decoder.string(decoder.field(progress, "title", itemPath), `${itemPath}.title`, true),
        objectiveFragment: decoder.string(
          decoder.field(progress, "objective_fragment", itemPath),
          `${itemPath}.objective_fragment`,
          true,
        ),
        scheduleIds,
        totalScheduleCount,
        completedScheduleCount: completedCount,
        inProgressScheduleCount: inProgressCount,
        pendingScheduleCount: pendingCount,
        blockedScheduleCount: blockedCount,
        completionPercent,
        status,
      };
    },
  );
  decoder.unique(studyUnitProgress.map((entry) => entry.unitId), `${path}.study_unit_progress.unit_id`);
  const expectedProgressUnits = studyUnits.filter((unit) => unit.includeInPlan);
  const projectedProgressUnits = expectedProgressUnits.length > 0 ? expectedProgressUnits : studyUnits;
  if (
    studyUnitProgress.length !== projectedProgressUnits.length ||
    studyUnitProgress.some((entry, index) => entry.unitId !== projectedProgressUnits[index]?.id)
  ) {
    throw new PlanningDecodeError(
      `${path}.study_unit_progress`,
      "study_unit_progress_projection_mismatch",
    );
  }

  const progressEvents = decoder.array(
    decoder.field(value, "progress_events", path),
    `${path}.progress_events`,
    (item, itemPath) => {
      const event = decoder.record(item, itemPath);
      const scheduleIds = decoder.stringArray(
        decoder.field(event, "schedule_ids", itemPath),
        `${itemPath}.schedule_ids`,
      );
      assertKnownReferences(
        scheduleIds,
        new Set(scheduleMap.keys()),
        `${itemPath}.schedule_ids`,
        "unknown_schedule_reference",
      );
      return {
        id: decoder.string(decoder.field(event, "id", itemPath), `${itemPath}.id`),
        actor: decoder.string(decoder.field(event, "actor", itemPath), `${itemPath}.actor`),
        source: decoder.string(decoder.field(event, "source", itemPath), `${itemPath}.source`),
        scheduleIds,
        status: decoder.enumeration(
          decoder.field(event, "status", itemPath),
          SCHEDULE_STATUSES,
          `${itemPath}.status`,
        ),
        note: decoder.string(decoder.field(event, "note", itemPath), `${itemPath}.note`, true),
        createdAt: decoder.string(
          decoder.field(event, "created_at", itemPath),
          `${itemPath}.created_at`,
        ),
      };
    },
  );
  decoder.unique(progressEvents.map((event) => event.id), `${path}.progress_events.id`);

  const planningQuestions = decoder.array(
    decoder.field(value, "planning_questions", path),
    `${path}.planning_questions`,
    (item, itemPath) => {
      const question = decoder.record(item, itemPath);
      const status = decoder.enumeration(
        decoder.field(question, "status", itemPath),
        PLANNING_QUESTION_STATUSES,
        `${itemPath}.status`,
      );
      const answeredAt = decoder.string(
        decoder.field(question, "answered_at", itemPath),
        `${itemPath}.answered_at`,
        true,
      );
      if ((status === "answered") !== Boolean(answeredAt)) {
        throw new PlanningDecodeError(`${itemPath}.answered_at`, "question_status_time_mismatch");
      }
      return {
        id: decoder.string(decoder.field(question, "id", itemPath), `${itemPath}.id`),
        question: decoder.string(
          decoder.field(question, "question", itemPath),
          `${itemPath}.question`,
        ),
        reason: decoder.string(decoder.field(question, "reason", itemPath), `${itemPath}.reason`, true),
        assumptions: decoder.stringArray(
          decoder.field(question, "assumptions", itemPath),
          `${itemPath}.assumptions`,
          true,
        ),
        answer: decoder.string(decoder.field(question, "answer", itemPath), `${itemPath}.answer`, true),
        status,
        sourceToolName: decoder.enumeration(
          decoder.field(question, "source_tool_name", itemPath),
          ["ask_planning_question"] as const,
          `${itemPath}.source_tool_name`,
        ),
        createdAt: decoder.string(
          decoder.field(question, "created_at", itemPath),
          `${itemPath}.created_at`,
        ),
        answeredAt,
      };
    },
  );
  decoder.unique(planningQuestions.map((question) => question.id), `${path}.planning_questions.id`);

  const rawSceneProfile = decoder.field(value, "scene_profile", path);
  const sceneProfile = decoder.nullable(
    rawSceneProfile,
    `${path}.scene_profile`,
    decodeSceneProfile,
  );
  return {
    id,
    documentId,
    personaId: decoder.string(
      decoder.field(value, "persona_id", path),
      `${path}.persona_id`,
    ),
    creationMode,
    courseTitle: decoder.string(
      decoder.field(value, "course_title", path),
      `${path}.course_title`,
    ),
    objective: decoder.string(decoder.field(value, "objective", path), `${path}.objective`),
    sceneProfileSummary: decoder.string(
      decoder.field(value, "scene_profile_summary", path),
      `${path}.scene_profile_summary`,
      true,
    ),
    ...(sceneProfile === null ? {} : { sceneProfile }),
    overview: decoder.string(decoder.field(value, "overview", path), `${path}.overview`),
    todayTasks: decoder.stringArray(
      decoder.field(value, "today_tasks", path),
      `${path}.today_tasks`,
    ),
    studyUnits,
    schedule,
    progressSummary,
    studyUnitProgress,
    progressEvents,
    planningQuestions,
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    ...(harnessTrace ? { harnessTrace } : {}),
  };
}

export function decodeLearningPlanList(raw: unknown): LearningPlan[] {
  const path = "learning_plans";
  const value = decoder.record(raw, path);
  const plans = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodeLearningPlan(item, { path: itemPath }),
  );
  decoder.unique(plans.map((plan) => plan.id), `${path}.items.id`);
  return plans;
}

export function decodeDocumentStudyUnitUpdate(
  raw: unknown,
  expectedDocumentId: string,
): { document: DocumentRecord; plans: LearningPlan[] } {
  const path = "document_study_unit_update";
  const value = decoder.record(raw, path);
  const document = decodeDocumentRecord(
    decoder.field(value, "document", path),
    expectedDocumentId,
    `${path}.document`,
  );
  const plans = decoder.array(
    decoder.field(value, "plans", path),
    `${path}.plans`,
    (item, itemPath) =>
      decodeLearningPlan(item, {
        expectedDocumentId,
        path: itemPath,
      }),
  );
  decoder.unique(plans.map((plan) => plan.id), `${path}.plans.id`);
  return { document, plans };
}

function decodeModelRecovery(raw: unknown, path: string): ModelRecovery {
  const value = decoder.record(raw, path);
  let schemaVersion: "model-recovery-v1" | undefined;
  if (Object.prototype.hasOwnProperty.call(value, "schema_version")) {
    schemaVersion = decoder.enumeration(
      decoder.field(value, "schema_version", path),
      MODEL_RECOVERY_SCHEMA_VERSIONS,
      `${path}.schema_version`,
    );
  }
  return {
    ...(schemaVersion === undefined ? {} : { schemaVersion }),
    recoveryId: decoder.string(
      decoder.field(value, "recovery_id", path),
      `${path}.recovery_id`,
    ),
    category: decoder.string(decoder.field(value, "category", path), `${path}.category`),
    reason: decoder.string(decoder.field(value, "reason", path), `${path}.reason`),
    strategy: decoder.string(decoder.field(value, "strategy", path), `${path}.strategy`),
    attempts: decoder.integer(decoder.field(value, "attempts", path), `${path}.attempts`, 1),
    note: decoder.string(decoder.field(value, "note", path), `${path}.note`, true),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
  };
}

function decodePlanRound(raw: unknown, path: string, expectedIndex: number): PlanGenerationRoundTrace {
  const value = decoder.record(raw, path);
  const roundIndex = decoder.integer(
    decoder.field(value, "round_index", path),
    `${path}.round_index`,
  );
  decoder.equal(roundIndex, expectedIndex, `${path}.round_index`);
  const toolCalls = decoder.array(
    decoder.field(value, "tool_calls", path),
    `${path}.tool_calls`,
    (item, itemPath) => {
      const toolCall = decoder.record(item, itemPath);
      return {
        toolCallId: decoder.string(
          decoder.field(toolCall, "tool_call_id", itemPath),
          `${itemPath}.tool_call_id`,
        ),
        toolName: decoder.enumeration(
          decoder.field(toolCall, "tool_name", itemPath),
          PLANNING_TOOL_NAMES,
          `${itemPath}.tool_name`,
        ),
        argumentsJson: decoder.string(
          decoder.field(toolCall, "arguments_json", itemPath),
          `${itemPath}.arguments_json`,
          true,
        ),
        argumentContractVersion: decoder.enumeration(
          decoder.field(toolCall, "argument_contract_version", itemPath),
          TOOL_ARGUMENT_CONTRACT_VERSIONS,
          `${itemPath}.argument_contract_version`,
        ),
        resultContractVersion: decoder.enumeration(
          decoder.field(toolCall, "result_contract_version", itemPath),
          TOOL_RESULT_CONTRACT_VERSIONS,
          `${itemPath}.result_contract_version`,
        ),
        resultSummary: decoder.string(
          decoder.field(toolCall, "result_summary", itemPath),
          `${itemPath}.result_summary`,
          true,
        ),
        resultJson: decoder.string(
          decoder.field(toolCall, "result_json", itemPath),
          `${itemPath}.result_json`,
          true,
        ),
      };
    },
  );
  decoder.unique(toolCalls.map((toolCall) => toolCall.toolCallId), `${path}.tool_calls.tool_call_id`);
  const recoveries = decoder.array(
    decoder.field(value, "recoveries", path),
    `${path}.recoveries`,
    decodeModelRecovery,
  );
  decoder.unique(recoveries.map((recovery) => recovery.recoveryId), `${path}.recoveries.recovery_id`);
  return {
    roundIndex,
    finishReason: decoder.string(
      decoder.field(value, "finish_reason", path),
      `${path}.finish_reason`,
      true,
    ),
    assistantContent: decoder.string(
      decoder.field(value, "assistant_content", path),
      `${path}.assistant_content`,
      true,
    ),
    thinking: decoder.string(decoder.field(value, "thinking", path), `${path}.thinking`, true),
    elapsedMs: decoder.integer(
      decoder.field(value, "elapsed_ms", path),
      `${path}.elapsed_ms`,
    ),
    timeoutSeconds: decoder.integer(
      decoder.field(value, "timeout_seconds", path),
      `${path}.timeout_seconds`,
    ),
    toolCalls,
    recoveries,
  };
}

function decodePlanTrace(
  raw: unknown,
  path: string,
  expectedDocumentId: string,
): PlanGenerationTrace {
  const value = decoder.record(raw, path);
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
  );
  decoder.equal(documentId, expectedDocumentId, `${path}.document_id`);
  const planId = decoder.nullable(
    decoder.field(value, "plan_id", path),
    `${path}.plan_id`,
    (item, itemPath) => decoder.string(item, itemPath),
  );
  const rounds = decoder.array(
    decoder.field(value, "rounds", path),
    `${path}.rounds`,
    (item, itemPath, index) => decodePlanRound(item, itemPath, index),
  );
  decoder.unique(
    rounds.flatMap((round) => round.toolCalls.map((toolCall) => toolCall.toolCallId)),
    `${path}.rounds.tool_calls.tool_call_id`,
  );
  decoder.unique(
    rounds.flatMap((round) => round.recoveries.map((recovery) => recovery.recoveryId)),
    `${path}.rounds.recoveries.recovery_id`,
  );
  return {
    documentId,
    planId,
    model: decoder.string(decoder.field(value, "model", path), `${path}.model`),
    createdAt: decoder.string(decoder.field(value, "created_at", path), `${path}.created_at`),
    rounds,
  };
}

export function decodeDocumentPlanningTraceResponse(
  raw: unknown,
  expectedDocumentId?: string,
  path = "planning_trace",
): DocumentPlanningTraceResponse {
  const value = decoder.record(raw, path);
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
  );
  if (expectedDocumentId !== undefined) {
    decoder.equal(documentId, expectedDocumentId, `${path}.document_id`);
  }
  const hasTrace = decoder.boolean(
    decoder.field(value, "has_trace", path),
    `${path}.has_trace`,
  );
  const summaryValue = decoder.record(
    decoder.field(value, "summary", path),
    `${path}.summary`,
  );
  const summary = {
    roundCount: decoder.integer(
      decoder.field(summaryValue, "round_count", `${path}.summary`),
      `${path}.summary.round_count`,
    ),
    toolCallCount: decoder.integer(
      decoder.field(summaryValue, "tool_call_count", `${path}.summary`),
      `${path}.summary.tool_call_count`,
    ),
    latestFinishReason: decoder.string(
      decoder.field(summaryValue, "latest_finish_reason", `${path}.summary`),
      `${path}.summary.latest_finish_reason`,
      true,
    ),
  };
  const trace = decoder.nullable(
    decoder.field(value, "trace", path),
    `${path}.trace`,
    (item, itemPath) => decodePlanTrace(item, itemPath, documentId),
  );
  if (hasTrace !== (trace !== null)) {
    throw new PlanningDecodeError(`${path}.trace`, "has_trace_projection_mismatch");
  }
  const expectedRoundCount = trace?.rounds.length ?? 0;
  const expectedToolCallCount = trace?.rounds.reduce(
    (total, round) => total + round.toolCalls.length,
    0,
  ) ?? 0;
  const expectedFinishReason = trace?.rounds.at(-1)?.finishReason ?? "";
  if (
    summary.roundCount !== expectedRoundCount ||
    summary.toolCallCount !== expectedToolCallCount ||
    summary.latestFinishReason !== expectedFinishReason
  ) {
    throw new PlanningDecodeError(`${path}.summary`, "trace_summary_projection_mismatch");
  }
  return { documentId, hasTrace, summary, trace };
}
