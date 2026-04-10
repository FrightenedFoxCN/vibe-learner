import type { CSSProperties } from "react";
import type { PersonaProfile } from "@gal-learner/shared";

interface PersonaSelectorProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onChange: (personaId: string) => void;
}

export function PersonaSelector({
  personas,
  selectedPersonaId,
  onChange
}: PersonaSelectorProps) {
  return (
    <aside style={styles.wrap}>
      <p style={styles.label}>教师人格</p>
      <select
        value={selectedPersonaId}
        onChange={(event) => onChange(event.target.value)}
        style={styles.select}
      >
        {personas.map((persona) => (
          <option key={persona.id} value={persona.id}>
            {persona.name} · {persona.source === "builtin" ? "内置" : "用户扩展"}
          </option>
        ))}
      </select>
    </aside>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    minWidth: 240,
    padding: 16,
    borderRadius: 20,
    border: "1px solid var(--border)",
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow-soft)"
  },
  label: {
    margin: "0 0 6px",
    color: "var(--muted)",
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: "0.04em"
  },
  select: {
    width: "100%",
    minHeight: 44,
    borderRadius: 12,
    border: "1px solid var(--border)",
    padding: "10px 12px",
    background: "rgba(255,255,255,0.98)",
    color: "var(--ink)"
  }
};
