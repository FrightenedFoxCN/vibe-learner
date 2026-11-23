import type {
  PersonaProfile,
  SessionAffinityState,
  SessionFollowUp,
  StudyChatResponse,
} from "@vibe-learner/shared";

interface CharacterShellProps {
  persona: PersonaProfile;
  response: StudyChatResponse | null;
  pending: boolean;
  turnCount?: number;
  affinityState?: SessionAffinityState;
  nextFollowUp?: SessionFollowUp | null;
  variant?: "default" | "embedded";
}

export function CharacterShell({
  persona,
  response,
  pending,
  turnCount = 0,
  affinityState,
  nextFollowUp,
  variant = "default",
}: CharacterShellProps) {
  const responseEvents = response?.characterEvents ?? [];
  const currentEvent = responseEvents[0] ?? null;
  const isEmbedded = variant === "embedded";

  const teachingMethodSlot = persona.slots.find((s) => s.kind === "teaching_method");
  const teachingLabel = teachingMethodSlot?.content || persona.summary;

  return (
    <div
      className={
        isEmbedded
          ? "study-character-wrap study-character-wrap-embedded"
          : "study-character-wrap"
      }
    >
      {!isEmbedded ? (
        <div className="study-character-header">
          <span className="study-character-name">{persona.name}</span>
          <span className="study-character-meta">{teachingLabel}</span>
        </div>
      ) : null}

      <div className="study-character-info-list">
        <InfoRow
          label="角色状态"
          value={currentEvent ? "表演状态已就绪" : pending ? "等待表演状态" : "待开始"}
        />
        <InfoRow label="对话" value={formatTurnCount(turnCount)} />
        <InfoRow
          label="情绪"
          value={formatEmotionLabel(currentEvent?.emotion ?? "calm")}
        />
        <InfoRow
          label="语气"
          value={formatSpeechStyleLabel(
            currentEvent?.speechStyle ?? persona.defaultSpeechStyle,
          )}
        />
        <InfoRow label="好感" value={formatAffinityLevel(affinityState?.level)} />
        <InfoRow label="续接" value={formatFollowUpState(nextFollowUp)} />
      </div>
      {affinityState?.summary ? (
        <div className="study-character-note-row">
          <span className="study-character-note-key">观察</span>
          <p className="study-character-note-text">{affinityState.summary}</p>
        </div>
      ) : null}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="study-character-info-row">
      <span className="study-character-info-label">{label}</span>
      <span className="study-character-info-value">{value}</span>
    </div>
  );
}

function formatEmotionLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "calm") return "冷静";
  if (normalized === "encouraging") return "鼓励";
  if (normalized === "playful") return "轻快";
  if (normalized === "serious") return "认真";
  if (normalized === "excited") return "兴奋";
  if (normalized === "concerned") return "关注";
  return value || "未标注";
}

function formatSpeechStyleLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "steady") return "平稳";
  if (normalized === "warm") return "温和";
  if (normalized === "dramatic") return "戏剧化";
  if (normalized === "gentle") return "轻柔";
  if (normalized === "energetic") return "有活力";
  return value || "默认";
}

function formatAffinityLevel(value?: string) {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized === "close") return "亲近";
  if (normalized === "warm") return "温和";
  if (normalized === "guarded") return "保留";
  if (normalized === "distant") return "疏离";
  if (normalized === "neutral") return "中性";
  return value || "中性";
}

function formatFollowUpState(value?: SessionFollowUp | null) {
  if (!value) {
    return "无";
  }
  if (value.status === "pending") {
    return value.reason ? `待续接 · ${value.reason}` : "待续接";
  }
  if (value.status === "completed") {
    return "已完成";
  }
  if (value.status === "canceled") {
    return "已取消";
  }
  return value.status || "未知";
}

function formatTurnCount(value: number) {
  if (value <= 0) {
    return "未开始";
  }
  return `${value} 轮`;
}
