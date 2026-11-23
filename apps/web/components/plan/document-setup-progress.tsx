import { useState } from "react";
import { formatElapsedMs } from "../../lib/format";
import {
  formatPlanStreamStatus,
  formatProcessError,
  formatProcessStreamStatus,
  formatRoundStatus,
  summarizePlanRounds,
  summarizeProcessProgress,
  type StreamEventItem,
} from "./document-setup-stream-summary";
import styles from "./document-setup.module.css";

interface StreamProgressProps {
  events: StreamEventItem[];
  status: string;
}

export function DocumentProcessingProgress({ events, status }: StreamProgressProps) {
  const progress = summarizeProcessProgress(events);
  return (
    <div className={styles.progressSection} aria-live="polite">
      <div className={styles.progressHeader}>
        <div className={styles.progressHeaderMeta}>
          <span className={styles.progressTitle}>教材解析 / OCR</span>
        </div>
        <span className={styles.progressStat} data-status={status}>
          {formatProcessStreamStatus(status)}
        </span>
      </div>
      <div className={styles.progressStats}>
        <span className={styles.progressStat}>
          页面 {progress.completedPages}
          {progress.totalPages ? ` / ${progress.totalPages}` : ""}
        </span>
        <span className={styles.progressStat}>阶段 {progress.phase}</span>
        {progress.rate ? (
          <span className={styles.progressStat}>速率 {progress.rate} 页/分钟</span>
        ) : null}
        {progress.eta ? (
          <span className={styles.progressStat}>预计还需 {progress.eta}</span>
        ) : null}
      </div>
      {progress.warning ? (
        <div className={styles.warningText}>{progress.warning}</div>
      ) : null}
      {progress.error ? (
        <div className={styles.roundError}>
          {formatProcessError(progress.error, progress.checkpointSaved)}
        </div>
      ) : null}
    </div>
  );
}

export function PlanGenerationProgress({ events, status }: StreamProgressProps) {
  const [showRoundDetails, setShowRoundDetails] = useState(false);
  const planRoundSummary = summarizePlanRounds(events);
  if (status === "idle" && !events.length && !planRoundSummary.rounds.length)
    return null;

  return (
    <div className={styles.progressSection}>
      <div className={styles.progressHeader}>
        <div className={styles.progressHeaderMeta}>
          <span className={styles.progressTitle}>生成进度</span>
        </div>
        <span className={styles.progressStat} data-status={status}>
          {formatPlanStreamStatus(status)}
        </span>
      </div>

      <div className={styles.progressStats}>
        <span className={styles.progressStat}>
          轮次 {planRoundSummary.rounds.length}
        </span>
        <span className={styles.progressStat}>
          调用 {planRoundSummary.totalToolCalls}
        </span>
        <span className={styles.progressStat}>
          问题 {planRoundSummary.planningQuestions.length}
        </span>
        <span className={styles.progressStat}>
          Token {planRoundSummary.totalTokens || "—"}
        </span>
        <span className={styles.progressStat}>
          耗时 {formatElapsedMs(planRoundSummary.totalElapsedMs)}
        </span>
        {planRoundSummary.repairCount ? (
          <span className={styles.progressStat}>
            修复 {planRoundSummary.repairCount} 次
          </span>
        ) : null}
      </div>

      {planRoundSummary.latestMessage ? (
        <div className={styles.progressNotice}>{planRoundSummary.latestMessage}</div>
      ) : null}

      {planRoundSummary.planningQuestions.length ? (
        <div className={styles.questionNotice}>
          {planRoundSummary.planningQuestions.map((item) => (
            <div key={item.id} className={styles.questionNoticeItem}>
              <strong className={styles.questionNoticeLabel}>待回答</strong>
              <span>{item.question}</span>
              {item.reason ? (
                <span className={styles.questionNoticeReason}>备注：{item.reason}</span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {planRoundSummary.rounds.length ? (
        <div className={styles.foldSection}>
          <button
            type="button"
            className={styles.foldButton}
            onClick={() => setShowRoundDetails((current) => !current)}
          >
            {showRoundDetails
              ? "收起调用细节"
              : `查看调用细节 · ${planRoundSummary.rounds.length} 轮`}
          </button>

          {showRoundDetails ? (
            <div className={styles.roundList}>
              {planRoundSummary.rounds.map((round) => (
                <div key={round.roundIndex} className={styles.roundCard}>
                  <div className={styles.roundHeader}>
                    <strong className={styles.roundTitle}>
                      第 {round.roundIndex + 1} 轮
                    </strong>
                    <span
                      className={`${styles.progressStat} ${styles.roundStatus}`}
                      data-status={round.status}
                    >
                      {formatRoundStatus(round.status)}
                    </span>
                  </div>
                  <span className={styles.roundMeta}>
                    工具 {round.toolCalls.length}
                    {round.finishReason ? ` · finish=${round.finishReason}` : ""}
                    {typeof round.elapsedMs === "number"
                      ? ` · ${round.elapsedMs} ms`
                      : ""}
                  </span>
                  {round.error ? (
                    <span className={styles.roundError}>出错：{round.error}</span>
                  ) : null}
                  {round.toolCalls.length ? (
                    <div className={styles.roundToolList}>
                      {round.toolCalls.map((toolName, index) => (
                        <span
                          key={`${round.roundIndex}:${toolName}:${index}`}
                          className={styles.roundToolTag}
                        >
                          {toolName}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
