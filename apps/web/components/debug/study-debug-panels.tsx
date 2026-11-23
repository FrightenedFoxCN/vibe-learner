"use client";

import type {
  DocumentRecord,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import styles from "./study-debug-panels.module.css";

interface StudyDebugPanelsProps {
  document: DocumentRecord | null;
  persona: PersonaProfile | null;
  session: StudySessionRecord | null;
  response: StudyChatResponse | null;
}

export function StudyDebugPanels({
  document,
  persona,
  session,
  response,
}: StudyDebugPanelsProps) {
  if (!session) {
    return <DebugEmptyState message="暂无会话" />;
  }

  const latestTurn = session.turns[session.turns.length - 1] ?? null;
  const latestCharacterEvents = response?.characterEvents.length
    ? response.characterEvents
    : (latestTurn?.characterEvents ?? []);
  const latestPersonaTrace = response?.personaSlotTrace?.length
    ? response.personaSlotTrace
    : (latestTurn?.personaSlotTrace ?? []);
  const latestMemoryTrace = response?.memoryTrace?.length
    ? response.memoryTrace
    : (latestTurn?.memoryTrace ?? []);
  const latestToolCalls = response?.toolCalls?.length
    ? response.toolCalls
    : (latestTurn?.toolCalls ?? []);
  const latestModelRecoveries = response?.modelRecoveries?.length
    ? response.modelRecoveries
    : (latestTurn?.modelRecoveries ?? []);
  const latestSceneProfile =
    response?.sceneProfile ?? latestTurn?.sceneProfile ?? session.sceneProfile ?? null;

  return (
    <div className={styles.stack}>
      <section className={styles.card}>
        <div className={styles.sectionHead}>
          <div className={styles.headerCopy}>
            <span className={styles.title}>对话上下文</span>
            <span className={styles.caption}>
              {document?.title ?? session.documentId} ·{" "}
              {persona?.name ?? session.personaId}
            </span>
          </div>
          <span className={styles.badge}>turns: {session.turns.length}</span>
        </div>
        <div className={styles.metaGrid}>
          <MetaItem label="Session" value={session.id} />
          <MetaItem label="Scene Instance" value={session.sceneInstanceId || "-"} />
          <MetaItem
            label="Study Unit"
            value={session.studyUnitTitle || session.studyUnitId}
          />
          <MetaItem label="Theme" value={session.themeHint || "-"} />
          <MetaItem label="Status" value={session.status} />
        </div>
        {latestSceneProfile ? (
          <div className={styles.sceneCard}>
            <strong>{latestSceneProfile.title}</strong>
            <span className={styles.caption}>
              {latestSceneProfile.sceneName || "未命名场景"} ·{" "}
              {latestSceneProfile.selectedPath.join(" / ") || "未定位路径"}
            </span>
            <span className={styles.bodyText}>{latestSceneProfile.summary}</span>
          </div>
        ) : null}
        {session.sessionSystemPrompt ? (
          <details className={styles.detailBlock}>
            <summary className={styles.summary}>系统提示词</summary>
            <pre className={styles.pre}>{session.sessionSystemPrompt}</pre>
          </details>
        ) : null}
      </section>

      <details className={styles.card} open>
        <summary className={styles.summary}>最新角色事件</summary>
        {latestCharacterEvents.length ? (
          <pre className={styles.pre}>
            {JSON.stringify(latestCharacterEvents, null, 2)}
          </pre>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card} open>
        <summary className={styles.summary}>本轮恢复记录</summary>
        {latestModelRecoveries.length ? (
          <div className={styles.list}>
            {latestModelRecoveries.map((item) => (
              <div key={item.recoveryId} className={styles.itemCard}>
                <strong>{item.reason}</strong>
                <span className={styles.caption}>
                  {item.strategy} · attempts {item.attempts}
                </span>
                {item.note ? (
                  <span className={styles.bodyText}>{item.note}</span>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card} open>
        <summary className={styles.summary}>本轮工具调用</summary>
        {latestToolCalls.length ? (
          <div className={styles.list}>
            {latestToolCalls.map((toolCall, index) => (
              <div key={`${toolCall.toolCallId}:${index}`} className={styles.itemCard}>
                <strong>{toolCall.toolName}</strong>
                <span className={styles.caption}>
                  {toolCall.resultSummary || "无结果摘要"}
                </span>
                <pre className={styles.pre}>{toolCall.argumentsJson}</pre>
                <pre className={styles.pre}>{toolCall.resultJson}</pre>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card} open>
        <summary className={styles.summary}>本轮参考人格插槽</summary>
        {latestPersonaTrace.length ? (
          <div className={styles.list}>
            {latestPersonaTrace.map((item, index) => (
              <div key={`${item.kind}:${index}`} className={styles.itemCard}>
                <strong>{item.label}</strong>
                <span className={styles.caption}>{item.reason}</span>
                <span className={styles.bodyText}>{item.contentExcerpt}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card} open>
        <summary className={styles.summary}>记忆检索命中</summary>
        {latestMemoryTrace.length ? (
          <div className={styles.list}>
            {latestMemoryTrace.map((hit, index) => (
              <div key={`${hit.sessionId}:${index}`} className={styles.itemCard}>
                <strong>
                  {hit.sceneTitle || "未设置场景"} · {hit.studyUnitId}
                </strong>
                <span className={styles.caption}>
                  score: {hit.score.toFixed(4)} ·{" "}
                  {hit.source === "tool_call" ? "tool" : "retriever"}
                </span>
                <span className={styles.bodyText}>{hit.snippet}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>对话调试历史</summary>
        {session.turns.length ? (
          <div className={styles.list}>
            {[...session.turns].reverse().map((turn, index) => (
              <div key={`${turn.createdAt}:${index}`} className={styles.itemCard}>
                <strong>{truncateText(turn.learnerMessage, 120)}</strong>
                <span className={styles.caption}>
                  {formatTimestamp(turn.createdAt, { style: "debug" })} · citations{" "}
                  {turn.citations.length} · character events{" "}
                  {turn.characterEvents.length}
                </span>
                <span className={styles.bodyText}>
                  {truncateText(turn.assistantReply, 220)}
                </span>
                <div className={styles.tagRow}>
                  <span className={styles.tag}>
                    persona trace {turn.personaSlotTrace?.length ?? 0}
                  </span>
                  <span className={styles.tag}>
                    memory trace {turn.memoryTrace?.length ?? 0}
                  </span>
                  {turn.interactiveQuestion ? (
                    <span className={styles.tag}>interactive question</span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaItem}>
      <span className={styles.caption}>{label}</span>
      <strong className={styles.metaValue}>{value}</strong>
    </div>
  );
}

function DebugEmptyState({ message }: { message: string }) {
  return <p className={styles.empty}>{message}</p>;
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}
