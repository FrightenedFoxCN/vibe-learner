"use client";

import type {
  DocumentDebugRecord,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentRecord,
  ModelToolConfig,
  StreamReport,
} from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import { formatOcrStatus } from "../../lib/ocr-status";
import styles from "./document-debug-panels.module.css";

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
}: DocumentDebugPanelsProps) {
  if (!document) {
    return <DebugEmptyState message="暂无教材" />;
  }

  const useLiveProcess =
    processLiveDocumentId === document.id && processLiveEvents.length > 0;
  const useLivePlan = planLiveDocumentId === document.id && planLiveEvents.length > 0;
  const displayProcessEvents = useLiveProcess
    ? processLiveEvents.map((event) => ({ ...event, createdAt: "" }))
    : (processReport?.events ?? []);
  const displayPlanEvents = useLivePlan
    ? planLiveEvents.map((event) => ({ ...event, createdAt: "" }))
    : (planReport?.events ?? []);
  const displayProcessStatus = useLiveProcess
    ? processLiveStatus
    : (processReport?.status ?? "idle");
  const displayPlanStatus = useLivePlan
    ? planLiveStatus
    : (planReport?.status ?? "idle");
  const visibleChunks = debugRecord?.chunks.slice(0, 12) ?? [];
  const visiblePages = debugRecord?.pages.slice(0, 10) ?? [];

  return (
    <div className={styles.stack}>
      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.headerCopy}>
            <span className={styles.cardTitle}>调试总览</span>
            <span className={styles.caption}>{document.title}</span>
          </div>
          <div className={styles.badgeRow}>
            {loading ? <span className={styles.badge}>刷新中</span> : null}
            <span className={styles.badge}>status: {document.status}</span>
            <span className={styles.badge}>
              debug: {document.debugReady ? "ready" : "pending"}
            </span>
          </div>
        </div>
        {error ? <p className={styles.error}>{error}</p> : null}
        <div className={styles.statusStrip}>
          <StatusPill label="process" status={displayProcessStatus} />
          <StatusPill label="plan" status={displayPlanStatus} />
        </div>
        <div className={styles.summaryGrid}>
          <SummaryItem
            label="Pages"
            value={String(debugRecord?.pageCount ?? document.pageCount)}
          />
          <SummaryItem
            label="Chunks"
            value={String(debugRecord?.chunks.length ?? document.chunkCount)}
          />
          <SummaryItem
            label="Study Units"
            value={String(debugRecord?.studyUnits.length ?? document.studyUnitCount)}
          />
          <SummaryItem label="Parser" value={debugRecord?.parserName ?? "-"} />
          <SummaryItem
            label="Extraction"
            value={debugRecord?.extractionMethod ?? "-"}
          />
          <SummaryItem
            label="OCR"
            value={`${formatOcrStatus(debugRecord?.ocrStatus ?? document.ocrStatus)}${
              debugRecord?.ocrLanguage ? `（${debugRecord.ocrLanguage}）` : ""
            }`}
          />
        </div>
      </section>

      <details className={styles.card} open>
        <summary className={styles.summary}>流式处理反馈</summary>
        <StreamPanel
          status={displayProcessStatus}
          events={displayProcessEvents}
          error={processReportError}
          emptyMessage="还没有文档处理流事件。"
        />
      </details>

      <details className={styles.card} open>
        <summary className={styles.summary}>流式生成学习计划</summary>
        <StreamPanel
          status={displayPlanStatus}
          events={displayPlanEvents}
          error={planReportError}
          emptyMessage="还没有计划生成流事件。"
        />
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>章节猜测</summary>
        {debugRecordError ? <PanelError message={debugRecordError} /> : null}
        {debugRecord?.sections.length ? (
          <div className={styles.list}>
            {debugRecord.sections.map((section) => (
              <div key={section.id} className={styles.itemCard}>
                <strong>{section.title || section.id}</strong>
                <span className={styles.caption}>
                  L{section.level} · p.{section.pageStart}–{section.pageEnd}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>学习编排清洗结果</summary>
        {debugRecordError ? <PanelError message={debugRecordError} /> : null}
        {debugRecord?.studyUnits.length ? (
          <div className={styles.list}>
            {debugRecord.studyUnits.map((unit) => (
              <div key={unit.id} className={styles.itemCard}>
                <strong>{unit.title}</strong>
                <span className={styles.caption}>
                  p.{unit.pageStart}–{unit.pageEnd} · {unit.unitKind}
                  {unit.includeInPlan ? "" : " · skipped"}
                </span>
                <span className={styles.bodyText}>
                  {truncateText(unit.summary || "-", 220)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>计划输入目录</summary>
        {planningContextError ? <PanelError message={planningContextError} /> : null}
        {planningContext?.courseOutline.length ? (
          <div className={styles.list}>
            {planningContext.courseOutline.map((node) => (
              <div key={node.sectionId} className={styles.itemCard}>
                <strong>{node.title || node.sectionId}</strong>
                <span className={styles.caption}>
                  L{node.level} · p.{node.pageStart}–{node.pageEnd}
                </span>
                {node.children.length ? (
                  <div className={styles.tagRow}>
                    {node.children.map((child) => (
                      <span key={child.sectionId} className={styles.tag}>
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

      <details className={styles.card}>
        <summary className={styles.summary}>计划工具与章节详情</summary>
        {planningContext ||
        modelToolConfig ||
        planningContextError ||
        modelToolConfigError ? (
          <div className={styles.sectionStack}>
            <div className={styles.subSection}>
              <span className={styles.subTitle}>当前可用工具</span>
              {planningContextError ? (
                <PanelError message={planningContextError} />
              ) : null}
              {planningContext?.availableTools.length ? (
                <div className={styles.tagRow}>
                  {planningContext.availableTools.map((tool) => (
                    <span key={tool.name} className={styles.tag}>
                      {tool.name}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <div className={styles.subSection}>
              <span className={styles.subTitle}>模型工具开关</span>
              {modelToolConfigError ? (
                <PanelError message={modelToolConfigError} />
              ) : null}
              {modelToolConfig?.stages.length ? (
                <div className={styles.list}>
                  {modelToolConfig.stages.map((stage) => (
                    <div key={stage.name} className={styles.itemCard}>
                      <strong>{stage.label}</strong>
                      <span className={styles.caption}>
                        {stage.stageEnabled ? "runtime on" : "runtime off"} ·{" "}
                        {stage.name}
                      </span>
                      <div className={styles.tagRow}>
                        {stage.tools.map((tool) => (
                          <span
                            key={tool.name}
                            className={
                              tool.effectiveEnabled ? styles.tag : styles.tagMuted
                            }
                          >
                            {tool.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
            <div className={styles.subSection}>
              <span className={styles.subTitle}>Study Unit Detail</span>
              {planningContextError ? (
                <PanelError message={planningContextError} />
              ) : null}
              {planningContext?.studyUnits.length ? (
                <div className={styles.list}>
                  {planningContext.studyUnits.map((unit) => {
                    const detail = planningContext.detailMap[unit.unitId];
                    return (
                      <div key={unit.unitId} className={styles.itemCard}>
                        <strong>{unit.title}</strong>
                        <span className={styles.caption}>
                          p.{unit.pageStart}–{unit.pageEnd} · detail chunks:{" "}
                          {detail?.chunkCount ?? 0}
                        </span>
                        <span className={styles.bodyText}>
                          {truncateText(unit.summary || "-", 180)}
                        </span>
                        {detail?.subsectionTitles.length ? (
                          <div className={styles.tagRow}>
                            {detail.subsectionTitles.map((title, index) => (
                              <span
                                key={`${unit.unitId}:${index}`}
                                className={styles.tag}
                              >
                                {title}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {detail?.chunkExcerpts.length ? (
                          <pre className={styles.preCompact}>
                            {truncateText(detail.chunkExcerpts[0]?.content ?? "", 500)}
                          </pre>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>计划模型 Trace</summary>
        {planningTraceError ? <PanelError message={planningTraceError} /> : null}
        {planningTrace?.trace?.rounds.length ? (
          <div className={styles.list}>
            <div className={styles.itemCard}>
              <strong>{planningTrace.trace.model || "unknown model"}</strong>
              <span className={styles.caption}>
                rounds: {planningTrace.summary.roundCount} · tool calls:{" "}
                {planningTrace.summary.toolCallCount} · recoveries:{" "}
                {planningTrace.trace.rounds.reduce(
                  (sum, round) => sum + (round.recoveries?.length ?? 0),
                  0,
                )}
              </span>
            </div>
            {planningTrace.trace.rounds.map((round) => (
              <div
                key={`${round.roundIndex}:${round.finishReason}`}
                className={styles.itemCard}
              >
                <strong>Round {round.roundIndex + 1}</strong>
                <span className={styles.caption}>
                  {round.finishReason || "no finish reason"} · {round.elapsedMs} ms ·
                  timeout {round.timeoutSeconds}s
                </span>
                {round.thinking ? (
                  <pre className={styles.preCompact}>
                    {truncateText(round.thinking, 900)}
                  </pre>
                ) : null}
                {round.assistantContent ? (
                  <pre className={styles.preCompact}>
                    {truncateText(round.assistantContent, 900)}
                  </pre>
                ) : null}
                {round.recoveries?.length ? (
                  <div className={styles.tagRow}>
                    {round.recoveries.map((recovery) => (
                      <span key={recovery.recoveryId} className={styles.tag}>
                        {recovery.reason} · {recovery.strategy} · x{recovery.attempts}
                      </span>
                    ))}
                  </div>
                ) : null}
                {round.toolCalls.length ? (
                  <div className={styles.list}>
                    {round.toolCalls.map((toolCall) => (
                      <div key={toolCall.toolCallId} className={styles.toolCallCard}>
                        <strong>{toolCall.toolName}</strong>
                        <span className={styles.caption}>
                          {toolCall.resultSummary || "无结果摘要"}
                        </span>
                        <pre className={styles.preCompact}>
                          {truncateText(toolCall.argumentsJson, 500)}
                        </pre>
                        <pre className={styles.preCompact}>
                          {truncateText(toolCall.resultJson, 500)}
                        </pre>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>解析告警</summary>
        {debugRecord?.warnings.length ? (
          <div className={styles.list}>
            {debugRecord.warnings.map((warning, index) => (
              <div key={`${warning.code}:${index}`} className={styles.itemCard}>
                <strong>{warning.code}</strong>
                <span className={styles.caption}>
                  {warning.pageNumber ? `page ${warning.pageNumber}` : "document level"}
                </span>
                <span className={styles.bodyText}>{warning.message}</span>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>切块结果</summary>
        {visibleChunks.length ? (
          <div className={styles.list}>
            {visibleChunks.map((chunk) => (
              <div key={chunk.id} className={styles.itemCard}>
                <strong>{chunk.sectionId || chunk.id}</strong>
                <span className={styles.caption}>
                  p.{chunk.pageStart}–{chunk.pageEnd} · {chunk.charCount} chars
                </span>
                <pre className={styles.preCompact}>
                  {truncateText(chunk.textPreview || chunk.content, 420)}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <DebugEmptyState message="暂无数据" />
        )}
      </details>

      <details className={styles.card}>
        <summary className={styles.summary}>逐页抽取</summary>
        {visiblePages.length ? (
          <div className={styles.list}>
            {visiblePages.map((page) => (
              <div key={page.pageNumber} className={styles.itemCard}>
                <strong>Page {page.pageNumber}</strong>
                <span className={styles.caption}>
                  {page.charCount} chars · {page.wordCount} words ·{" "}
                  {page.extractionSource}
                </span>
                {page.headingCandidates.length ? (
                  <div className={styles.tagRow}>
                    {page.headingCandidates.slice(0, 4).map((candidate, index) => (
                      <span key={`${page.pageNumber}:${index}`} className={styles.tag}>
                        {candidate.text}
                      </span>
                    ))}
                  </div>
                ) : null}
                <pre className={styles.preCompact}>
                  {truncateText(page.textPreview || "[empty]", 420)}
                </pre>
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

function StreamPanel({
  status,
  events,
  error,
  emptyMessage,
}: {
  status: string;
  events: Array<{
    stage: string;
    payload: Record<string, unknown>;
    createdAt?: string;
  }>;
  error?: string;
  emptyMessage: string;
}) {
  const visibleEvents = events.slice(-8).reverse();
  const streamErrorEvent = [...events]
    .reverse()
    .find((event) => event.stage === "stream_error");
  const streamError = error || extractEventError(streamErrorEvent?.payload);
  return (
    <div className={styles.sectionStack}>
      {streamError ? <PanelError message={streamError} /> : null}
      <div className={styles.statusRow}>
        <StatusPill label="status" status={status} />
        <span className={styles.caption}>
          latest: {visibleEvents[0]?.stage ?? "none"} · total: {events.length}
        </span>
      </div>
      {visibleEvents.length ? (
        <div className={styles.list}>
          {visibleEvents.map((event, index) => (
            <div key={`${event.stage}:${index}`} className={styles.itemCard}>
              <strong>{event.stage}</strong>
              <span className={styles.caption}>
                {formatTimestamp(event.createdAt, {
                  style: "debug",
                  empty: "实时事件",
                })}
              </span>
              <pre className={styles.preCompact}>
                {truncateJson(event.payload, 500)}
              </pre>
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
    <div className={styles.summaryItem}>
      <span className={styles.caption}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ label, status }: { label: string; status: string }) {
  return (
    <span className={styles.badge} data-status={status}>
      {label}: {status}
    </span>
  );
}

function DebugEmptyState({ message }: { message: string }) {
  return <p className={styles.empty}>{message}</p>;
}

function PanelError({ message }: { message: string }) {
  return <div className={styles.errorPanel}>{message}</div>;
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
