import type { PlanRevision, PlanRevisionProposal } from "@vibe-learner/shared";
import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { decodeLearningPlan, PlanningDecodeError } from "./planning-decode.ts";

const fail = (path: string, reason: string): never => { throw new PlanningDecodeError(path, reason); };
const d = new StrictResponseDecoder(fail);
function exact(value: Record<string, unknown>, keys: string[], path: string) {
  for (const key of Object.keys(value)) if (!keys.includes(key)) fail(`${path}.${key}`, "unexpected_field");
  for (const key of keys) d.field(value, key, path);
}

function boundedString(raw: unknown, path: string, maximum: number, allowEmpty = false) {
  const value = d.string(raw, path, allowEmpty);
  if (Array.from(value).length > maximum) fail(path, "string_too_long");
  return value;
}
export interface PlanRevisionAdmission {
  baseRevision: number;
  instruction?: string;
  rollbackRevision?: number;
}
export function decodePlanRevision(raw: unknown, planId: string, requestId: string, admission?: PlanRevisionAdmission): PlanRevision {
  const p = "plan_revision";
  const v = d.record(raw, p);
  exact(v, ["operation_id", "client_request_id", "plan_id", "base_revision", "status", "instruction", "rollback_revision", "proposal", "base_plan", "result", "error_code"], p);
  if (v.plan_id !== planId || v.client_request_id !== requestId) fail(p, "identity_mismatch");
  const operationId = d.string(v.operation_id, `${p}.operation_id`);
  if (!/^plan-revision-[a-f0-9]{32}$/.test(operationId)) fail(p, "invalid_operation_id");
  const baseRevision = d.integer(v.base_revision, `${p}.base_revision`);
  const instruction = boundedString(v.instruction, `${p}.instruction`, 8000, true);
  const rollbackRevision = d.nullable(v.rollback_revision, `${p}.rollback_revision`, value => d.integer(value, `${p}.rollback_revision`));
  if (rollbackRevision === null ? !instruction.trim() : instruction !== "") fail(p, "invalid_action");
  if (admission && (baseRevision !== admission.baseRevision || instruction !== (admission.instruction ?? "")
    || rollbackRevision !== (admission.rollbackRevision ?? null))) fail(p, "admission_mismatch");
  const baseRaw = d.record(v.base_plan, `${p}.base_plan`);
  if (baseRaw.revision !== baseRevision) fail(p, "base_revision_mismatch");
  const basePlan = decodeLearningPlan(baseRaw, { expectedPlanId: planId });
  const status = d.enumeration(v.status, ["generating", "ready", "applying", "accepted", "rejected", "failed", "uncertain", "conflict"] as const, `${p}.status`);
  const proposal = d.nullable(v.proposal, `${p}.proposal`, (raw, path): PlanRevisionProposal => {
    const value = d.record(raw, path);
    exact(value, ["schema_name", "schema_version", "explanation", "course_title", "overview", "today_tasks", "schedule"], path);
    if (value.schema_name !== "PlanRevisionProposal" || value.schema_version !== "plan-revision-proposal-v1") fail(path, "unsupported_contract");
    const schedule = d.array(value.schedule, `${path}.schedule`, (item, itemPath) => {
      const entry = d.record(item, itemPath);
      exact(entry, ["schedule_ref", "title", "focus"], itemPath);
      return { scheduleRef: boundedString(entry.schedule_ref, `${itemPath}.schedule_ref`, 160), title: boundedString(entry.title, `${itemPath}.title`, 500), focus: boundedString(entry.focus, `${itemPath}.focus`, 4000) };
    });
    if (!schedule.length || schedule.length > 64) fail(path, "schedule_count_invalid");
    d.unique(schedule.map(item => item.scheduleRef), path);
    if (schedule.length !== basePlan.schedule.length || schedule.some(item => !basePlan.schedule.some(old => old.id === item.scheduleRef))) fail(path, "schedule_target_mismatch");
    const todayTasks = d.stringArray(value.today_tasks, `${path}.today_tasks`);
    if (!todayTasks.length || todayTasks.length > 24) fail(path, "task_count_invalid");
    if (todayTasks.some(task => !task.trim() || Array.from(task).length > 4000)) fail(path, "task_invalid");
    return { explanation: boundedString(value.explanation, `${path}.explanation`, 4000), courseTitle: boundedString(value.course_title, `${path}.course_title`, 500),
      overview: boundedString(value.overview, `${path}.overview`, 8000), todayTasks, schedule };
  });
  if (["ready", "applying", "accepted", "rejected", "conflict"].includes(status) && !proposal) fail(p, "proposal_missing");
  const result = d.nullable(v.result, `${p}.result`, value => decodeLearningPlan(value, { expectedPlanId: planId }));
  if ((status === "accepted") !== (result !== null)) fail(p, "result_status_mismatch");
  if (result && proposal) {
    const expected = { ...basePlan, revision: baseRevision + 1, courseTitle: proposal.courseTitle,
      overview: proposal.overview, todayTasks: proposal.todayTasks,
      schedule: proposal.schedule.map(item => ({ ...basePlan.schedule.find(old => old.id === item.scheduleRef)!, title: item.title, focus: item.focus })) };
    // Progress counts/status remain immutable, while labels and schedule order
    // are application-derived from the revised schedule, matching PlanProgressProjector.
    expected.studyUnitProgress = basePlan.studyUnitProgress.map(progress => {
      const unit = basePlan.studyUnits.find(item => item.id === progress.unitId)!;
      const related = expected.schedule.filter(item => item.unitId === progress.unitId);
      const objective = basePlan.objective.replace(/\s+/gu, " ").replace(/^[ 。.!！?？;；：:]+|[ 。.!！?？;；：:]+$/gu, "");
      const goalTitle = !objective ? "目标导向学习计划" : Array.from(objective).length <= 24 ? objective
        : `${Array.from(objective).slice(0, 24).join("").trimEnd()}…`;
      return { ...progress, scheduleIds: related.map(item => item.id),
        title: unit.title.trim() || related.flatMap(item => item.scheduleChapters).find(chapter => chapter.title.trim())?.title.trim() || unit.id,
        objectiveFragment: related.find(item => item.focus.trim())?.focus.trim() || unit.summary.trim() || goalTitle };
    });
    if (JSON.stringify(result) !== JSON.stringify(expected)) fail(p, "committed_projection_mismatch");
  }
  return { operationId, clientRequestId: requestId, planId, baseRevision, status, proposal, basePlan, result,
    instruction, rollbackRevision, errorCode: d.string(v.error_code, p, true) };
}
