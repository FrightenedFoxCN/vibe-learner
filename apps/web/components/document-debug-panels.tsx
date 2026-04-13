"use client";

import type {
  DocumentDebugRecord,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentRecord,
  ModelToolConfig,
  StreamReport
} from "@vibe-learner/shared";
import type { CSSProperties } from "react";

type LiveStreamEvent = {
  stage: string;
  payload: Record<string, unknown>;
};

interface DocumentDebugPanelsProps {
  document: DocumentRecord | null;
  debugRecord: DocumentDebugRecord | null;
  debugRecordError?: string;
  planningContext: DocumentPlanningContext | null;
  planningContextError?: string;
  planningTrace: DocumentPlanningTraceResponse | null;
  planningTraceError?: string;
  modelToolConfig: ModelToolConfig | null;
  modelToolConfigError?: string;
  processReport: StreamReport | null;
  processReportError?: string;
  planReport: StreamReport | null;
  planReportError?: string;
  processLiveDocumentId?: string;
  processLiveEvents?: LiveStreamEvent[];
  processLiveStatus?: string;
  planLiveDocumentId?: string;
  planLiveEvents?: LiveStreamEvent[];
  planLiveStatus?: string;
  loading?: boolean;
  error?: string;
  lastUpdatedAt?: string;
  autoRefreshActive?: boolean;
}

export function DocumentDebugPanels({
  document,
  debugRecord,
  debugRecordError = "",
  planningContext,
  planningContextError = "",
  planningTrace,
  planningTraceError = "",
  modelToolConfig,
  modelToolConfigError = "",
  processReport,
  processReportError = "",
  planReport,
  planReportError = "",
  processLiveDocumentId = "",
  processLiveEvents = [],
  processLiveStatus = "idle",
  planLiveDocumentId = "",
  planLiveEvents = [],
  planLiveStatus = "idle",
  loading = false,
  error = "",
  lastUpdatedAt = "",
  autoRefreshActive = false
}: DocumentDebugPanelsProps) {
  if (!document) {
    return <DebugEmptyState message="当前还没有可检查的教材。先上传教材或切换到已有学习计划。" />;
  }

  const useLiveProcess = processLiveDocumentId === document.id && processLiveEvents.length > 0;
  const useLivePlan = planLiveDocumentId === document.id && planLiveEvents.length > 0;
  const displayProcessEvents = useLiveProcess
    ? processLiveEvents.map((event) => ({ ...event, createdAt: "" }))
    : processReport?.events ?? [];
  const displayPlanEvents = useLivePlan
    ? planLiveEvents.map((event) => ({ ...event, createdAt: "" }))
    : planReport?.events ?? [];
  const displayProcessStatus = useLiveProcess ? processLiveStatus : processReport?.status ?? "idle";
  const displayPlanStatus = useLivePlan ? planLiveStatus : planReport?.status ?? "idle";
  const visibleChunks = debugRecord?.chunks.slice(0, 12) ?? [];
  const visiblePages = debugRecord?.pages.slice(0, 10) ?? [];

  return (
    <div style={styles.stack}>
      <section style={styles.card}>
        <div style={styles.cardHeader}>
          <div style={styles.headerCopy}>
            <span style={styles.cardTitle}>调试总览</span>
            <span style={styles.caption}>{document.title}</span>
          </div>
          <div style={styles.badgeRow}>
            {loading ? <span style={styles.badge}>刷新中</span> : null}
            <span style={styles.badge}>status: {document.status}</span>
            <span style={styles.badge}>debug: {document.debugReady ? "ready" : "pending"}</span>
          </div>
        </div>
        {error ? <p style={styles.error}>{error}</p> : null}
        <div style={styles.statusStrip}>
          <StatusPill label="process" status={displayProcessStatus} />
          <StatusPill label="plan" status={displayPlanStatus} />
          {lastUpdatedAt ? <span style={styles.metaText}>最近刷新：{formatDateTime(lastUpdatedAt)}</span> : null}
          {autoRefreshActive ? <span style={styles.liveText}>自动刷新中</span> : null}
        </div>
        <div style={styles.summaryGrid}>
          <SummaryItem label="Pages" value={String(debugRecord?.pageCount ?? document.pageCount)} />
          <SummaryItem label="Chunks" value={String(debugRecord?.chunks.length ?? document.chunkCount)} />
          <SummaryItem label="Study Units" value={String(debugRecord?.studyUnits.length ?? document.studyUnitCount)} />
          <SummaryItem label="Parser" value={debugRecord?.parserName ?? "-"} />
          <SummaryItem label="Extraction" value={debugRecord?.extractionMethod ?? "-"} />
          <SummaryItem
            label="OCR"
            value={
              debugRecord
                ? debugRecord.ocrApplied
                  ? `yes${debugRecord.ocrLanguage ? ` (${debugRecord.ocrLanguage})` : ""}`
                  : "no"
                : document.ocrStatus
            }
          />
        </div>
      </section>

      <details style={styles.card} open>
        <summary style={styles.summary}>流式处理反馈</summary>
        <StreamPanel
          status={displayProcessStatus}
          events={displayProcessEvents}
          error={processReportError}
          emptyMessage="还没有文档处理流事件。"
        />
      </details>

      <details style={styles.card} open>
        <summary style={styles.summary}>流式生成学习计划</summary>
        <StreamPanel
          status={displayPlanStatus}
          events={displayPlanEvents}
          error={planReportError}
          emptyMessage="还没有计划生成流事件。"
        />
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>章节猜测</summary>
        {debugRecordError ? <PanelError message={debugRecordError} /> : null}
        {debugRecord?.sections.length ? (
          <div style={styles.list}>
            {debugRecord.sections.map((section) => (
              <div key={section.id} style={styles.itemCard}>
                <strong>{section.title || section.id}</strong>
                <span style={styles.caption}>
                  L{section.level} · p.{section.pageStart}–{section.pageEnd}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="当前文档还没有章节猜测结果。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>学习编排清洗结果</summary>
        {debugRecordError ? <PanelError message={debugRecordError} /> : null}
        {debugRecord?.studyUnits.length ? (
          <div style={styles.list}>
            {debugRecord.studyUnits.map((unit) => (
              <div key={unit.id} style={styles.itemCard}>
                <strong>{unit.title}</strong>
                <span style={styles.caption}>
                  p.{unit.pageStart}–{unit.pageEnd} · {unit.unitKind}
                  {unit.includeInPlan ? "" : " · skipped"}
                </span>
                <span style={styles.bodyText}>{truncateText(unit.summary || "暂无摘要。", 220)}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="当前文档还没有学习单元。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>计划输入目录</summary>
        {planningContextError ? <PanelError message={planningContextError} /> : null}
        {planningContext?.courseOutline.length ? (
          <div style={styles.list}>
            {planningContext.courseOutline.map((node) => (
              <div key={node.sectionId} style={styles.itemCard}>
                <strong>{node.title || node.sectionId}</strong>
                <span style={styles.caption}>
                  L{node.level} · p.{node.pageStart}–{node.pageEnd}
                </span>
                {node.children.length ? (
                  <div style={styles.tagRow}>
                    {node.children.map((child) => (
                      <span key={child.sectionId} style={styles.tag}>
                        {child.title}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="还没有计划输入目录。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>计划工具与章节详情</summary>
        {planningContext || modelToolConfig || planningContextError || modelToolConfigError ? (
          <div style={styles.sectionStack}>
            <div style={styles.subSection}>
              <span style={styles.subTitle}>当前可用工具</span>
              {planningContextError ? <PanelError message={planningContextError} /> : null}
              {planningContext?.availableTools.length ? (
                <div style={styles.tagRow}>
                  {planningContext.availableTools.map((tool) => (
                    <span key={tool.name} style={styles.tag}>
                      {tool.name}
                    </span>
                  ))}
                </div>
              ) : (
                <span style={styles.caption}>暂无 planning context 工具清单。</span>
              )}
            </div>
            <div style={styles.subSection}>
              <span style={styles.subTitle}>模型工具开关</span>
              {modelToolConfigError ? <PanelError message={modelToolConfigError} /> : null}
              {modelToolConfig?.stages.length ? (
                <div style={styles.list}>
                  {modelToolConfig.stages.map((stage) => (
                    <div key={stage.name} style={styles.itemCard}>
                      <strong>{stage.label}</strong>
                      <span style={styles.caption}>
                        {stage.stageEnabled ? "runtime on" : "runtime off"} · {stage.name}
                      </span>
                      <div style={styles.tagRow}>
                        {stage.tools.map((tool) => (
                          <span key={tool.name} style={tool.effectiveEnabled ? styles.tag : styles.tagMuted}>
                            {tool.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <span style={styles.caption}>暂无模型工具配置。</span>
              )}
            </div>
            <div style={styles.subSection}>
              <span style={styles.subTitle}>Study Unit Detail</span>
              {planningContextError ? <PanelError message={planningContextError} /> : null}
              {planningContext?.studyUnits.length ? (
                <div style={styles.list}>
                  {planningContext.studyUnits.map((unit) => {
                    const detail = planningContext.detailMap[unit.unitId];
                    return (
                      <div key={unit.unitId} style={styles.itemCard}>
                        <strong>{unit.title}</strong>
                        <span style={styles.caption}>
                          p.{unit.pageStart}–{unit.pageEnd} · detail chunks: {detail?.chunkCount ?? 0}
                        </span>
                        <span style={styles.bodyText}>{truncateText(unit.summary || "暂无摘要。", 180)}</span>
                        {detail?.subsectionTitles.length ? (
                          <div style={styles.tagRow}>
                            {detail.subsectionTitles.map((title, index) => (
                              <span key={`${unit.unitId}:${index}`} style={styles.tag}>
                                {title}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {detail?.chunkExcerpts.length ? (
                          <pre style={styles.preCompact}>{truncateText(detail.chunkExcerpts[0]?.content ?? "", 500)}</pre>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <span style={styles.caption}>暂无章节细节。</span>
              )}
            </div>
          </div>
        ) : (
          <DebugEmptyState message="当前没有可展示的计划工具和章节详情。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>计划模型 Trace</summary>
        {planningTraceError ? <PanelError message={planningTraceError} /> : null}
        {planningTrace?.trace?.rounds.length ? (
          <div style={styles.list}>
            <div style={styles.itemCard}>
              <strong>{planningTrace.trace.model || "unknown model"}</strong>
              <span style={styles.caption}>
                rounds: {planningTrace.summary.roundCount} · tool calls: {planningTrace.summary.toolCallCount}
              </span>
            </div>
            {planningTrace.trace.rounds.map((round) => (
              <div key={`${round.roundIndex}:${round.finishReason}`} style={styles.itemCard}>
                <strong>Round {round.roundIndex + 1}</strong>
                <span style={styles.caption}>
                  {round.finishReason || "no finish reason"} · {round.elapsedMs} ms · timeout {round.timeoutSeconds}s
                </span>
                {round.thinking ? <pre style={styles.preCompact}>{truncateText(round.thinking, 900)}</pre> : null}
                {round.assistantContent ? (
                  <pre style={styles.preCompact}>{truncateText(round.assistantContent, 900)}</pre>
                ) : null}
                {round.toolCalls.length ? (
                  <div style={styles.list}>
                    {round.toolCalls.map((toolCall) => (
                      <div key={toolCall.toolCallId} style={styles.toolCallCard}>
                        <strong>{toolCall.toolName}</strong>
                        <span style={styles.caption}>{toolCall.resultSummary || "无结果摘要"}</span>
                        <pre style={styles.preCompact}>{truncateText(toolCall.argumentsJson, 500)}</pre>
                        <pre style={styles.preCompact}>{truncateText(toolCall.resultJson, 500)}</pre>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无计划模型 trace。先生成一次学习计划。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>解析告警</summary>
        {debugRecord?.warnings.length ? (
          <div style={styles.list}>
            {debugRecord.warnings.map((warning, index) => (
              <div key={`${warning.code}:${index}`} style={styles.itemCard}>
                <strong>{warning.code}</strong>
                <span style={styles.caption}>
                  {warning.pageNumber ? `page ${warning.pageNumber}` : "document level"}
                </span>
                <span style={styles.bodyText}>{warning.message}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="当前没有解析告警。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>切块结果</summary>
        {visibleChunks.length ? (
          <div style={styles.list}>
            {visibleChunks.map((chunk) => (
              <div key={chunk.id} style={styles.itemCard}>
                <strong>{chunk.sectionId || chunk.id}</strong>
                <span style={styles.caption}>
                  p.{chunk.pageStart}–{chunk.pageEnd} · {chunk.charCount} chars
                </span>
                <pre style={styles.preCompact}>{truncateText(chunk.textPreview || chunk.content, 420)}</pre>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="当前没有 chunk 调试信息。" />
        )}
      </details>

      <details style={styles.card}>
        <summary style={styles.summary}>逐页抽取</summary>
        {visiblePages.length ? (
          <div style={styles.list}>
            {visiblePages.map((page) => (
              <div key={page.pageNumber} style={styles.itemCard}>
                <strong>Page {page.pageNumber}</strong>
                <span style={styles.caption}>
                  {page.charCount} chars · {page.wordCount} words · {page.extractionSource}
                </span>
                {page.headingCandidates.length ? (
                  <div style={styles.tagRow}>
                    {page.headingCandidates.slice(0, 4).map((candidate, index) => (
                      <span key={`${page.pageNumber}:${index}`} style={styles.tag}>
                        {candidate.text}
                      </span>
                    ))}
                  </div>
                ) : null}
                <pre style={styles.preCompact}>{truncateText(page.textPreview || "[empty]", 420)}</pre>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="当前没有逐页抽取结果。" />
        )}
      </details>
    </div>
  );
}

function StreamPanel({
  status,
  events,
  error,
  emptyMessage
}: {
  status: string;
  events: Array<{ stage: string; payload: Record<string, unknown>; createdAt?: string }>;
  error?: string;
  emptyMessage: string;
}) {
  const visibleEvents = events.slice(-8).reverse();
  const streamErrorEvent = [...events].reverse().find((event) => event.stage === "stream_error");
  const streamError = error || extractEventError(streamErrorEvent?.payload);
  return (
    <div style={styles.sectionStack}>
      {streamError ? <PanelError message={streamError} /> : null}
      <div style={styles.statusRow}>
        <StatusPill label="status" status={status} />
        <span style={styles.caption}>
          latest: {visibleEvents[0]?.stage ?? "none"} · total: {events.length}
        </span>
      </div>
      {visibleEvents.length ? (
        <div style={styles.list}>
          {visibleEvents.map((event, index) => (
            <div key={`${event.stage}:${index}`} style={styles.itemCard}>
              <strong>{event.stage}</strong>
              <span style={styles.caption}>{formatDateTime(event.createdAt)}</span>
              <pre style={styles.preCompact}>{truncateJson(event.payload, 500)}</pre>
            </div>
          ))}
        </div>
      ) : (
        <DebugEmptyState message={emptyMessage} />
      )}
    </div>
  );
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.summaryItem}>
      <span style={styles.caption}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ label, status }: { label: string; status: string }) {
  return (
    <span style={{ ...styles.badge, ...statusBadgeStyle(status) }}>
      {label}: {status}
    </span>
  );
}

function DebugEmptyState({ message }: { message: string }) {
  return <p style={styles.empty}>{message}</p>;
}

function PanelError({ message }: { message: string }) {
  return <div style={styles.errorPanel}>{message}</div>;
}

function truncateJson(value: Record<string, unknown>, maxLength: number) {
  return truncateText(JSON.stringify(value, null, 2), maxLength);
}

function extractEventError(payload?: Record<string, unknown>) {
  if (!payload) {
    return "";
  }
  const value = payload.detail ?? payload.error ?? payload.message;
  if (typeof value === "string") {
    return value.trim();
  }
  if (value !== undefined && value !== null) {
    return String(value).trim();
  }
  return "";
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function formatDateTime(value?: string) {
  if (!value) {
    return "实时事件";
  }
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
    background: "linear-gradient(180deg, color-mix(in srgb, white 76%, var(--accent-soft)) 0%, var(--bg) 72%)",
    borderRadius: 16,
    padding: "14px 16px"
  },
  cardHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap"
  },
  headerCopy: {
    display: "grid",
    gap: 4
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)"
  },
  badgeRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap"
  },
  badge: {
    fontSize: 11,
    fontWeight: 600,
    padding: "4px 8px",
    borderRadius: 999,
    background: "var(--accent-soft)",
    color: "var(--accent)"
  },
  statusStrip: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    alignItems: "center",
    marginTop: 12
  },
  metaText: {
    fontSize: 11,
    color: "var(--muted)"
  },
  liveText: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--accent)"
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
    gap: 10,
    marginTop: 14
  },
  summaryItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  summary: {
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    color: "var(--ink)"
  },
  sectionStack: {
    display: "grid",
    gap: 12,
    marginTop: 12
  },
  subSection: {
    display: "grid",
    gap: 8
  },
  subTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--ink-2)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
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
  toolCallCard: {
    display: "grid",
    gap: 6,
    padding: "10px 12px",
    borderRadius: 10,
    background: "color-mix(in srgb, var(--panel) 82%, white)"
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
    background: "white",
    border: "1px solid var(--border)",
    color: "var(--ink-2)"
  },
  tagMuted: {
    fontSize: 11,
    padding: "4px 8px",
    borderRadius: 999,
    background: "var(--panel-strong)",
    border: "1px solid var(--border)",
    color: "var(--muted)"
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap"
  },
  preCompact: {
    margin: 0,
    padding: "10px 12px",
    borderRadius: 10,
    background: "white",
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
  },
  errorPanel: {
    marginTop: 12,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid color-mix(in srgb, var(--negative) 24%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 10%, white)",
    color: "var(--negative)",
    fontSize: 13,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap"
  },
  error: {
    margin: "12px 0 0",
    fontSize: 13,
    color: "var(--negative)"
  }
};

function statusBadgeStyle(status: string): CSSProperties {
  if (status === "completed") {
    return {
      background: "color-mix(in srgb, var(--positive, #0f9d58) 16%, white)",
      color: "var(--positive, #0f9d58)"
    };
  }
  if (status === "running") {
    return {
      background: "color-mix(in srgb, var(--accent) 16%, white)",
      color: "var(--accent)"
    };
  }
  if (status === "error") {
    return {
      background: "color-mix(in srgb, var(--negative) 12%, white)",
      color: "var(--negative)"
    };
  }
  return {
    background: "var(--accent-soft)",
    color: "var(--accent)"
  };
}
