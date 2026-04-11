import type { CSSProperties } from "react";
import type { PersonaProfile, StudyChatResponse } from "@vibe-learner/shared";

import { placeholderCharacterRenderer } from "./character-renderer";

interface CharacterShellProps {
  persona: PersonaProfile;
  response: StudyChatResponse | null;
  pending: boolean;
}

export function CharacterShell({ persona, response, pending }: CharacterShellProps) {
  const currentEvent = response?.characterEvents[0] ?? null;
  const Renderer = placeholderCharacterRenderer.Render;

  const teachingMethodSlot = persona.slots.find((s) => s.kind === "teaching_method");
  const narrativeModeSlot = persona.slots.find((s) => s.kind === "narrative_mode");
  const teachingLabel = teachingMethodSlot?.content || persona.summary;
  const narrativeLabel = formatNarrativeMode(narrativeModeSlot?.content ?? "grounded");

  return (
    <div style={styles.wrap}>
      <div style={styles.header}>
        <span style={styles.name}>{persona.name}</span>
        <span style={styles.meta}>{teachingLabel} · {narrativeLabel}</span>
      </div>

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
        <div style={styles.stateItem}>
          <span style={styles.stateKey}>场景</span>
          <span style={styles.stateVal}>{currentEvent?.sceneHint ?? "study_session"}</span>
        </div>
      </div>
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
};

function formatNarrativeMode(mode: string) {
  if (mode === "light_story") return "轻剧情陪伴";
  if (mode === "grounded") return "稳态导学";
  return mode;
}
