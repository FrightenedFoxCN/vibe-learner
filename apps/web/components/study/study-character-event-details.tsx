import type { CharacterStateEvent } from "@vibe-learner/shared";
import { collectEventDetails } from "./study-console-format";

export function CharacterEventDetails({ events }: { events: CharacterStateEvent[] }) {
  if (!events.length) {
    return null;
  }

  const detailItems = collectEventDetails(events);
  if (!detailItems.length) {
    return null;
  }

  return (
    <details className="study-console-event-inline" data-study-event-details>
      <summary className="study-console-event-summary">
        表演与工具详情 · {detailItems.length} 项
      </summary>
      <div className="study-console-event-notes">
        {detailItems.map((item, index) => (
          <p
            key={`${item.label}:${item.text}:${index}`}
            className="study-console-event-note-text"
          >
            <span className="study-console-event-note-label">{item.label}</span>
            {item.text}
          </p>
        ))}
      </div>
    </details>
  );
}
