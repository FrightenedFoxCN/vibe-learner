import type { StudyConsoleProps } from "./study-console-types";
import { formatToolName } from "./study-console-format";

type StudyPlanConfirmationsProps = Pick<
  StudyConsoleProps,
  "planConfirmations" | "onResolvePlanConfirmation" | "disabled" | "isPending"
>;

export function StudyPlanConfirmations({
  planConfirmations,
  onResolvePlanConfirmation,
  disabled,
  isPending,
}: StudyPlanConfirmationsProps) {
  const pendingConfirmations =
    planConfirmations?.filter((item) => item.status === "pending") ?? [];
  if (!pendingConfirmations.length) return null;

  return (
    <div className="study-console-confirmation-stack">
      {pendingConfirmations.map((item) => (
        <div key={item.id} className="study-console-confirmation-card">
          <div className="study-console-confirmation-head">
            <span className="study-console-confirmation-title">{item.title}</span>
            <span className="study-console-confirmation-meta">
              {formatToolName(item.toolName)}
            </span>
          </div>
          <p className="study-console-confirmation-summary">
            {item.summary || "请确认这项调整。"}
          </p>
          {item.previewLines.length ? (
            <div className="study-console-confirmation-lines">
              {item.previewLines.map((line, index) => (
                <span
                  key={`${item.id}:${index}`}
                  className="study-console-confirmation-line"
                >
                  {line}
                </span>
              ))}
            </div>
          ) : null}
          <div className="study-console-confirmation-actions">
            <button
              type="button"
              className="study-console-confirm-approve-btn study-console-btn-disabled"
              disabled={disabled || isPending || !onResolvePlanConfirmation}
              onClick={() => {
                if (onResolvePlanConfirmation)
                  void onResolvePlanConfirmation({
                    confirmationId: item.id,
                    decision: "approve",
                  });
              }}
            >
              确认应用
            </button>
            <button
              type="button"
              className="study-console-confirm-reject-btn study-console-btn-disabled"
              disabled={disabled || isPending || !onResolvePlanConfirmation}
              onClick={() => {
                if (onResolvePlanConfirmation)
                  void onResolvePlanConfirmation({
                    confirmationId: item.id,
                    decision: "reject",
                  });
              }}
            >
              暂不应用
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
