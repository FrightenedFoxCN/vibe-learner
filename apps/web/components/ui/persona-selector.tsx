import type { PersonaProfile } from "@vibe-learner/shared";

interface PersonaSelectorProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onChange: (personaId: string) => void;
  compact?: boolean;
  selectId?: string;
}

export function PersonaSelector({
  personas,
  selectedPersonaId,
  onChange,
  compact = false,
  selectId,
}: PersonaSelectorProps) {
  const selectedPersona =
    personas.find((persona) => persona.id === selectedPersonaId) ?? personas[0] ?? null;

  if (compact) {
    return (
      <div className="grid gap-2">
        <select
          id={selectId}
          value={selectedPersonaId}
          onChange={(event) => onChange(event.target.value)}
          className="h-11 w-full border border-border bg-panel px-2.5 text-sm text-ink"
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
    <aside className="min-w-[220px] rounded-md border border-border bg-panel-strong p-3.5">
      <p className="mt-0 mb-1.5 text-xs font-semibold tracking-[0.04em] text-muted">
        教师人格
      </p>
      <select
        id={selectId}
        value={selectedPersonaId}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 w-full rounded-sm border border-border bg-panel-strong px-2.5 py-2 text-ink"
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

function PersonaMiniCard({
  persona,
  compact = false,
}: {
  persona: PersonaProfile;
  compact?: boolean;
}) {
  return (
    <div
      className={`grid border border-border bg-bg ${compact ? "gap-1.5 p-2.5" : "gap-2 p-3"}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[13px] font-bold text-ink">{persona.name}</span>
        <span className="text-[11px] text-muted">
          {persona.source === "builtin" ? "内置" : "用户扩展"}
        </span>
      </div>
      <p className="m-0 text-xs leading-normal text-muted">
        {persona.summary || "未填写摘要"}
      </p>
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2 gap-y-1">
        <span className="text-[11px] tracking-[0.04em] text-muted">关系</span>
        <span className="text-xs text-ink">{persona.relationship || "未填写"}</span>
        <span className="text-[11px] tracking-[0.04em] text-muted">称呼</span>
        <span className="text-xs text-ink">{persona.learnerAddress || "未填写"}</span>
      </div>
    </div>
  );
}
