import type { StudyConsoleProps } from "./study-console-types";

type StudyStatusStripProps = Pick<
  StudyConsoleProps,
  "isPending" | "disabled" | "chatErrorMessage"
>;

export function StudyStatusStrip({
  isPending,
  disabled,
  chatErrorMessage,
}: StudyStatusStripProps) {
  return (
    <div className="study-console-status-strip" aria-label="会话状态">
      <StudyStatusItem
        label="会话"
        value={disabled ? "未创建" : "已建立"}
        kind="session"
      />
      <StudyStatusItem
        label="记录同步"
        value={
          chatErrorMessage
            ? "需要确认"
            : isPending
              ? "等待结果"
              : disabled
                ? "未开始"
                : "已同步"
        }
        kind="sync"
      />
      <StudyStatusItem
        label="模型"
        value={isPending ? "生成中" : "空闲"}
        kind="model"
      />
    </div>
  );
}

function StudyStatusItem({
  label,
  value,
  kind,
}: {
  label: string;
  value: string;
  kind: "session" | "sync" | "model";
}) {
  return (
    <span className="study-console-status-item" data-study-status={kind}>
      <span className="study-console-status-label">{label}</span>
      <span className="study-console-status-value">{value}</span>
    </span>
  );
}

type StudyChatRecoveryProps = Pick<
  StudyConsoleProps,
  | "isPending"
  | "disabled"
  | "chatErrorMessage"
  | "chatOperationStatus"
  | "canQueryLastAsk"
  | "canResendLastAsk"
  | "canRefreshSessionAfterAsk"
  | "onQueryLastAsk"
  | "onRetryLastAsk"
  | "onRefreshSessionAfterAsk"
>;

export function StudyChatRecovery({
  isPending,
  disabled,
  chatErrorMessage,
  chatOperationStatus,
  canQueryLastAsk,
  canResendLastAsk,
  canRefreshSessionAfterAsk,
  onQueryLastAsk,
  onRetryLastAsk,
  onRefreshSessionAfterAsk,
}: StudyChatRecoveryProps) {
  if (!chatErrorMessage) return null;

  return (
    <div className="study-console-error-box" role="status" aria-live="polite">
      <span className="study-console-error-title">
        {chatOperationStatus === "not_committed"
          ? "已确认本次回复未保存"
          : chatOperationStatus === "admitted" || chatOperationStatus === "running"
            ? "仍在等待本次回复"
            : "本次对话需要确认"}
      </span>
      <span className="study-console-error-text">{chatErrorMessage}</span>
      {canQueryLastAsk ? (
        <button
          type="button"
          className="study-console-retry-btn study-console-btn-disabled"
          disabled={isPending || disabled || !onQueryLastAsk}
          onClick={() => {
            if (onQueryLastAsk) void onQueryLastAsk();
          }}
        >
          {isPending ? "查询中…" : "查询本次请求结果"}
        </button>
      ) : null}
      {canResendLastAsk ? (
        <button
          type="button"
          className="study-console-retry-btn study-console-btn-disabled"
          disabled={isPending || disabled || !onRetryLastAsk}
          onClick={() => {
            if (onRetryLastAsk) void onRetryLastAsk();
          }}
        >
          {isPending ? "发送中…" : "重新发送（新请求）"}
        </button>
      ) : null}
      {canRefreshSessionAfterAsk ? (
        <button
          type="button"
          className="study-console-retry-btn study-console-btn-disabled"
          disabled={isPending || disabled || !onRefreshSessionAfterAsk}
          onClick={() => {
            if (onRefreshSessionAfterAsk) void onRefreshSessionAfterAsk();
          }}
        >
          {isPending ? "刷新中…" : "刷新会话状态"}
        </button>
      ) : null}
    </div>
  );
}
