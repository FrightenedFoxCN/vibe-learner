import type { CSSProperties } from "react";
import type { PersonaProfile } from "@gal-learner/shared";

interface PersonaSelectorProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onChange: (personaId: string) => void;
  compact?: boolean;
}

export function PersonaSelector({
  personas,
  selectedPersonaId,
  onChange,
  compact = false
}: PersonaSelectorProps) {
  if (compact) {
    return (
      <select
        value={selectedPersonaId}
        onChange={(event) => onChange(event.target.value)}
        style={styles.selectCompact}
      >
        {personas.map((persona) => (
          <option key={persona.id} value={persona.id}>
            {persona.name}
          </option>
        ))}
      </select>
    );
  }

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
    minWidth: 220,
    padding: 14,
    borderRadius: 6,
    border: "1px solid var(--border)",
    background: "var(--panel-strong)",
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
    minHeight: 40,
    borderRadius: 4,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "var(--panel-strong)",
    color: "var(--ink)"
  },
  selectCompact: {
    height: 32,
    borderRadius: 4,
    border: "1px solid var(--border)",
    padding: "0 8px",
    background: "var(--panel-strong)",
    color: "var(--ink)",
    fontSize: 13
  }
};
