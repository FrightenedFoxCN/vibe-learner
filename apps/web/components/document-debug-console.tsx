"use client";

import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentDebugRecord,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentRecord,
  StreamReport
} from "@vibe-learner/shared";

import {
  getDocumentDebug,
  getDocumentPlanEvents,
  getDocumentPlanningContext,
  getDocumentPlanningTrace,
  getDocumentProcessEvents,
  listDocuments
} from "../lib/api";
import { useLearningWorkspace } from "./learning-workspace-provider";
import { TopNav } from "./top-nav";

export function DocumentDebugConsole() {
  const {
    processStreamDocumentId: liveProcessDocumentId,
    planStreamDocumentId: livePlanDocumentId,
    processStreamEvents: liveProcessStreamEvents,
    planStreamEvents: livePlanStreamEvents,
    processStreamStatus: liveProcessStreamStatus,
    planStreamStatus: livePlanStreamStatus
  } = useLearningWorkspace();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [debugRecord, setDebugRecord] = useState<DocumentDebugRecord | null>(null);
  const [planningContext, setPlanningContext] = useState<DocumentPlanningContext | null>(null);
  const [planningTrace, setPlanningTrace] = useState<DocumentPlanningTraceResponse | null>(null);
  const [message, setMessage] = useState("正在加载解析结果...");
  const [processStreamEvents, setProcessStreamEvents] = useState<Array<{ stage: string; payload: Record<string, unknown> }>>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<Array<{ stage: string; payload: Record<string, unknown> }>>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const selectedDocument = documents.find((document) => document.id === selectedId) ?? null;
  const coarseSections = debugRecord?.sections.filter((section) => section.level === 1) ?? [];
  const fineSections = debugRecord?.sections.filter((section) => section.level === 2) ?? [];
  const planningTraceRecord = planningTrace?.trace ?? null;
  const visiblePages = debugRecord?.pages.slice(0, 12) ?? [];
  const hiddenPageCount = Math.max(0, (debugRecord?.pages.length ?? 0) - visiblePages.length);
  const visibleChunks = debugRecord?.chunks.slice(0, 16) ?? [];
  const hiddenChunkCount = Math.max(0, (debugRecord?.chunks.length ?? 0) - visibleChunks.length);
  const displayProcessStreamEvents =
    selectedId && selectedId === liveProcessDocumentId && liveProcessStreamEvents.length
      ? liveProcessStreamEvents
      : processStreamEvents;
  const displayPlanStreamEvents =
    selectedId && selectedId === livePlanDocumentId && livePlanStreamEvents.length
      ? livePlanStreamEvents
      : planStreamEvents;
  const displayProcessStreamStatus =
    selectedId && selectedId === liveProcessDocumentId && liveProcessStreamEvents.length
      ? liveProcessStreamStatus
      : processStreamStatus;
  const displayPlanStreamStatus =
    selectedId && selectedId === livePlanDocumentId && livePlanStreamEvents.length
      ? livePlanStreamStatus
      : planStreamStatus;
  const latestProcessEvent =
    displayProcessStreamEvents[displayProcessStreamEvents.length - 1] ?? null;
  const latestPlanEvent =
    displayPlanStreamEvents[displayPlanStreamEvents.length - 1] ?? null;

  const applyStreamReport = (
    report: StreamReport,
    setEvents: Dispatch<SetStateAction<Array<{ stage: string; payload: Record<string, unknown> }>>>,
    setStatus: Dispatch<SetStateAction<string>>
  ) => {
    setEvents(
      report.events.map((event) => ({
        stage: event.stage,
        payload: event.payload
      }))
    );
    setStatus(report.status);
  };

  const loadStreamReports = async (documentId: string) => {
    const [processReport, planReport] = await Promise.all([
      getDocumentProcessEvents(documentId),
      getDocumentPlanEvents(documentId)
    ]);
    applyStreamReport(processReport, setProcessStreamEvents, setProcessStreamStatus);
    applyStreamReport(planReport, setPlanStreamEvents, setPlanStreamStatus);
    return {
      processStatus: processReport.status,
      planStatus: planReport.status
    };
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        await refreshDocuments(undefined, active);
      } catch (error) {
        if (active) {
          setMessage(`无法连接 AI 服务: ${String(error)}`);
        }
      }
    };
    void load();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    const hasActiveWork =
      selectedDocument?.status === "processing" ||
      processStreamStatus === "running" ||
      planStreamStatus === "running";
    const pollIntervalMs = hasActiveWork ? 1500 : 4000;
    const timer = window.setInterval(() => {
      void refreshDocuments(selectedId, true, true);
    }, pollIntervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [selectedId, selectedDocument?.status, processStreamStatus, planStreamStatus]);

  const handleSelect = (documentId: string) => {
    setSelectedId(documentId);
    const load = async () => {
      try {
        await loadDebugReport(documentId);
      } catch (error) {
        setMessage(`读取调试报告失败: ${String(error)}`);
      }
    };
    void load();
  };

  const loadDebugReport = async (documentId: string) => {
    const doc = documents.find((item) => item.id === documentId);
    const streamState = await loadStreamReports(documentId);
    if (!doc?.debugReady) {
      setDebugRecord(null);
      setPlanningContext(null);
      setPlanningTrace(null);
      if (doc?.status === "processing" || streamState.processStatus === "running") {
        setMessage("该文档仍在处理中，已加载最近一次流式处理记录。");
      } else {
        setMessage("该文档尚未生成调试报告。");
      }
      return;
    }
    const report = await getDocumentDebug(documentId);
    const planning = await getDocumentPlanningContext(documentId);
    const trace = await getDocumentPlanningTrace(documentId);
    setDebugRecord(report);
    setPlanningContext(planning);
    setPlanningTrace(trace);
    setMessage("已切换到新的解析调试报告。");
  };

  const refreshDocuments = async (preferredId?: string, active = true, silent = false) => {
    const docs = await listDocuments();
    if (!active) {
      return;
    }
    setDocuments(docs);
    const nextId = preferredId ?? selectedId ?? docs.find((item) => item.debugReady)?.id ?? docs[0]?.id ?? "";
    if (!nextId) {
      setDebugRecord(null);
      setPlanningContext(null);
      setPlanningTrace(null);
      setProcessStreamEvents([]);
      setPlanStreamEvents([]);
      setProcessStreamStatus("idle");
      setPlanStreamStatus("idle");
      if (!silent) {
        setMessage("还没有文档。先在主页上传教材，再回来看解析后台。");
      }
      return;
    }
    setSelectedId(nextId);
    const nextDoc = docs.find((item) => item.id === nextId);
    const streamState = await loadStreamReports(nextId);
    if (!active) {
      return;
    }
    if (!nextDoc?.debugReady) {
      setDebugRecord(null);
      setPlanningContext(null);
      setPlanningTrace(null);
      if (!silent) {
        if (nextDoc?.status === "processing" || streamState.processStatus === "running") {
          setMessage("该文档仍在处理中，已回放最近一次流式处理记录。");
        } else {
          setMessage("该文档尚未生成调试报告，请先处理文档。");
        }
      }
      return;
    }
    const report = await getDocumentDebug(nextId);
    const planning = await getDocumentPlanningContext(nextId);
    const trace = await getDocumentPlanningTrace(nextId);
    if (!active) {
      return;
    }
    setDebugRecord(report);
    setPlanningContext(planning);
    setPlanningTrace(trace);
    if (!silent) {
      setMessage("已加载解析调试报告。");
    }
  };

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/debug" />

      <div style={styles.hero}>
        <div style={styles.heroLeft}>
          <span style={styles.heroTitle}>教材解析后台</span>
          <span style={styles.heroSub}>解析链路中间结果：页级抽取、候选标题、切块边界与告警。</span>
        </div>
        <span style={styles.message}>{message}</span>
      </div>

      <section className="debug-main-grid">
        <aside className="debug-sidebar-sticky" style={styles.sidebar}>
          <h2 style={styles.sidebarTitle}>文档列表</h2>
          {documents.map((document) => (
            <button
              key={document.id}
              style={{
                ...styles.docButton,
                ...(document.id === selectedId ? styles.docButtonActive : {})
              }}
              onClick={() => handleSelect(document.id)}
            >
              <strong>{document.title}</strong>
              <span>
                {document.status} · {document.pageCount} 页 · {document.chunkCount} chunks
              </span>
            </button>
          ))}
        </aside>

        <section style={styles.content}>
          <article style={styles.summaryCard}>
            <h2 style={styles.sectionTitle}>解析摘要</h2>
            {debugRecord ? (
              <>
                <div style={styles.summaryGrid}>
                  <div style={styles.summaryItem}>
                    <span>Parser</span>
                    <strong>{debugRecord.parserName}</strong>
                  </div>
                  <div style={styles.summaryItem}>
                    <span>Pages</span>
                    <strong>{debugRecord.pageCount}</strong>
                  </div>
                  <div style={styles.summaryItem}>
                    <span>Characters</span>
                    <strong>{debugRecord.totalCharacters}</strong>
                  </div>
                  <div style={styles.summaryItem}>
                    <span>Language</span>
                    <strong>{debugRecord.dominantLanguageHint}</strong>
                  </div>
                  <div style={styles.summaryItem}>
                    <span>Extraction</span>
                    <strong>{debugRecord.extractionMethod}</strong>
                  </div>
                  <div style={styles.summaryItem}>
                    <span>OCR</span>
                    <strong>
                      {debugRecord.ocrApplied
                        ? `yes${debugRecord.ocrLanguage ? ` (${debugRecord.ocrLanguage})` : ""}`
                        : "no"}
                    </strong>
                  </div>
                </div>
              </>
            ) : (
              <p style={styles.empty}>暂无调试报告。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>流式处理反馈</h2>
            <div style={styles.streamStatusRow}>
              <span style={styles.streamStatusLabel}>状态</span>
              <span style={styles.streamStatusValue}>{displayProcessStreamStatus}</span>
              <span style={styles.streamStatusLabel}>最近阶段</span>
              <span style={styles.streamStatusValue}>{latestProcessEvent?.stage ?? "none"}</span>
            </div>
            {displayProcessStreamEvents.length ? (
              <details style={styles.streamDetails}>
                <summary style={styles.streamSummary}>展开最近 8 条处理事件</summary>
                <div style={styles.chunkGrid}>
                  {displayProcessStreamEvents.slice(-8).map((event, index) => (
                    <div key={`${event.stage}-${index}`} style={styles.chunkCard}>
                      <strong>{event.stage}</strong>
                      <pre style={styles.preCompact}>{truncateJson(event.payload, 1200)}</pre>
                    </div>
                  ))}
                </div>
              </details>
            ) : (
              <p style={styles.empty}>暂无处理事件记录。请在计划生成页通过“上传并生成计划”触发完整流程。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>流式生成学习计划</h2>
            <div style={styles.streamStatusRow}>
              <span style={styles.streamStatusLabel}>状态</span>
              <span style={styles.streamStatusValue}>{displayPlanStreamStatus}</span>
              <span style={styles.streamStatusLabel}>最近阶段</span>
              <span style={styles.streamStatusValue}>{latestPlanEvent?.stage ?? "none"}</span>
            </div>
            {displayPlanStreamEvents.length ? (
              <details style={styles.streamDetails}>
                <summary style={styles.streamSummary}>展开最近 8 条计划事件</summary>
                <div style={styles.chunkGrid}>
                  {displayPlanStreamEvents.slice(-8).map((event, index) => (
                    <div key={`${event.stage}-${index}`} style={styles.chunkCard}>
                      <strong>{event.stage}</strong>
                      <pre style={styles.preCompact}>{truncateJson(event.payload, 1200)}</pre>
                    </div>
                  ))}
                </div>
              </details>
            ) : (
              <p style={styles.empty}>暂无计划流事件记录。请在计划生成页通过“上传并生成计划”触发完整流程。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>章节猜测</h2>
            {debugRecord?.sections.length ? (
              <div style={styles.sectionGrid}>
                <div style={styles.sectionColumn}>
                  <div style={styles.sectionColumnHeader}>
                    <strong>一级分段</strong>
                    <span>{coarseSections.length} sections</span>
                  </div>
                  <div style={styles.list}>
                    {coarseSections.map((section, index) => (
                      <div key={`${section.id}-${index}`} style={styles.listItem}>
                        <div style={styles.sectionMetaRow}>
                          <strong>{section.title}</strong>
                          <span style={styles.sectionLevelBadge}>L1</span>
                        </div>
                        <span>
                          p.{section.pageStart}-{section.pageEnd}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div style={styles.sectionColumn}>
                  <div style={styles.sectionColumnHeader}>
                    <strong>二级分段</strong>
                    <span>{fineSections.length} sections</span>
                  </div>
                  <div style={styles.list}>
                    {fineSections.length ? (
                      fineSections.map((section, index) => (
                        <div key={`${section.id}-${index}`} style={styles.listItem}>
                          <div style={styles.sectionMetaRow}>
                            <strong>{section.title}</strong>
                            <span style={styles.sectionLevelBadgeFine}>L2</span>
                          </div>
                          <span>
                            p.{section.pageStart}-{section.pageEnd}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p style={styles.empty}>暂无二级分段。</p>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p style={styles.empty}>暂无章节结果。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>学习编排清洗结果</h2>
            {debugRecord?.studyUnits.length ? (
              <div style={styles.list}>
                {debugRecord.studyUnits.map((unit) => (
                  <div key={unit.id} style={styles.listItem}>
                    <div style={styles.sectionMetaRow}>
                      <strong>{unit.title}</strong>
                      <span style={unit.includeInPlan ? styles.sectionLevelBadgeFine : styles.sectionLevelBadge}>
                        {unit.unitKind}
                      </span>
                    </div>
                    <span>
                      p.{unit.pageStart}-{unit.pageEnd} · confidence {unit.confidence}
                    </span>
                    <span>{unit.summary}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.empty}>暂无学习编排结果。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>计划工具与章节详情</h2>
            {planningContext ? (
              <div style={styles.list}>
                <div style={styles.toolRow}>
                  {planningContext.availableTools.map((tool) => (
                    <div key={tool.name} style={styles.toolCard}>
                      <strong>{tool.name}</strong>
                      <span>{tool.description}</span>
                    </div>
                  ))}
                </div>
                {planningContext.studyUnits.map((unit) => {
                  const detail = planningContext.detailMap[unit.unitId];
                  return (
                    <div key={unit.unitId} style={styles.listItem}>
                      <div style={styles.sectionMetaRow}>
                        <strong>{unit.title}</strong>
                        <span style={unit.includeInPlan ? styles.sectionLevelBadgeFine : styles.sectionLevelBadge}>
                          {unit.unitKind}
                        </span>
                      </div>
                      <span>
                        tool target: {unit.detailToolTargetId} · p.{unit.pageStart}-{unit.pageEnd}
                      </span>
                      <span>{unit.summary}</span>
                      {unit.subsectionTitles.length ? (
                        <div style={styles.childChipRow}>
                          {unit.subsectionTitles.map((title) => (
                            <span key={title} style={styles.headingTag}>
                              {title}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {detail ? (
                        <div style={styles.detailBlock}>
                          <span>关联 sections: {detail.relatedSections.map((section) => section.title).join(" / ") || "无"}</span>
                          <span>chunk excerpts: {detail.chunkCount}</span>
                          {detail.chunkExcerpts.length ? (
                            <div style={styles.chunkGrid}>
                              {detail.chunkExcerpts.slice(0, 2).map((chunk) => (
                                <div key={chunk.chunkId} style={styles.chunkCard}>
                                  <strong>{chunk.chunkId}</strong>
                                  <span>
                                    p.{chunk.pageStart}-{chunk.pageEnd} · {chunk.charCount} chars
                                  </span>
                                  <pre style={styles.preCompact}>{truncateText(chunk.content, 220)}</pre>
                                </div>
                              ))}
                              {detail.chunkExcerpts.length > 2 ? (
                                <div style={styles.chunkCardCollapsed}>
                                  其余 {detail.chunkExcerpts.length - 2} 条 excerpt 已折叠。
                                </div>
                              ) : null}
                            </div>
                          ) : (
                            <span style={styles.emptyInline}>暂无可供工具读取的 chunk 内容。</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p style={styles.empty}>暂无计划工具上下文。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>计划模型 Trace</h2>
            {planningTraceRecord?.rounds.length ? (
              <div style={styles.list}>
                <div style={styles.toolCard}>
                  <strong>{planningTraceRecord.model || "unknown model"}</strong>
                  <span>
                    plan id: {planningTraceRecord.planId ?? "未写入"} · created at: {planningTraceRecord.createdAt || "unknown"}
                  </span>
                  <span>
                    rounds: {planningTrace?.summary.roundCount ?? 0} · tool calls: {planningTrace?.summary.toolCallCount ?? 0} · latest finish: {planningTrace?.summary.latestFinishReason || "unknown"}
                  </span>
                </div>
                {planningTraceRecord.rounds.map((round) => (
                  <div key={round.roundIndex} style={styles.listItem}>
                    <div style={styles.sectionMetaRow}>
                      <strong>Round {round.roundIndex}</strong>
                      <span style={styles.sectionLevelBadgeFine}>
                        {round.finishReason || "unknown_finish"}
                      </span>
                    </div>
                    <span>
                      {round.elapsedMs} ms · timeout scope = single round · threshold {round.timeoutSeconds}s
                    </span>
                    {round.thinking ? (
                      <div style={styles.detailBlock}>
                        <strong>Thinking</strong>
                        <pre style={styles.pre}>{truncateText(round.thinking, 1200)}</pre>
                      </div>
                    ) : (
                      <span style={styles.emptyInline}>无 reasoning/thinking 内容。</span>
                    )}
                    {round.assistantContent ? (
                      <div style={styles.detailBlock}>
                        <strong>Assistant content</strong>
                        <pre style={styles.pre}>{truncateText(round.assistantContent, 1200)}</pre>
                      </div>
                    ) : null}
                    {round.toolCalls.length ? (
                      <div style={styles.detailBlock}>
                        <strong>Tool calls</strong>
                        <div style={styles.chunkGrid}>
                          {round.toolCalls.map((toolCall) => (
                            <div key={toolCall.toolCallId} style={styles.chunkCard}>
                              <strong>{toolCall.toolName}</strong>
                              <span>{toolCall.toolCallId}</span>
                              {toolCall.resultSummary ? (
                                <span style={styles.traceSummary}>{toolCall.resultSummary}</span>
                              ) : null}
                              <pre style={styles.preCompact}>{truncateText(toolCall.argumentsJson, 1200)}</pre>
                              <pre style={styles.preCompact}>{truncateText(toolCall.resultJson, 1200)}</pre>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <span style={styles.emptyInline}>本轮无 tool call。</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.empty}>暂无计划模型 trace。先生成一次学习计划。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>解析告警</h2>
            {debugRecord?.warnings.length ? (
              <div style={styles.list}>
                {debugRecord.warnings.map((warning, index) => (
                  <div key={`${warning.code}-${index}`} style={styles.warningItem}>
                    <strong>{warning.code}</strong>
                    <span>
                      {warning.message}
                      {warning.pageNumber ? ` (page ${warning.pageNumber})` : ""}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.empty}>无告警。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>切块结果</h2>
            {visibleChunks.length ? (
              <div style={styles.chunkGrid}>
                {visibleChunks.map((chunk) => (
                  <div key={chunk.id} style={styles.chunkCard}>
                    <strong>{chunk.id}</strong>
                    <span>
                      {chunk.sectionId} · p.{chunk.pageStart}-{chunk.pageEnd} · {chunk.charCount} chars
                    </span>
                    <pre style={styles.preCompact}>{truncateText(chunk.textPreview, 180)}</pre>
                  </div>
                ))}
                {hiddenChunkCount ? (
                  <div style={styles.chunkCardCollapsed}>
                    仅展示前 {visibleChunks.length} 个 chunk，剩余 {hiddenChunkCount} 个已折叠。
                  </div>
                ) : null}
              </div>
            ) : (
              <p style={styles.empty}>暂无 chunks。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>逐页抽取</h2>
            {visiblePages.length ? (
              <div style={styles.pageList}>
                {visiblePages.map((page) => (
                  <div key={page.pageNumber} style={styles.pageCard}>
                    <div style={styles.pageMeta}>
                      <strong>Page {page.pageNumber}</strong>
                      <span>
                        {page.charCount} chars · {page.wordCount} words · dominant font {page.dominantFontSize} · {page.extractionSource}
                      </span>
                    </div>
                    <div style={styles.headingRow}>
                      {page.headingCandidates.length ? (
                        page.headingCandidates.map((candidate, index) => (
                          <span key={`${candidate.text}-${index}`} style={styles.headingTag}>
                            {candidate.text} · {candidate.confidence}
                          </span>
                        ))
                      ) : (
                        <span style={styles.headingTagMuted}>无标题候选</span>
                      )}
                    </div>
                    <pre style={styles.pre}>{truncateText(page.textPreview || "[empty]", 1200)}</pre>
                  </div>
                ))}
                {hiddenPageCount ? (
                  <div style={styles.pageCardCollapsed}>
                    仅展示前 {visiblePages.length} 页的页级抽取结果，剩余 {hiddenPageCount} 页已折叠。
                  </div>
                ) : null}
              </div>
            ) : (
              <p style={styles.empty}>暂无页级结果。</p>
            )}
          </article>
        </section>
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "20px 32px 48px"
  },
  hero: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 14,
    flexWrap: "wrap"
  },
  heroLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12
  },
  heroTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  heroSub: {
    fontSize: 13,
    color: "var(--muted)"
  },
  message: {
    fontSize: 13,
    color: "var(--accent)",
    whiteSpace: "nowrap"
  },
  sidebar: {
    display: "grid",
    gap: 0,
    alignContent: "start",
    borderRight: "1px solid var(--border)",
    paddingRight: 24,
    position: "sticky",
    top: 20
  },
  sidebarTitle: {
    margin: "0 0 8px",
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)"
  },
  docButton: {
    textAlign: "left",
    display: "grid",
    gap: 4,
    padding: "10px 0 10px 8px",
    border: "none",
    borderBottom: "1px solid var(--border)",
    background: "transparent",
    cursor: "pointer",
    fontSize: 13,
    color: "var(--ink)"
  },
  docButtonActive: {
    borderLeft: "2px solid var(--accent)",
    paddingLeft: 6,
    color: "var(--accent)"
  },
  content: {
    display: "grid",
    gap: 0
  },
  summaryCard: {
    paddingTop: 16,
    paddingBottom: 16,
    borderTop: "1px solid var(--border)"
  },
  sectionTitle: {
    margin: "0 0 14px",
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)"
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: 1,
    background: "var(--border)"
  },
  actionRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginBottom: 14
  },
  actionButton: {
    border: "1px solid var(--border)",
    background: "transparent",
    padding: "6px 12px",
    borderRadius: 3,
    cursor: "pointer",
    fontSize: 13,
    color: "var(--ink)"
  },
  actionButtonAccent: {
    border: "none",
    background: "var(--accent)",
    padding: "6px 12px",
    borderRadius: 3,
    cursor: "pointer",
    fontSize: 13,
    color: "white",
    fontWeight: 600
  },
  summaryItem: {
    display: "grid",
    gap: 4,
    padding: "12px 14px",
    background: "var(--bg)",
    fontSize: 13
  },
  card: {
    paddingTop: 16,
    paddingBottom: 4,
    borderTop: "1px solid var(--border)"
  },
  streamStatusRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
    marginBottom: 10
  },
  streamStatusLabel: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  streamStatusValue: {
    fontSize: 13,
    color: "var(--ink)"
  },
  streamDetails: {
    display: "grid",
    gap: 8
  },
  streamSummary: {
    color: "var(--accent)",
    cursor: "pointer",
    fontSize: 13,
    width: "fit-content"
  },
  formGrid: {
    display: "grid",
    gap: 12,
    marginBottom: 14
  },
  field: {
    display: "grid",
    gap: 6,
    fontSize: 13,
    color: "var(--muted)"
  },
  input: {
    width: "100%",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    fontSize: 13,
    color: "var(--ink)"
  },
  select: {
    width: "100%",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    fontSize: 13,
    color: "var(--ink)"
  },
  textarea: {
    width: "100%",
    minHeight: 72,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 13,
    color: "var(--ink)"
  },
  list: {
    display: "grid",
    gap: 0
  },
  sectionGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 32
  },
  sectionColumn: {
    display: "grid",
    gap: 0,
    alignContent: "start"
  },
  sectionColumnHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    color: "var(--muted)",
    fontSize: 13,
    paddingBottom: 8,
    borderBottom: "1px solid var(--border)"
  },
  listItem: {
    display: "grid",
    gap: 4,
    padding: "10px 0",
    borderBottom: "1px solid var(--border)",
    fontSize: 13
  },
  childChipRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap"
  },
  toolRow: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: 1,
    background: "var(--border)",
    marginBottom: 14
  },
  toolCard: {
    display: "grid",
    gap: 4,
    padding: "12px 14px",
    background: "var(--bg)",
    fontSize: 13
  },
  detailBlock: {
    display: "grid",
    gap: 8,
    paddingLeft: 12,
    borderLeft: "2px solid var(--border)",
    marginTop: 4
  },
  emptyInline: {
    color: "var(--muted)",
    fontSize: 13
  },
  sectionMetaRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center"
  },
  sectionLevelBadge: {
    fontSize: 11,
    color: "var(--muted)",
    fontWeight: 700
  },
  sectionLevelBadgeFine: {
    fontSize: 11,
    color: "var(--teal)",
    fontWeight: 700
  },
  warningItem: {
    display: "grid",
    gap: 4,
    padding: "10px 0 10px 12px",
    borderBottom: "1px solid var(--border)",
    borderLeft: "2px solid var(--accent)",
    fontSize: 13
  },
  chunkGrid: {
    display: "grid",
    gap: 10
  },
  chunkCard: {
    display: "grid",
    gap: 6,
    paddingLeft: 12,
    paddingTop: 8,
    paddingBottom: 8,
    borderLeft: "2px solid var(--border)",
    borderBottom: "1px solid var(--border)",
    fontSize: 13
  },
  chunkCardCollapsed: {
    padding: "10px 0",
    color: "var(--muted)",
    fontSize: 13,
    borderBottom: "1px dashed var(--border)"
  },
  traceSummary: {
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.5
  },
  pageList: {
    display: "grid",
    gap: 0
  },
  pageCard: {
    display: "grid",
    gap: 8,
    padding: "12px 0",
    borderBottom: "1px solid var(--border)",
    fontSize: 13
  },
  pageCardCollapsed: {
    padding: "10px 0",
    color: "var(--muted)",
    fontSize: 13
  },
  pageMeta: {
    display: "grid",
    gap: 4
  },
  headingRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap"
  },
  headingTag: {
    padding: "2px 6px",
    border: "1px solid var(--border)",
    borderRadius: 3,
    fontSize: 11
  },
  headingTagMuted: {
    padding: "2px 6px",
    border: "1px solid var(--border)",
    borderRadius: 3,
    fontSize: 11,
    color: "var(--muted)"
  },
  pre: {
    margin: 0,
    padding: 12,
    borderRadius: 3,
    background: "rgba(45,36,31,0.92)",
    color: "#fff6ed",
    whiteSpace: "pre-wrap",
    lineHeight: 1.6,
    overflowX: "auto",
    fontSize: 13
  },
  preCompact: {
    margin: 0,
    padding: 10,
    borderRadius: 3,
    background: "rgba(45,36,31,0.92)",
    color: "#fff6ed",
    whiteSpace: "pre-wrap",
    lineHeight: 1.5,
    overflowX: "auto",
    fontSize: 12
  },
  empty: {
    margin: "10px 0 0",
    color: "var(--muted)",
    fontSize: 13
  }
};

function truncateText(text: string, maxChars: number) {
  const normalized = (text || "").trim();
  if (normalized.length <= maxChars) {
    return normalized;
  }
  return `${normalized.slice(0, maxChars).trimEnd()}...`;
}

function truncateJson(value: unknown, maxChars: number) {
  return truncateText(JSON.stringify(value, null, 2), maxChars);
}
