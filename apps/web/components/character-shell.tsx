import type { CSSProperties } from "react";
import type {
  PersonaProfile,
  SessionAffinityState,
  SessionFollowUp,
  SessionProjectedPdf,
  StudyChatResponse
} from "@vibe-learner/shared";

interface CharacterShellProps {
  persona: PersonaProfile;
  response: StudyChatResponse | null;
  pending: boolean;
  affinityState?: SessionAffinityState;
  projectedPdf?: SessionProjectedPdf | null;
  nextFollowUp?: SessionFollowUp | null;
  variant?: "default" | "embedded";
}

export function CharacterShell({
  persona,
  response,
  pending,
  affinityState,
  projectedPdf,
  nextFollowUp,
  variant = "default"
}: CharacterShellProps) {
  const responseEvents = response?.characterEvents ?? [];
  const currentEvent = responseEvents[0] ?? null;
  const isEmbedded = variant === "embedded";

  const teachingMethodSlot = persona.slots.find((s) => s.kind === "teaching_method");
  const narrativeModeSlot = persona.slots.find((s) => s.kind === "narrative_mode");
  const teachingLabel = teachingMethodSlot?.content || persona.summary;
  const narrativeLabel = formatNarrativeMode(narrativeModeSlot?.content ?? "稳态导学");
  const actionText = formatActionText(currentEvent?.action ?? "");
  const primaryNote = currentEvent?.commentary || currentEvent?.toolSummary || "";
  const deliveryCue = currentEvent?.deliveryCue || "";

  return (
    <div style={{ ...styles.wrap, ...(isEmbedded ? styles.wrapEmbedded : {}) }}>
      {!isEmbedded ? (
        <div style={styles.header}>
          <span style={styles.name}>{persona.name}</span>
          <span style={styles.meta}>{persona.relationship || "未设关系"} · {persona.learnerAddress || "未设称呼"}</span>
          <span style={styles.meta}>{teachingLabel} · {narrativeLabel}</span>
        </div>
      ) : null}

      <section style={styles.statusCard}>
        <div style={styles.sectionHead}>
          <strong style={styles.sectionTitle}>状态</strong>
          <span style={styles.sectionMeta}>
            {pending ? "更新中" : currentEvent ? "已同步" : "待开始"}
          </span>
        </div>
        <div style={styles.stateGrid}>
          <StateChip label="情绪" value={formatEmotionLabel(currentEvent?.emotion ?? "calm")} />
          <StateChip label="语气" value={formatSpeechStyleLabel(currentEvent?.speechStyle ?? persona.defaultSpeechStyle)} />
          {!isEmbedded ? <StateChip label="场景" value={formatSceneHint(currentEvent?.sceneHint ?? "study_session")} /> : null}
        </div>
        {actionText ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>动作</span>
            <p style={styles.noteText}>{actionText}</p>
          </div>
        ) : null}
        {deliveryCue ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>语气</span>
            <p style={styles.noteText}>{deliveryCue}</p>
          </div>
        ) : null}
        {primaryNote ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>说明</span>
            <p style={styles.noteText}>{primaryNote}</p>
          </div>
        ) : null}
      </section>

      <section style={styles.statusCard}>
        <div style={styles.sectionHead}>
          <strong style={styles.sectionTitle}>会话信息</strong>
          <span style={styles.sectionMeta}>实时</span>
        </div>
        <div style={styles.stateGrid}>
          <StateChip
            label="好感度"
            value={`${formatAffinityLevel(affinityState?.level)} · ${affinityState?.score ?? 0}`}
          />
          <StateChip
            label="投射"
            value={projectedPdf ? formatProjectedPreview(projectedPdf) : "未投射"}
          />
          <StateChip
            label="续接"
            value={nextFollowUp ? formatFollowUpState(nextFollowUp) : "无"}
          />
        </div>
        {affinityState?.summary ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>备注</span>
            <p style={styles.noteText}>{affinityState.summary}</p>
          </div>
        ) : null}
        {projectedPdf ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>当前材料</span>
            <p style={styles.noteText}>
              {projectedPdf.title}
              {projectedPdf.sourceKind === "attachment_image"
                ? " · 图片"
                : ` · 第 ${projectedPdf.pageNumber} 页${projectedPdf.pageCount ? ` / 共 ${projectedPdf.pageCount} 页` : ""}`}
              {projectedPdf.overlays.length ? ` · ${projectedPdf.overlays.length} 个标注` : ""}
            </p>
          </div>
        ) : null}
        {nextFollowUp ? (
          <div style={styles.noteBlock}>
            <span style={styles.noteKey}>下次续接</span>
            <p style={styles.noteText}>
              {formatDueAt(nextFollowUp.dueAt)} · {nextFollowUp.reason || "继续当前话题"}
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function StateChip({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.stateItem}>
      <span style={styles.stateKey}>{label}</span>
      <span style={styles.stateVal}>{value}</span>
    </div>
  );
}

function formatNarrativeMode(mode: string) {
  if (mode === "light_story" || mode.includes("轻剧情")) return "轻剧情陪伴";
  if (mode === "grounded" || mode.includes("稳态导学") || mode.includes("贴地")) return "稳态导学";
  return mode;
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

function formatActionText(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "idle") return "";
  if (normalized === "nod") return "轻轻点头。";
  if (normalized === "point") return "指向重点。";
  if (normalized === "lean_in") return "微微前倾。";
  if (normalized === "smile") return "带着笑意。";
  if (normalized === "pause") return "短暂停顿。";
  if (normalized === "write") return "比划书写。";
  return value.trim();
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

function formatSceneHint(value: string) {
  if (!value) {
    return "学习场景";
  }
  if (value.startsWith("study_session:")) {
    const detail = value.replace("study_session:", "");
    return `学习场景 · ${detail}`;
  }
  if (value.startsWith("scene_tool:")) {
    return `场景工具 · ${formatToolName(value.replace("scene_tool:", ""))}`;
  }
  return value
    .replaceAll("study_session", "学习场景")
    .replaceAll("overview", "概览")
    .replaceAll("scene_tool", "场景工具");
}

function formatToolName(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "read_scene_overview") return "读取场景";
  if (normalized === "add_scene") return "新增场景层";
  if (normalized === "move_to_scene") return "切换场景层";
  if (normalized === "add_object") return "新增物件";
  if (normalized === "update_object_description") return "更新物件描述";
  if (normalized === "delete_object") return "删除物件";
  if (normalized === "retrieve_memory_context") return "检索记忆";
  if (normalized === "read_page_range_content") return "读取教材正文";
  if (normalized === "read_page_range_images") return "读取教材图像";
  return value || "工具事件";
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

function formatFollowUpState(value: SessionFollowUp) {
  if (value.status === "pending") return "待触发";
  if (value.status === "completed") return "已完成";
  if (value.status === "canceled") return "已取消";
  return value.status || "未知";
}

function formatProjectedPreview(value: SessionProjectedPdf) {
  if (value.sourceKind === "attachment_image") {
    return value.overlays.length ? `图片 · ${value.overlays.length} 标注` : "图片";
  }
  return `p.${value.pageNumber}${value.pageCount ? ` / ${value.pageCount}` : ""}`;
}

function formatDueAt(value: string) {
  const parsed = Date.parse(value || "");
  if (!Number.isFinite(parsed)) {
    return "时间未定";
  }
  return new Date(parsed).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    borderTop: "1px solid var(--border)",
    paddingTop: 14,
    display: "grid",
    gap: 12,
    minWidth: 0,
    maxWidth: "100%",
    overflow: "hidden",
  },
  wrapEmbedded: {
    borderTop: "none",
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
  statusCard: {
    display: "grid",
    gap: 8,
    padding: "10px 12px",
    borderRadius: 12,
    background: "var(--bg)",
    border: "1px solid var(--border)",
    minWidth: 0,
  },
  sectionHead: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 10,
    flexWrap: "wrap",
  },
  sectionTitle: {
    fontSize: 13,
    color: "var(--ink)",
  },
  sectionMeta: {
    fontSize: 11,
    color: "var(--muted)",
    whiteSpace: "nowrap",
  },
  stateGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(84px, 1fr))",
    gap: 8,
    minWidth: 0,
  },
  stateItem: {
    display: "grid",
    gap: 2,
    minWidth: 0,
    padding: "7px 9px",
    borderRadius: 10,
    background: "var(--panel)",
    border: "1px solid var(--border)",
  },
  stateKey: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--muted)",
  },
  stateVal: {
    fontSize: 12,
    color: "var(--ink)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  noteBlock: {
    display: "grid",
    gap: 4,
    padding: "8px 10px",
    borderRadius: 10,
    background: "var(--panel)",
    border: "1px solid var(--border)",
    minWidth: 0,
  },
  noteKey: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
  },
  noteText: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--ink)",
    wordBreak: "break-word",
  },
};
