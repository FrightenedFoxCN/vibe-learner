import type { CSSProperties } from "react";
import type { CharacterStateEvent, PersonaProfile, StudyChatResponse } from "@gal-learner/shared";

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
          <span style={styles.metaLabel}>Teaching</span>
          <strong>{persona.teachingStyle.join(" / ")}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>Narrative</span>
          <strong>{persona.narrativeMode}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>Speech</span>
          <strong>{currentEvent?.speechStyle ?? persona.defaultSpeechStyle}</strong>
        </div>
        <div style={styles.metaCard}>
          <span style={styles.metaLabel}>Scene</span>
          <strong>{currentEvent?.sceneHint ?? "persona shell"}</strong>
        </div>
      </div>

      <div style={styles.streamBox}>
        <p style={styles.streamTitle}>Character event stream</p>
        <pre style={styles.pre}>
          {JSON.stringify(response?.characterEvents ?? [], null, 2)}
        </pre>
      </div>
    </aside>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 32,
    border: "1px solid var(--border)",
    background: "linear-gradient(180deg, rgba(255,248,238,0.96), rgba(250,239,220,0.88))",
    boxShadow: "var(--shadow)"
  },
  label: {
    margin: 0,
    color: "var(--teal)",
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontSize: 12
  },
  title: {
    margin: "12px 0 6px",
    fontSize: 36,
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
    marginTop: 18
  },
  metaCard: {
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.74)",
    border: "1px solid var(--border)",
    display: "grid",
    gap: 4
  },
  metaLabel: {
    fontSize: 12,
    color: "var(--muted)"
  },
  streamBox: {
    marginTop: 16,
    padding: 16,
    borderRadius: 18,
    background: "rgba(45,36,31,0.92)",
    color: "#fef7f0"
  },
  streamTitle: {
    margin: 0,
    fontSize: 13,
    color: "#dbc7b7"
  },
  pre: {
    margin: "10px 0 0",
    overflowX: "auto",
    whiteSpace: "pre-wrap",
    fontSize: 12,
    lineHeight: 1.6
  }
};
