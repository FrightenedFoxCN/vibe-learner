import type { CSSProperties, JSX } from "react";
import type { CharacterStateEvent, PersonaProfile } from "@vibe-learner/shared";

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
      <div style={styles.avatar}>
        <span>{persona.name.slice(0, 1)}</span>
      </div>
      <div style={styles.badges}>
        <span style={styles.badge}>
          {pending ? "思考中" : currentEvent?.emotion ?? persona.defaultSpeechStyle}
        </span>
        <span style={styles.badge}>{currentEvent?.action ?? "待机"}</span>
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
    minHeight: 200,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    background: "var(--panel)",
    border: "1px solid var(--border)",
    padding: "24px 16px",
  },
  avatar: {
    width: 80,
    height: 80,
    background: "var(--accent)",
    display: "grid",
    placeItems: "center",
    fontSize: 32,
    color: "white",
    fontWeight: 700,
  },
  badges: {
    display: "flex",
    gap: 8,
  },
  badge: {
    padding: "4px 10px",
    background: "var(--ink)",
    color: "white",
    fontSize: 12,
    fontWeight: 500,
  },
};
