import type { CharacterStateEvent, StudySessionRecord } from "@vibe-learner/shared";

export function formatTurnTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function buildRenderableReply(
  reply: string,
  richBlocks?: Array<{ kind: string; content: string }>,
) {
  const normalizedReply = String(reply ?? "").trim();
  const blocks = Array.isArray(richBlocks) ? richBlocks : [];
  if (!blocks.length) {
    return normalizedReply;
  }
  const appendix = blocks
    .map((block) => {
      const kind = String(block.kind ?? "")
        .trim()
        .toLowerCase();
      const content = String(block.content ?? "").trim();
      if (!kind || !content) {
        return "";
      }
      if (kind === "mermaid") {
        return `\n\n\`\`\`mermaid\n${content}\n\`\`\``;
      }
      return `\n\n\`\`\`${kind}\n${content}\n\`\`\``;
    })
    .filter(Boolean)
    .join("");
  return `${normalizedReply}${appendix}`;
}
export function collectEventDetails(events: CharacterStateEvent[]) {
  const items: Array<{ label: "角色动作" | "表达提示" | "工具回执"; text: string }> =
    [];
  const seen = new Set<string>();

  events.forEach((event) => {
    [
      { label: "角色动作" as const, text: formatActionDescription(event.action) },
      { label: "表达提示" as const, text: event.deliveryCue },
      { label: "工具回执" as const, text: event.toolSummary },
    ].forEach((item) => {
      const text = String(item.text ?? "").trim();
      if (!text || text.length < 6 || seen.has(text)) {
        return;
      }
      seen.add(text);
      items.push({ label: item.label, text });
    });
  });

  return items.slice(0, 6);
}

function formatActionDescription(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "idle") return "";
  if (normalized === "nod") return "轻轻点头。";
  if (normalized === "point") return "指向当前重点。";
  if (normalized === "lean_in") return "微微前倾。";
  if (normalized === "smile") return "带着笑意。";
  if (normalized === "pause") return "短暂停顿。";
  if (normalized === "write") return "抬手书写比划。";
  return value.trim();
}

export function formatToolName(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "update_learning_plan") return "提出计划修改";
  if (normalized === "update_learning_plan_progress") return "提出进度修改";
  return value || "工具事件";
}

function isAttemptTurn(message: string) {
  return message.trim().startsWith("[练习作答]");
}

export function isHiddenLearnerMessage(
  turn: Pick<
    StudySessionRecord["turns"][number],
    "learnerMessage" | "learnerMessageKind"
  >,
) {
  const kind = String(turn.learnerMessageKind ?? "learner");
  if (kind !== "learner") {
    return true;
  }
  const normalized = turn.learnerMessage.trim();
  return normalized.startsWith("[练习作答]") || normalized.startsWith("[交互回调]");
}

export function formatLearnerMessage(
  turn: Pick<
    StudySessionRecord["turns"][number],
    "learnerMessage" | "learnerMessageKind"
  >,
) {
  const kind = String(turn.learnerMessageKind ?? "learner");
  if (kind === "interactive_callback") return "答题回调";
  if (kind === "session_prelude") return "章节预处理";
  if (kind === "scheduled_follow_up") return "自动续接";
  if (!isAttemptTurn(turn.learnerMessage)) return turn.learnerMessage;
  return turn.learnerMessage.replace("[练习作答]", "练习作答").trim();
}

export function formatAttachmentLabel(
  attachment: NonNullable<
    StudySessionRecord["turns"][number]["learnerAttachments"]
  >[number],
) {
  const typeLabel =
    attachment.kind === "image" ? "图片" : attachment.kind === "pdf" ? "PDF" : "附件";
  return `${typeLabel} · ${attachment.name}`;
}

export function formatFileSize(size: number) {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${size} B`;
}
