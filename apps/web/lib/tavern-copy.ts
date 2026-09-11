import type { TavernRun } from "@vibe-learner/shared";
import type { TavernParticipantGenerationState } from "./tavern-workspace-state.ts";

export const TAVERN_COPY_CONTRACT = "tavern-copy-v1";
export const RUN_STATUS_LABELS: Readonly<Record<TavernRun["status"], string>> = Object.freeze({
  pending: "等待生成", completed: "已完成", partial: "部分角色已回应", failed: "本轮未完成", canceled: "已取消",
});
export const STEP_STATUS_LABELS: Readonly<Record<TavernParticipantGenerationState, string>> = Object.freeze({
  idle: "就绪", pending: "等待发言", generating: "正在生成", completed: "已回应", failed: "回应未完成",
  blocked: "前序未完成，尚未执行", canceled: "已取消", previous_completed: "上一轮已回应",
  previous_failed: "上一轮未完成", previous_blocked: "上一轮尚未执行", previous_canceled: "上一轮已取消",
});
export const TAVERN_COPY = Object.freeze({
  partial: "部分角色回应未完成；已保存的回应不会重复生成，可在下方仅恢复未完成角色。",
  failed: "本轮角色回应未完成；可从恢复入口继续尚未完成的角色。",
  retryIncomplete: "仍有角色未完成回应；已保存的回应不会重复生成，可继续恢复剩余角色。",
  blocked: "因前序回应未完成而暂未执行",
  canceled: "已取消接收本轮结果；已发出的模型请求可能仍运行到超时",
  cancelUnconfirmed: "取消结果尚未确认，请刷新查看本轮状态，再决定是否重试。",
  archived: "归档房间为只读状态。",
  recovered: "位已完成回应，已保存的回应不会重复生成。",
  retryScope: "本次只恢复先前未完成的角色。",
});
const ERROR_COPY: Readonly<Record<string, string>> = Object.freeze({
  tavern_revision_conflict: "房间刚刚发生了更新，请刷新并确认内容后重试。",
  tavern_run_in_progress: "这个房间已有一轮互动正在生成，请稍后刷新。",
  tavern_continue_anchor_stale: "对话已出现更新；请基于最新一条消息继续。",
  tavern_retry_context_changed: "房间内容或角色设定已变化，不能继续旧恢复任务。",
  tavern_retry_already_created: "这次未完成互动已经创建过恢复任务，请刷新查看结果。",
  tavern_room_not_active: "这个房间已归档；恢复使用后才能继续互动。",
  tavern_run_failed: "本轮回应未完成；已保存的消息不会丢失，可从恢复入口继续未完成角色。",
});

// Callers classify transport/decode failures; unrecognized server codes never
// become learner-facing text. Raw evidence remains in the debug projection.
export function tavernFailureNotice(code: string, kind: "decode" | "network" | "other", fallback: string): string {
  if (Object.hasOwn(ERROR_COPY, code)) return ERROR_COPY[code]!;
  if (kind === "decode") return "服务器返回的数据未通过可靠性校验；页面已保留现有内容，请刷新恢复，若持续出现请查看调试详情。";
  if (kind === "network") return "无法连接 AI 服务，请检查服务是否已启动。";
  return fallback;
}
