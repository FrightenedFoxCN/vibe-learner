"use client";

import type {
  DocumentRecord,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";
import type { CSSProperties } from "react";

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
  response
}: StudyDebugPanelsProps) {
  if (!session) {
    return <DebugEmptyState message="暂无会话" />;
  }

  const latestTurn = session.turns[session.turns.length - 1] ?? null;
  const latestCharacterEvents = response?.characterEvents.length
    ? response.characterEvents
    : latestTurn?.characterEvents ?? [];
  const latestPersonaTrace = response?.personaSlotTrace?.length
    ? response.personaSlotTrace
    : latestTurn?.personaSlotTrace ?? [];
  const latestMemoryTrace = response?.memoryTrace?.length
    ? response.memoryTrace
    : latestTurn?.memoryTrace ?? [];
  const latestToolCalls = response?.toolCalls?.length
    ? response.toolCalls
    : latestTurn?.toolCalls ?? [];
  const latestModelRecoveries = response?.modelRecoveries?.length
    ? response.modelRecoveries
    : latestTurn?.modelRecoveries ?? [];
  const latestSceneProfile = response?.sceneProfile ?? latestTurn?.sceneProfile ?? session.sceneProfile ?? null;

  return (
    <div style={styles.stack}>
      <section style={styles.card}>
        <div style={styles.sectionHead}>
          <div style={styles.headerCopy}>
            <span style={styles.title}>对话上下文</span>
            <span style={styles.caption}>
              {document?.title ?? session.documentId} · {persona?.name ?? session.personaId}
            </span>
          </div>
          <span style={styles.badge}>turns: {session.turns.length}</span>
        </div>
        <div style={styles.metaGrid}>
          <MetaItem label="Session" value={session.id} />
          <MetaItem label="Scene Instance" value={session.sceneInstanceId || "-"} />
          <MetaItem label="Section" value={session.sectionTitle || session.sectionId} />
          <MetaItem label="Theme" value={session.themeHint || "-"} />
          <MetaItem label="Status" value={session.status} />
        </div>
        {latestSceneProfile ? (
          <div style={styles.sceneCard}>
            <strong>{latestSceneProfile.title}</strong>
            <span style={styles.caption}>
              {latestSceneProfile.sceneName || "未命名场景"} · {latestSceneProfile.selectedPath.join(" / ") || "未定位路径"}
            </span>
            <span style={styles.bodyText}>{latestSceneProfile.summary}</span>
          </div>
        ) : null}
        {session.sessionSystemPrompt ? (
          <details style={styles.detailBlock}>
            <summary style={styles.summary}>系统提示词</summary>
            <pre style={styles.pre}>{session.sessionSystemPrompt}</pre>
          </details>
        ) : null}
      </section>

      <details style={styles.card} open>
        <summary style={styles.summary}>最新角色事件</summary>
        {latestCharacterEvents.length ? (
          <pre style={styles.pre}>{JSON.stringify(latestCharacterEvents, null, 2)}</pre>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details style={styles.card} open>
        <summary style={styles.summary}>本轮恢复记录</summary>
        {latestModelRecoveries.length ? (
          <div style={styles.list}>
            {latestModelRecoveries.map((item) => (
              <div key={item.recoveryId} style={styles.itemCard}>
                <strong>{item.reason}</strong>
                <span style={styles.caption}>{item.strategy} · attempts {item.attempts}</span>
                {item.note ? <span style={styles.bodyText}>{item.note}</span> : null}
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details style={styles.card} open>
        <summary style={styles.summary}>本轮工具调用</summary>
        {latestToolCalls.length ? (
          <div style={styles.list}>
            {latestToolCalls.map((toolCall, index) => (
              <div key={`${toolCall.toolCallId}:${index}`} style={styles.itemCard}>
                <strong>{toolCall.toolName}</strong>
                <span style={styles.caption}>{toolCall.resultSummary || "无结果摘要"}</span>
                <pre style={styles.pre}>{toolCall.argumentsJson}</pre>
                <pre style={styles.pre}>{toolCall.resultJson}</pre>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details style={styles.card} open>
        <summary style={styles.summary}>本轮参考人格插槽</summary>
        {latestPersonaTrace.length ? (
          <div style={styles.list}>
            {latestPersonaTrace.map((item, index) => (
              <div key={`${item.kind}:${index}`} style={styles.itemCard}>
                <strong>{item.label}</strong>
                <span style={styles.caption}>{item.reason}</span>
                <span style={styles.bodyText}>{item.contentExcerpt}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details style={styles.card} open>
        <summary style={styles.summary}>记忆检索命中</summary>
        {latestMemoryTrace.length ? (
          <div style={styles.list}>
            {latestMemoryTrace.map((hit, index) => (
              <div key={`${hit.sessionId}:${index}`} style={styles.itemCard}>
                <strong>{hit.sceneTitle || "未设置场景"} · {hit.sectionId}</strong>
                <span style={styles.caption}>
                  score: {hit.score.toFixed(4)} · {hit.source === "tool_call" ? "tool" : "retriever"}
                </span>
                <span style={styles.bodyText}>{hit.snippet}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>对话调试历史</summary>
        {session.turns.length ? (
          <div style={styles.list}>
            {[...session.turns].reverse().map((turn, index) => (
              <div key={`${turn.createdAt}:${index}`} style={styles.itemCard}>
                <strong>{truncateText(turn.learnerMessage, 120)}</strong>
                <span style={styles.caption}>
                  {formatDateTime(turn.createdAt)} · citations {turn.citations.length} · character events {turn.characterEvents.length}
                </span>
                <span style={styles.bodyText}>{truncateText(turn.assistantReply, 220)}</span>
                <div style={styles.tagRow}>
                  <span style={styles.tag}>persona trace {turn.personaSlotTrace?.length ?? 0}</span>
                  <span style={styles.tag}>memory trace {turn.memoryTrace?.length ?? 0}</span>
                  {turn.interactiveQuestion ? <span style={styles.tag}>interactive question</span> : null}
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
    <div style={styles.metaItem}>
      <span style={styles.caption}>{label}</span>
      <strong style={styles.metaValue}>{value}</strong>
    </div>
  );
}

function DebugEmptyState({ message }: { message: string }) {
  return <p style={styles.empty}>{message}</p>;
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

const styles: Record<string, CSSProperties> = {
  stack: {
    display: "grid",
    gap: 12
  },
  card: {
    border: "1px solid var(--border)",
    background: "var(--bg)",
    borderRadius: 16,
    padding: "14px 16px"
  },
  sectionHead: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap"
  },
  headerCopy: {
    display: "grid",
    gap: 4
  },
  title: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)"
  },
  badge: {
    fontSize: 11,
    fontWeight: 600,
    padding: "4px 8px",
    borderRadius: 999,
    background: "var(--accent-soft)",
    color: "var(--accent)"
  },
  metaGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: 10,
    marginTop: 14
  },
  metaItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  metaValue: {
    fontSize: 13,
    color: "var(--ink-2)",
    wordBreak: "break-word"
  },
  detailBlock: {
    marginTop: 12
  },
  sceneCard: {
    display: "grid",
    gap: 4,
    marginTop: 12,
    padding: "12px 14px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  summary: {
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    color: "var(--ink)"
  },
  list: {
    display: "grid",
    gap: 10,
    marginTop: 12
  },
  itemCard: {
    display: "grid",
    gap: 6,
    padding: "12px 14px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  tagRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap"
  },
  tag: {
    fontSize: 11,
    padding: "4px 8px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink-2)"
  },
  pre: {
    margin: "12px 0 0",
    padding: "10px 12px",
    borderRadius: 10,
    background: "var(--panel)",
    border: "1px solid var(--border)",
    whiteSpace: "pre-wrap",
    overflowX: "auto",
    fontSize: 11,
    lineHeight: 1.6,
    fontFamily: "var(--font-mono)"
  },
  caption: {
    fontSize: 12,
    color: "var(--muted)"
  },
  bodyText: {
    fontSize: 13,
    color: "var(--ink-2)",
    lineHeight: 1.6
  },
  empty: {
    margin: "12px 0 0",
    fontSize: 13,
    color: "var(--muted)"
  }
};
