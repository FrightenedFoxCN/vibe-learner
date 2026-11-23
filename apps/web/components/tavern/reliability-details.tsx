import type {
  TavernParticipant,
  TavernRun,
  TavernRunRecoveryChain,
} from "@vibe-learner/shared";
import {
  RUN_STATUS_LABELS,
  STEP_STATUS_LABELS,
  TAVERN_COPY,
} from "../../lib/tavern-copy";
import { formatShortTime } from "./tavern-format";

export function ReliabilityDetails({
  runs,
  retryableRuns,
  recoveryChains,
  participants,
  roomActive,
  busy,
  onRetry,
}: {
  runs: TavernRun[];
  retryableRuns: TavernRun[];
  recoveryChains: TavernRunRecoveryChain[];
  participants: TavernParticipant[];
  roomActive: boolean;
  busy: boolean;
  onRetry: (run: TavernRun) => void;
}) {
  const retryableIds = new Set(retryableRuns.map((run) => run.id));
  const recoveredRootIds = new Set(
    recoveryChains
      .filter((chain) => chain.chainStatus === "recovered")
      .map((chain) => chain.rootRunId),
  );
  const names = new Map(
    participants.map((participant) => [
      participant.personaId,
      participant.displayName || "未命名角色",
    ]),
  );
  return (
    <details className="tavern-panel reliability-details">
      <summary>
        <span>
          <span className="tavern-kicker">Reliability Details</span>
          <strong>可靠性摘要</strong>
        </span>
        <span
          className="tavern-count"
          aria-label={`${retryableRuns.length} 个待恢复项`}
        >
          待恢复 {retryableRuns.length}
        </span>
      </summary>
      <div className="tavern-reliability-content">
        <p className="tavern-panel-footnote">
          这里只显示可读恢复摘要；完整 Harness trace 可在全局调试层查看。
        </p>
        {runs.length ? (
          runs.slice(0, 12).map((run) => {
            const repairCount = [
              ...run.harnessTrace,
              ...run.speakerSteps.flatMap((step) =>
                step.harnessTrace ? [step.harnessTrace] : [],
              ),
            ].filter((trace) => trace.status === "repaired").length;
            return (
              <div className="tavern-run-summary" key={run.id}>
                <div className="tavern-run-title-row">
                  <strong>{RUN_STATUS_LABELS[run.status]}</strong>
                  <span>
                    {run.mode === "direct" ? "单角色" : "多人引导"} ·{" "}
                    {formatShortTime(run.createdAt)}
                  </span>
                </div>
                <ul>
                  {run.speakerSteps.map((step) => (
                    <li key={`${run.id}-${step.stepIndex}`}>
                      <span>{names.get(step.personaId) || "房间角色"}</span>
                      <span>
                        {step.status === "blocked"
                          ? TAVERN_COPY.blocked
                          : STEP_STATUS_LABELS[step.status]}
                      </span>
                    </li>
                  ))}
                </ul>
                {repairCount ? (
                  <p className="tavern-repair-note">
                    本轮有 {repairCount} 项输出经校验后自动修正。
                  </p>
                ) : null}
                {retryableIds.has(run.id) ? (
                  <button
                    type="button"
                    className="tavern-button secondary full"
                    onClick={() => onRetry(run)}
                    disabled={!roomActive || busy}
                  >
                    仅重试未完成角色
                  </button>
                ) : recoveredRootIds.has(run.id) ? (
                  <p className="tavern-repair-note">
                    该部分结果已由后续范围重试完整恢复。
                  </p>
                ) : run.parentRunId ? (
                  <p className="tavern-repair-note">{TAVERN_COPY.retryScope}</p>
                ) : null}
              </div>
            );
          })
        ) : (
          <p className="tavern-empty-copy">
            发起互动后，这里会显示每位角色的生成与恢复结果。
          </p>
        )}
      </div>
    </details>
  );
}
