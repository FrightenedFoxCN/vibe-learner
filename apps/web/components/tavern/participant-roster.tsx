import { STEP_STATUS_LABELS } from "../../lib/tavern-copy";
import { projectParticipantStates } from "../../lib/tavern-workspace-state";

export function ParticipantRoster({
  states,
  selectedIds,
  activeReplyIds = [],
  disabled,
  onToggle,
}: {
  states: ReturnType<typeof projectParticipantStates>;
  selectedIds: string[];
  activeReplyIds?: string[];
  disabled: boolean;
  onToggle: (personaId: string) => void;
}) {
  return (
    <section
      className="tavern-panel participant-roster"
      aria-labelledby="participant-roster-title"
    >
      <div className="tavern-panel-heading">
        <h2 id="participant-roster-title">角色与目标</h2>
        <span className="tavern-count">{selectedIds.length} 已选</span>
      </div>
      {states.length ? (
        <div className="tavern-roster-list">
          {states.map(({ participant, state }) => {
            const selected = selectedIds.includes(participant.personaId);
            const displayName = participant.displayName || "未命名角色";
            const stateLabel =
              selected && state === "idle"
                ? activeReplyIds.length &&
                  !activeReplyIds.includes(participant.personaId)
                  ? "下轮目标"
                  : "本轮目标"
                : STEP_STATUS_LABELS[state];
            return (
              <label
                key={participant.personaId}
                className={`tavern-roster-item${selected ? " selected" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onToggle(participant.personaId)}
                />
                <span className="tavern-avatar" aria-hidden="true">
                  {displayName.slice(0, 1)}
                </span>
                <span className="tavern-roster-copy">
                  <strong>{displayName}</strong>
                  <small className={`state-${state}`}>{stateLabel}</small>
                </span>
              </label>
            );
          })}
        </div>
      ) : (
        <p className="tavern-empty-copy">打开房间后在这里选择本轮发言角色。</p>
      )}
      <p className="tavern-panel-footnote">
        选 1 位为单聊；选 2–4 位时，服务器按名册顺序引导讨论。
      </p>
    </section>
  );
}
