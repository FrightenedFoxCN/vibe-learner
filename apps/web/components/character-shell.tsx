import type { CSSProperties } from "react";
import type {
  PersonaProfile,
  SessionAffinityState,
  SessionFollowUp,
  StudyChatResponse
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
  variant = "default"
}: CharacterShellProps) {
  const responseEvents = response?.characterEvents ?? [];
  const currentEvent = responseEvents[0] ?? null;
  const isEmbedded = variant === "embedded";

  const teachingMethodSlot = persona.slots.find((s) => s.kind === "teaching_method");
  const teachingLabel = teachingMethodSlot?.content || persona.summary;

  return (
    <div style={{ ...styles.wrap, ...(isEmbedded ? styles.wrapEmbedded : {}) }}>
      {!isEmbedded ? (
        <div style={styles.header}>
          <span style={styles.name}>{persona.name}</span>
          <span style={styles.meta}>{teachingLabel}</span>
        </div>
      ) : null}

      <div style={styles.infoList}>
        <InfoRow
          label="状态"
          value={pending ? "更新中" : currentEvent ? "已同步" : "待开始"}
        />
        <InfoRow label="对话" value={formatTurnCount(turnCount)} />
        <InfoRow label="情绪" value={formatEmotionLabel(currentEvent?.emotion ?? "calm")} />
        <InfoRow label="语气" value={formatSpeechStyleLabel(currentEvent?.speechStyle ?? persona.defaultSpeechStyle)} />
        <InfoRow label="好感" value={formatAffinityLevel(affinityState?.level)} />
        <InfoRow label="续接" value={formatFollowUpState(nextFollowUp)} />
      </div>
      {affinityState?.summary ? (
        <div style={styles.noteRow}>
          <span style={styles.noteKey}>观察</span>
          <p style={styles.noteText}>{affinityState.summary}</p>
        </div>
      ) : null}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.infoRow}>
      <span style={styles.infoLabel}>{label}</span>
      <span style={styles.infoValue}>{value}</span>
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

const styles: Record<string, CSSProperties> = {
  wrap: {
    paddingTop: 4,
    display: "grid",
    gap: 10,
    minWidth: 0,
    maxWidth: "100%",
    overflow: "hidden",
  },
  wrapEmbedded: {
    paddingTop: 0,
  },
  header: {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    flexWrap: "wrap",
  },
  name: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)",
  },
  meta: {
    fontSize: 12,
    color: "var(--muted)",
  },
  infoList: {
    display: "grid",
    gap: 6,
    minWidth: 0,
  },
  infoRow: {
    display: "grid",
    gridTemplateColumns: "56px minmax(0, 1fr)",
    gap: 8,
    alignItems: "start",
    minWidth: 0,
  },
  infoLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
    paddingTop: 1,
  },
  infoValue: {
    fontSize: 12,
    color: "var(--ink)",
    lineHeight: 1.5,
    wordBreak: "break-word",
  },
  noteRow: {
    display: "grid",
    gridTemplateColumns: "56px minmax(0, 1fr)",
    gap: 8,
    alignItems: "start",
    minWidth: 0,
  },
  noteKey: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
    paddingTop: 1,
  },
  noteText: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--ink)",
    wordBreak: "break-word",
  },
};
