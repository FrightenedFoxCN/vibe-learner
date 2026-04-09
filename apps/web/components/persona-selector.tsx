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
            {persona.name} · {persona.source}
          </option>
        ))}
      </select>
    </aside>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    minWidth: 240,
    padding: 18,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  label: {
    margin: "0 0 8px",
    color: "var(--muted)",
    fontSize: 14
  },
  select: {
    width: "100%",
    borderRadius: 16,
    border: "1px solid var(--border)",
    padding: "12px 14px",
    background: "white"
  }
};
