import type { CSSProperties } from "react";
import type { PersonaProfile, StudyChatResponse } from "@vibe-learner/shared";

import { placeholderCharacterRenderer } from "./character-renderer";

interface CharacterShellProps {
  persona: PersonaProfile;
  response: StudyChatResponse | null;
  pending: boolean;
  variant?: "default" | "embedded";
}

export function CharacterShell({
  persona,
  response,
  pending,
  variant = "default"
}: CharacterShellProps) {
  const currentEvent = response?.characterEvents[0] ?? null;
  const toolEvents = (response?.characterEvents ?? []).filter((event) => event.toolName);
  const Renderer = placeholderCharacterRenderer.Render;
  const isEmbedded = variant === "embedded";

  const teachingMethodSlot = persona.slots.find((s) => s.kind === "teaching_method");
  const narrativeModeSlot = persona.slots.find((s) => s.kind === "narrative_mode");
  const teachingLabel = teachingMethodSlot?.content || persona.summary;
  const narrativeLabel = formatNarrativeMode(narrativeModeSlot?.content ?? "稳态导学");

  return (
    <div style={{ ...styles.wrap, ...(isEmbedded ? styles.wrapEmbedded : {}) }}>
      {!isEmbedded ? (
        <div style={styles.header}>
          <span style={styles.name}>{persona.name}</span>
          <span style={styles.meta}>{teachingLabel} · {narrativeLabel}</span>
        </div>
      ) : null}

      <Renderer persona={persona} currentEvent={currentEvent} pending={pending} />

      <div style={styles.stateRow}>
        <div style={styles.stateItem}>
          <span style={styles.stateKey}>神态</span>
          <span style={styles.stateVal}>{currentEvent?.emotion ?? "calm"}</span>
        </div>
        <div style={styles.stateItem}>
          <span style={styles.stateKey}>动作</span>
          <span style={styles.stateVal}>{currentEvent?.action ?? "idle"}</span>
        </div>
        <div style={styles.stateItem}>
          <span style={styles.stateKey}>风格</span>
          <span style={styles.stateVal}>{currentEvent?.speechStyle ?? persona.defaultSpeechStyle}</span>
        </div>
        {!isEmbedded ? (
          <div style={styles.stateItem}>
            <span style={styles.stateKey}>场景</span>
            <span style={styles.stateVal}>{currentEvent?.sceneHint ?? "study_session"}</span>
          </div>
        ) : null}
      </div>

      {toolEvents.length ? (
        <div style={styles.toolWrap}>
          <span style={styles.stateKey}>场景工具事件</span>
          <div style={styles.toolList}>
            {toolEvents.map((event, index) => (
              <div key={`${event.lineSegmentId}:${index}`} style={styles.toolItem}>
                <strong style={styles.toolName}>{event.toolName}</strong>
                <span style={styles.toolSummary}>{event.toolSummary || event.sceneHint}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    borderTop: "1px solid var(--border)",
    paddingTop: 14,
    display: "grid",
    gap: 12,
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
  stateRow: {
    display: "flex",
    gap: 16,
    flexWrap: "wrap",
  },
  stateItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline",
  },
  stateKey: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.07em",
  },
  stateVal: {
    fontSize: 13,
    color: "var(--ink)",
  },
  toolWrap: {
    display: "grid",
    gap: 8,
  },
  toolList: {
    display: "grid",
    gap: 8,
  },
  toolItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    borderRadius: 12,
    background: "var(--panel)",
    border: "1px solid var(--border)",
  },
  toolName: {
    fontSize: 12,
    color: "var(--ink)",
  },
  toolSummary: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5,
  },
};

function formatNarrativeMode(mode: string) {
  if (mode === "light_story" || mode.includes("轻剧情")) return "轻剧情陪伴";
  if (mode === "grounded" || mode.includes("稳态导学") || mode.includes("贴地")) return "稳态导学";
  return mode;
}
