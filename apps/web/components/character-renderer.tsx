import type { CSSProperties, JSX } from "react";
import type { CharacterStateEvent, PersonaProfile } from "@gal-learner/shared";

export interface CharacterRendererProps {
  persona: PersonaProfile;
  currentEvent: CharacterStateEvent | null;
  pending: boolean;
}

export interface CharacterRendererAdapter {
  kind: "placeholder" | "live2d";
  Render: (props: CharacterRendererProps) => JSX.Element;
}

function PlaceholderRenderer({
  persona,
  currentEvent,
  pending
}: CharacterRendererProps) {
  return (
    <div style={styles.figure}>
      <div style={styles.halo} />
      <div style={styles.avatar}>
        <span>{persona.name.slice(0, 1)}</span>
      </div>
      <div style={styles.badges}>
        <span style={styles.badge}>
          {pending ? "thinking" : currentEvent?.emotion ?? persona.defaultSpeechStyle}
        </span>
        <span style={styles.badge}>{currentEvent?.action ?? "idle"}</span>
      </div>
    </div>
  );
}

export const placeholderCharacterRenderer: CharacterRendererAdapter = {
  kind: "placeholder",
  Render: PlaceholderRenderer
};

const styles: Record<string, CSSProperties> = {
  figure: {
    position: "relative",
    marginTop: 24,
    minHeight: 280,
    display: "grid",
    placeItems: "center",
    overflow: "hidden",
    borderRadius: 28,
    background: "radial-gradient(circle at top, rgba(197,92,59,0.24), transparent 40%), rgba(255,255,255,0.6)",
    border: "1px solid var(--border)"
  },
  halo: {
    position: "absolute",
    width: 220,
    height: 220,
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(255,219,192,0.9), rgba(255,219,192,0))"
  },
  avatar: {
    position: "relative",
    width: 162,
    height: 162,
    borderRadius: "50%",
    display: "grid",
    placeItems: "center",
    fontSize: 56,
    fontFamily: "var(--font-display), sans-serif",
    color: "white",
    background: "linear-gradient(160deg, var(--accent), #f19b6b)"
  },
  badges: {
    position: "absolute",
    bottom: 20,
    display: "flex",
    gap: 10
  },
  badge: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(45,36,31,0.78)",
    color: "white",
    fontSize: 13
  }
};
