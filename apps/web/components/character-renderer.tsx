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
  const actionText = formatActionText(currentEvent?.action ?? "");
  return (
    <div style={styles.figure}>
      <div style={styles.avatar}>
        <span>{persona.name.slice(0, 1)}</span>
      </div>
      <div style={styles.badges}>
        <span style={styles.badge}>{pending ? "思考中" : currentEvent?.emotion ?? "calm"}</span>
        <span style={styles.badgeAlt}>{currentEvent?.speechStyle ?? persona.defaultSpeechStyle}</span>
      </div>
      {actionText ? <p style={styles.actionLine}>{actionText}</p> : null}
    </div>
  );
}

function formatActionText(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "idle") return "";
  if (normalized === "nod") return "轻轻点头，示意可以继续。";
  if (normalized === "point") return "抬手指向当前重点。";
  if (normalized === "lean_in") return "身体微微前倾，等待回应。";
  if (normalized === "smile") return "嘴角带笑，给出鼓励。";
  if (normalized === "pause") return "短暂停住，像是在整理思路。";
  if (normalized === "write") return "抬手书写比划，标出结构关系。";
  return value.trim();
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
  actionLine: {
    margin: 0,
    maxWidth: 240,
    textAlign: "center",
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--muted)",
  },
  badge: {
    padding: "4px 10px",
    background: "var(--ink)",
    color: "white",
    fontSize: 12,
    fontWeight: 500,
  },
  badgeAlt: {
    padding: "4px 10px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 12,
    fontWeight: 500,
    border: "1px solid var(--border)",
  },
};
