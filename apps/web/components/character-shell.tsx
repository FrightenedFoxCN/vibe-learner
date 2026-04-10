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
    <div style={styles.wrap}>
      <div style={styles.header}>
        <span style={styles.name}>{persona.name}</span>
        <span style={styles.meta}>
          {persona.teachingStyle.join(" / ")} · {formatNarrativeMode(persona.narrativeMode)}
        </span>
      </div>

      <Renderer persona={persona} currentEvent={currentEvent} pending={pending} />

      <div style={styles.stateRow}>
        <span style={styles.stateItem}>
          <span style={styles.stateKey}>神态</span>
          {currentEvent?.emotion ?? "calm"}
        </span>
        <span style={styles.stateItem}>
          <span style={styles.stateKey}>动作</span>
          {currentEvent?.action ?? "idle"}
        </span>
        <span style={styles.stateItem}>
          <span style={styles.stateKey}>风格</span>
          {currentEvent?.speechStyle ?? persona.defaultSpeechStyle}
        </span>
        <span style={styles.stateItem}>
          <span style={styles.stateKey}>场景</span>
          {currentEvent?.sceneHint ?? "study_session"}
        </span>
      </div>

      {response?.characterEvents.length ? (
        <pre style={styles.pre}>{JSON.stringify(response.characterEvents, null, 2)}</pre>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    borderTop: "1px solid var(--border)",
    paddingTop: 14,
    display: "grid",
    gap: 12
  },
  header: {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    flexWrap: "wrap"
  },
  name: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  meta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  stateRow: {
    display: "flex",
    gap: 16,
    fontSize: 13,
    color: "var(--ink)"
  },
  stateItem: {
    display: "flex",
    gap: 6,
    alignItems: "center"
  },
  stateKey: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  pre: {
    margin: 0,
    padding: "10px 12px",
    background: "var(--panel)",
    border: "1px solid var(--border)",
    borderRadius: 3,
    overflowX: "auto",
    whiteSpace: "pre-wrap",
    fontSize: 11,
    lineHeight: 1.6,
    color: "var(--ink)"
  }
};

function formatNarrativeMode(mode: string) {
  if (mode === "light_story") return "轻剧情陪伴";
  if (mode === "grounded") return "稳态导学";
  return mode;
}
