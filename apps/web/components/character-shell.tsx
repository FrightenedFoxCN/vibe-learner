import type { CSSProperties } from "react";
import type { PersonaProfile, StudyChatResponse } from "@gal-learner/shared";

import { placeholderCharacterRenderer } from "./character-renderer";

interface CharacterShellProps {
  persona: PersonaProfile;
  response: StudyChatResponse | null;
  pending: boolean;
}

export function CharacterShell({ persona, response, pending }: CharacterShellProps) {
  const currentEvent = response?.characterEvents[0] ?? null;
  const Renderer = placeholderCharacterRenderer.Render;

  return (
    <aside style={styles.panel}>
      <p style={styles.label}>角色层</p>
      <h2 style={styles.title}>{persona.name}</h2>
      <p style={styles.summary}>{persona.summary}</p>
      <Renderer persona={persona} currentEvent={currentEvent} pending={pending} />

      <div style={styles.metaGrid}>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>教学风格</span>
          <strong>{persona.teachingStyle.join(" / ")}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>叙事模式</span>
          <strong>{formatNarrativeMode(persona.narrativeMode)}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>说话风格</span>
          <strong>{currentEvent?.speechStyle ?? persona.defaultSpeechStyle}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>场景提示</span>
          <strong>{currentEvent?.sceneHint ?? "study_session"}</strong>
        </div>
      </div>

      <div style={styles.streamBox}>
        <p style={styles.streamTitle}>角色事件快照</p>
        <pre style={styles.pre}>{formatEventStream(response)}</pre>
      </div>
    </aside>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "linear-gradient(180deg, rgba(252,255,255,0.98), rgba(242,249,250,0.96))",
    boxShadow: "var(--shadow)"
  },
  label: {
    margin: 0,
    color: "var(--accent)",
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontSize: 12
  },
  title: {
    margin: "12px 0 6px",
    fontSize: 30,
    fontFamily: "var(--font-display), sans-serif"
  },
  summary: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  metaGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
    marginTop: 14
  },
  metaCard: {
    padding: 12,
    borderRadius: 12,
    background: "rgba(255,255,255,0.96)",
    border: "1px solid var(--border)",
    display: "grid",
    gap: 4,
    boxShadow: "var(--shadow-soft)"
  },
  metaLabel: {
    fontSize: 12,
    color: "var(--muted)"
  },
  streamBox: {
    marginTop: 14,
    padding: 16,
    borderRadius: 12,
    background: "#15353b",
    color: "#ecf8fa"
  },
  streamTitle: {
    margin: 0,
    fontSize: 13,
    color: "#9ed0d6"
  },
  pre: {
    margin: "10px 0 0",
    overflowX: "auto",
    whiteSpace: "pre-wrap",
    fontSize: 12,
    lineHeight: 1.6
  }
};

function formatNarrativeMode(mode: string) {
  if (mode === "light_story") {
    return "轻剧情陪伴";
  }
  if (mode === "grounded") {
    return "稳态导学";
  }
  return mode;
}

function formatEventStream(response: StudyChatResponse | null) {
  if (!response?.characterEvents.length) {
    return "尚未收到角色事件。\n生成导学回复后，这里会显示 emotion / action / speech_style 等结构化状态。";
  }
  return JSON.stringify(response.characterEvents, null, 2);
}
