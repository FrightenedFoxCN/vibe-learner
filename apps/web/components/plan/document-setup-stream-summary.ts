import { documentPlanningTextBlockReason } from "../../lib/document-planning-readiness";

export interface StreamEventItem {
  stage: string;
  payload: Record<string, unknown>;
}

type PlanRoundStatus = "running" | "completed" | "failed";

interface PlanRoundSummaryItem {
  roundIndex: number;
  status: PlanRoundStatus;
  toolCalls: string[];
  finishReason: string;
  elapsedMs?: number;
  error?: string;
}

interface PlanningQuestionSummaryItem {
  id: string;
  question: string;
  reason: string;
}

export function summarizePlanRounds(events: StreamEventItem[]) {
  const rounds = new Map<number, PlanRoundSummaryItem>();
  const planningQuestions = new Map<string, PlanningQuestionSummaryItem>();
  let totalToolCalls = 0;
  let latestMessage = "";
  let totalTokens = 0;
  let totalElapsedMs = 0;
  let repairCount = 0;

  for (const event of events) {
    const roundIndex = toNumber(event.payload.round_index);
    const ensureRound = () => {
      if (roundIndex === null) {
        return null;
      }
      const current = rounds.get(roundIndex) ?? {
        roundIndex,
        status: "running" as const,
        toolCalls: [],
        finishReason: "",
      };
      rounds.set(roundIndex, current);
      return current;
    };

    if (event.stage === "model_round_started") {
      const round = ensureRound();
      if (round) {
        round.status = "running";
        latestMessage = `第 ${round.roundIndex + 1} 轮开始。`;
      }
      continue;
    }

    if (event.stage === "model_tool_call") {
      const round = ensureRound();
      const toolName = String(event.payload.tool_name ?? "").trim();
      if (round && toolName) {
        round.toolCalls.push(toolName);
        totalToolCalls += 1;
        latestMessage = `第 ${round.roundIndex + 1} 轮调用了 ${toolName}。`;
      }
      continue;
    }

    if (event.stage === "planning_question_asked") {
      const questionId = String(event.payload.question_id ?? "").trim();
      const question = String(event.payload.question ?? "").trim();
      if (questionId && question) {
        planningQuestions.set(questionId, {
          id: questionId,
          question,
          reason: String(event.payload.reason ?? "").trim(),
        });
        latestMessage = "有待回答问题。";
      }
      continue;
    }

    if (event.stage === "model_round_completed") {
      const round = ensureRound();
      if (round) {
        round.status = "completed";
        round.finishReason = String(event.payload.finish_reason ?? "").trim();
        round.elapsedMs = toNumber(event.payload.elapsed_ms) ?? undefined;
        totalElapsedMs += round.elapsedMs ?? 0;
        totalTokens +=
          toNumber(event.payload.total_tokens) ??
          toNumber(event.payload.completion_tokens) ??
          0;
        latestMessage = `第 ${round.roundIndex + 1} 轮完成。`;
      }
      continue;
    }

    if (event.stage === "model_round_failed") {
      const round = ensureRound();
      if (round) {
        round.status = "failed";
        round.finishReason = String(event.payload.finish_reason ?? "").trim();
        round.elapsedMs = toNumber(event.payload.elapsed_ms) ?? undefined;
        round.error = String(event.payload.error ?? "").trim();
        totalTokens +=
          toNumber(event.payload.total_tokens) ??
          toNumber(event.payload.completion_tokens) ??
          0;
        latestMessage = `第 ${round.roundIndex + 1} 轮失败。`;
      }
      continue;
    }

    if (event.stage.includes("repair") || event.stage === "schema_repair") {
      repairCount += 1;
    }

    if (event.stage === "learning_plan_completed") {
      latestMessage = "计划已生成。";
      continue;
    }

    if (event.stage === "stream_error") {
      latestMessage = `生成出错：${String(event.payload.error ?? "未知错误")}`;
      continue;
    }

    if (event.stage === "stream_cancelled") {
      latestMessage = "生成已中断。";
      continue;
    }

    if (event.stage === "stream_completed" && !latestMessage) {
      latestMessage = "生成完成。";
    }
  }

  return {
    rounds: [...rounds.values()].sort((a, b) => a.roundIndex - b.roundIndex),
    planningQuestions: [...planningQuestions.values()],
    totalToolCalls,
    totalTokens,
    totalElapsedMs,
    repairCount,
    latestMessage,
  };
}

export function summarizeProcessProgress(events: StreamEventItem[]) {
  let totalPages = 0;
  let completedPages = 0;
  let phase = "等待开始";
  let warning = "";
  let error = "";
  let checkpointSaved: boolean | null = null;
  for (const event of events) {
    totalPages = Math.max(totalPages, toNumber(event.payload.page_count) ?? 0);
    completedPages = Math.max(
      completedPages,
      toNumber(event.payload.processed_pages) ??
        toNumber(event.payload.page_number) ??
        0,
    );
    if (event.stage === "parser_started") phase = "读取目录与页面";
    if (event.stage === "page_parsed")
      phase = event.payload.used_ocr ? "OCR 回退识别" : "提取页面文本";
    if (event.stage === "margin_patterns_detected") phase = "清理页眉页脚";
    if (event.stage === "study_units_built") phase = "整理学习单元";
    if (
      event.stage === "document_processing_completed" &&
      event.payload.chunk_count === 0
    ) {
      warning = documentPlanningTextBlockReason({
        chunkCount: 0,
        ocrStatus: event.payload.ocr_status === "unavailable" ? "unavailable" : null,
      });
    }
    if (
      event.stage === "ocr_failed" ||
      event.payload.extraction_source === "ocr_failed"
    )
      warning = "部分页面 OCR 失败，结果可能缺少文字。";
    if (event.stage === "stream_error")
      error = String(event.payload.error ?? "未知错误");
    if (typeof event.payload.checkpoint_saved === "boolean")
      checkpointSaved = event.payload.checkpoint_saved;
  }
  const last = events.at(-1);
  const elapsedMs = toNumber(last?.payload.elapsed_ms) ?? 0;
  const rate =
    completedPages && elapsedMs > 0
      ? Math.round(completedPages / (elapsedMs / 60000))
      : 0;
  const remaining =
    totalPages > completedPages && rate
      ? Math.ceil((totalPages - completedPages) / rate)
      : 0;
  return {
    totalPages,
    completedPages,
    phase,
    warning,
    error,
    checkpointSaved,
    rate: rate || 0,
    eta: remaining ? `${remaining} 分钟` : "",
  };
}

export function formatProcessStreamStatus(status: string) {
  if (status === "running") return "解析中";
  if (status === "completed") return "已完成";
  if (status === "cancelled") return "已中断";
  if (status === "error") return "失败";
  return "未开始";
}

export function formatProcessError(error: string, checkpointSaved: boolean | null) {
  const checkpoint =
    checkpointSaved === true
      ? "已保存 checkpoint"
      : checkpointSaved === false
        ? "未保存 checkpoint"
        : "checkpoint 状态未返回";
  if (error.includes("ocr_unavailable"))
    return `OCR 引擎暂不可用（${checkpoint}）；请检查运行设置或拆分 PDF 后重试。`;
  if (error.includes("ocr_partial") || error.includes("ocr_failed"))
    return `部分页面 OCR 失败（${checkpoint}）；可拆分 PDF、调整 OCR 设置后重试。`;
  if (error.includes("timeout"))
    return `教材解析超时（${checkpoint}）；可拆分 PDF 或调整运行上限后重试。`;
  return `教材解析失败（${checkpoint}）；请检查 OCR 引擎、拆分 PDF 后重试。`;
}

function toNumber(value: unknown): number | null {
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

export function formatPlanStreamStatus(status: string) {
  switch (status) {
    case "running":
      return "生成中";
    case "completed":
      return "已完成";
    case "cancelled":
      return "已中断";
    case "error":
      return "出错";
    default:
      return "未开始";
  }
}

export function formatRoundStatus(status: PlanRoundStatus) {
  switch (status) {
    case "completed":
      return "完成";
    case "failed":
      return "失败";
    default:
      return "进行中";
  }
}
