import {
  tavernAutomaticRecoveryDelay,
  type TavernPendingRecoveryProgress,
} from "../../lib/tavern-pending-recovery";

export function TavernPendingRecovery({
  progress,
  busy,
  onRetry,
}: {
  progress: TavernPendingRecoveryProgress;
  busy: boolean;
  onRetry: () => void;
}) {
  const notice = progress.inFlight
    ? "正在恢复本轮互动…"
    : tavernAutomaticRecoveryDelay(progress) === null
      ? "本轮自动恢复已停止，可以手动恢复。"
      : "暂未确认本轮互动已恢复；稍后会再次自动尝试。";
  return (
    <section className="tavern-panel" aria-label="中断互动恢复">
      <p className="tavern-panel-footnote" role="status">
        {notice} 已提交的消息会保留。
      </p>
      <button
        type="button"
        className="tavern-button secondary"
        disabled={busy || progress.inFlight}
        onClick={onRetry}
      >
        手动恢复本轮互动
      </button>
    </section>
  );
}
