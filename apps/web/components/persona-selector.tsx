import type { CSSProperties } from "react";
import type { PersonaProfile } from "@vibe-learner/shared";

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
  const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId) ?? personas[0] ?? null;

  if (compact) {
    return (
      <div style={styles.compactWrap}>
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
        {selectedPersona ? <PersonaMiniCard persona={selectedPersona} compact /> : null}
      </div>
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
      {selectedPersona ? <PersonaMiniCard persona={selectedPersona} /> : null}
    </aside>
  );
}

function PersonaMiniCard({ persona, compact = false }: { persona: PersonaProfile; compact?: boolean }) {
  return (
    <div style={{ ...styles.card, ...(compact ? styles.cardCompact : {}) }}>
      <div style={styles.cardHead}>
        <span style={styles.cardName}>{persona.name}</span>
        <span style={styles.cardSource}>{persona.source === "builtin" ? "内置" : "用户扩展"}</span>
      </div>
      <p style={styles.cardSummary}>{persona.summary || "未填写摘要"}</p>
      <div style={styles.cardMetaGrid}>
        <span style={styles.cardMetaLabel}>关系</span>
        <span style={styles.cardMetaValue}>{persona.relationship || "未填写"}</span>
        <span style={styles.cardMetaLabel}>称呼</span>
        <span style={styles.cardMetaValue}>{persona.learnerAddress || "未填写"}</span>
      </div>
    </div>
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
  compactWrap: {
    display: "grid",
    gap: 8
  },
  selectCompact: {
    width: "100%",
    height: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    padding: "0 10px",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    fontSize: 14
  },
  card: {
    display: "grid",
    gap: 8,
    padding: 12,
    borderRadius: 10,
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 84%, var(--panel-strong))"
  },
  cardCompact: {
    padding: 10,
    gap: 6
  },
  cardHead: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap"
  },
  cardName: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  cardSource: {
    fontSize: 11,
    color: "var(--muted)"
  },
  cardSummary: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--muted)"
  },
  cardMetaGrid: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: "4px 8px",
    alignItems: "center"
  },
  cardMetaLabel: {
    fontSize: 11,
    color: "var(--muted)",
    letterSpacing: "0.04em"
  },
  cardMetaValue: {
    fontSize: 12,
    color: "var(--ink)"
  }
};
