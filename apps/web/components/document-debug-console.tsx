"use client";

import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentDebugRecord,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  LearningPlan,
  PersonaProfile,
  DocumentRecord,
  StreamReport
} from "@gal-learner/shared";

import {
  createLearningPlanStream,
  getDocumentDebug,
  getDocumentPlanEvents,
  getDocumentPlanningContext,
  getDocumentPlanningTrace,
  getDocumentProcessEvents,
  listDocuments,
  listPersonas,
  processDocumentStream
} from "../lib/api";

export function DocumentDebugConsole() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [debugRecord, setDebugRecord] = useState<DocumentDebugRecord | null>(null);
  const [planningContext, setPlanningContext] = useState<DocumentPlanningContext | null>(null);
  const [planningTrace, setPlanningTrace] = useState<DocumentPlanningTraceResponse | null>(null);
  const [message, setMessage] = useState("正在加载解析结果...");
  const [selectedPersonaId, setSelectedPersonaId] = useState("mentor-aurora");
  const [objective, setObjective] = useState("梳理这本教材的结构并生成第一轮学习安排。");
  const [processStreamEvents, setProcessStreamEvents] = useState<Array<{ stage: string; payload: Record<string, unknown> }>>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<Array<{ stage: string; payload: Record<string, unknown> }>>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const [latestPlan, setLatestPlan] = useState<LearningPlan | null>(null);
  const [processBusy, setProcessBusy] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const selectedDocument = documents.find((document) => document.id === selectedId) ?? null;
  const coarseSections = debugRecord?.sections.filter((section) => section.level === 1) ?? [];
  const fineSections = debugRecord?.sections.filter((section) => section.level === 2) ?? [];
  const planningTraceRecord = planningTrace?.trace ?? null;
  const visiblePages = debugRecord?.pages.slice(0, 12) ?? [];
  const hiddenPageCount = Math.max(0, (debugRecord?.pages.length ?? 0) - visiblePages.length);
  const visibleChunks = debugRecord?.chunks.slice(0, 16) ?? [];
  const hiddenChunkCount = Math.max(0, (debugRecord?.chunks.length ?? 0) - visibleChunks.length);

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
        const remotePersonas = await listPersonas();
        if (active) {
          setPersonas(remotePersonas);
          if (remotePersonas[0]) {
            setSelectedPersonaId(remotePersonas[0].id);
          }
        }
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

  const handleReprocess = (forceOcr: boolean) => {
    if (!selectedId) {
      return;
    }
    const run = async () => {
      try {
        setProcessBusy(true);
        setProcessStreamEvents([]);
        setProcessStreamStatus("running");
        setMessage(forceOcr ? "正在执行强制 OCR 解析..." : "正在重新解析文档...");
        await processDocumentStream(selectedId, { forceOcr }, (event) => {
          setProcessStreamEvents((current) => [...current.slice(-39), event]);
          setProcessStreamStatus(resolveStreamStatus(event.stage));
          setMessage(`处理中: ${event.stage}`);
        });
        await refreshDocuments(selectedId, true, true);
        setMessage(forceOcr ? "强制 OCR 解析完成。" : "重新解析完成。");
      } catch (error) {
        setProcessStreamStatus("error");
        setMessage(`重新解析失败: ${String(error)}`);
      } finally {
        setProcessBusy(false);
      }
    };
    void run();
  };

  const handleGeneratePlan = () => {
    if (!selectedId) {
      return;
    }
    const run = async () => {
      try {
        setPlanBusy(true);
        setPlanStreamEvents([]);
        setPlanStreamStatus("running");
        setLatestPlan(null);
        setMessage("正在流式生成学习计划...");
        const plan = await createLearningPlanStream(
          {
            documentId: selectedId,
            personaId: selectedPersonaId,
            objective
          },
          (event) => {
            setPlanStreamEvents((current) => [...current.slice(-59), event]);
            setPlanStreamStatus(resolveStreamStatus(event.stage));
            setMessage(`计划处理中: ${event.stage}`);
          }
        );
        setLatestPlan(plan);
        await loadStreamReports(selectedId);
        const trace = await getDocumentPlanningTrace(selectedId);
        setPlanningTrace(trace);
        setMessage("学习计划生成完成。");
      } catch (error) {
        setPlanStreamStatus("error");
        setMessage(`计划生成失败: ${String(error)}`);
      } finally {
        setPlanBusy(false);
      }
    };
    void run();
  };

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.eyebrow}>Parser Debug Console</p>
          <h1 style={styles.title}>教材解析后台</h1>
          <p style={styles.subtitle}>
            这里展示解析链路的中间结果，而不是只看最终 sections。你可以直接检查页级抽取、候选标题、切块边界与告警。
          </p>
          <p style={styles.message}>{message}</p>
        </div>
        <a href="/" style={styles.link}>
          返回学习页
        </a>
      </section>

      <section style={styles.grid}>
        <aside style={styles.sidebar}>
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
            {selectedDocument ? (
              <div style={styles.actionRow}>
                <button
                  type="button"
                  style={styles.actionButton}
                  disabled={processBusy || planBusy}
                  onClick={() => handleReprocess(false)}
                >
                  {processBusy ? "处理中..." : "重新解析"}
                </button>
                <button
                  type="button"
                  style={styles.actionButtonAccent}
                  disabled={processBusy || planBusy}
                  onClick={() => handleReprocess(true)}
                >
                  {processBusy ? "处理中..." : "强制 OCR"}
                </button>
              </div>
            ) : null}
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
            {processStreamEvents.length ? (
              <div style={styles.list}>
                {processStreamEvents.map((event, index) => (
                  <div key={`${event.stage}-${index}`} style={styles.chunkCard}>
                    <strong>{event.stage}</strong>
                    <pre style={styles.pre}>{JSON.stringify(event.payload, null, 2)}</pre>
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.empty}>点击“重新解析”或“强制 OCR”后，这里会实时显示处理阶段。</p>
            )}
          </article>

          <article style={styles.card}>
            <h2 style={styles.sectionTitle}>流式生成学习计划</h2>
            <div style={styles.formGrid}>
              <label style={styles.field}>
                <span>教师人格</span>
                <select
                  value={selectedPersonaId}
                  onChange={(event) => setSelectedPersonaId(event.target.value)}
                  style={styles.select}
                >
                  {personas.map((persona) => (
                    <option key={persona.id} value={persona.id}>
                      {persona.name}
                    </option>
                  ))}
                </select>
              </label>
              <label style={styles.field}>
                <span>学习目标</span>
                <textarea
                  value={objective}
                  onChange={(event) => setObjective(event.target.value)}
                  style={styles.textarea}
                />
              </label>
            </div>
            <div style={styles.actionRow}>
              <button
                type="button"
                style={styles.actionButtonAccent}
                disabled={!selectedId || processBusy || planBusy}
                onClick={handleGeneratePlan}
              >
                {planBusy ? "生成中..." : "流式生成计划"}
              </button>
            </div>
            {latestPlan ? (
              <div style={styles.list}>
                <div style={styles.toolCard}>
                  <strong>{latestPlan.overview}</strong>
                  <span>
                    {latestPlan.todayTasks.length} 条今日任务 · {latestPlan.schedule.length} 条日程
                  </span>
                </div>
              </div>
            ) : null}
            {planStreamEvents.length ? (
              <div style={styles.list}>
                {planStreamEvents.map((event, index) => (
                  <div key={`${event.stage}-${index}`} style={styles.chunkCard}>
                    <strong>{event.stage}</strong>
                    <pre style={styles.pre}>{JSON.stringify(event.payload, null, 2)}</pre>
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.empty}>选择文档后，可以在这里流式观察学习计划生成过程。</p>
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
                    {coarseSections.map((section) => (
                      <div key={section.id} style={styles.listItem}>
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
                      fineSections.map((section) => (
                        <div key={section.id} style={styles.listItem}>
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
                        <pre style={styles.pre}>{round.thinking}</pre>
                      </div>
                    ) : (
                      <span style={styles.emptyInline}>无 reasoning/thinking 内容。</span>
                    )}
                    {round.assistantContent ? (
                      <div style={styles.detailBlock}>
                        <strong>Assistant content</strong>
                        <pre style={styles.pre}>{round.assistantContent}</pre>
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
                              <pre style={styles.preCompact}>{toolCall.argumentsJson}</pre>
                              <pre style={styles.preCompact}>{toolCall.resultJson}</pre>
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
                    <pre style={styles.pre}>{page.textPreview || "[empty]"}</pre>
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

function resolveStreamStatus(stage: string) {
  if (stage === "stream_completed") {
    return "completed";
  }
  if (stage === "stream_error") {
    return "error";
  }
  return "running";
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    padding: "32px 24px 48px"
  },
  hero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 20,
    alignItems: "flex-start",
    marginBottom: 24
  },
  eyebrow: {
    margin: 0,
    color: "var(--teal)",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    fontSize: 13,
    fontWeight: 700
  },
  title: {
    margin: "8px 0 10px",
    fontFamily: "var(--font-display), sans-serif",
    fontSize: "clamp(2rem, 5vw, 4rem)"
  },
  subtitle: {
    margin: 0,
    maxWidth: 760,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  message: {
    margin: "12px 0 0",
    color: "var(--accent)"
  },
  link: {
    padding: "12px 16px",
    borderRadius: 999,
    background: "var(--panel-strong)",
    border: "1px solid var(--border)",
    textDecoration: "none"
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "320px minmax(0, 1fr)",
    gap: 20
  },
  sidebar: {
    padding: 20,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)",
    display: "grid",
    gap: 12,
    alignContent: "start"
  },
  sidebarTitle: {
    margin: 0,
    fontSize: 20,
    fontFamily: "var(--font-display), sans-serif"
  },
  docButton: {
    textAlign: "left",
    display: "grid",
    gap: 6,
    padding: 14,
    borderRadius: 18,
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.72)",
    cursor: "pointer"
  },
  docButtonActive: {
    border: "1px solid var(--accent)",
    background: "var(--accent-soft)"
  },
  content: {
    display: "grid",
    gap: 18
  },
  summaryCard: {
    padding: 22,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  sectionTitle: {
    margin: 0,
    fontSize: 22,
    fontFamily: "var(--font-display), sans-serif"
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: 12,
    marginTop: 16
  },
  actionRow: {
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
    marginTop: 16
  },
  actionButton: {
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.84)",
    padding: "10px 14px",
    borderRadius: 999,
    cursor: "pointer"
  },
  actionButtonAccent: {
    border: "1px solid rgba(197,92,59,0.24)",
    background: "var(--accent-soft)",
    padding: "10px 14px",
    borderRadius: 999,
    cursor: "pointer"
  },
  summaryItem: {
    display: "grid",
    gap: 4,
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.78)",
    border: "1px solid var(--border)"
  },
  card: {
    padding: 22,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  formGrid: {
    display: "grid",
    gap: 12,
    marginTop: 14
  },
  field: {
    display: "grid",
    gap: 8
  },
  input: {
    width: "100%",
    borderRadius: 14,
    border: "1px solid var(--border)",
    padding: "10px 12px",
    background: "rgba(255,255,255,0.9)"
  },
  select: {
    width: "100%",
    borderRadius: 14,
    border: "1px solid var(--border)",
    padding: "10px 12px",
    background: "rgba(255,255,255,0.9)"
  },
  textarea: {
    width: "100%",
    minHeight: 88,
    borderRadius: 16,
    border: "1px solid var(--border)",
    padding: 12,
    background: "rgba(255,255,255,0.9)",
    resize: "vertical"
  },
  list: {
    display: "grid",
    gap: 10,
    marginTop: 14
  },
  sectionGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 16,
    marginTop: 14
  },
  sectionColumn: {
    display: "grid",
    gap: 10,
    alignContent: "start"
  },
  sectionColumnHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    color: "var(--muted)"
  },
  listItem: {
    display: "grid",
    gap: 6,
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.78)",
    border: "1px solid var(--border)"
  },
  childChipRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap"
  },
  toolRow: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12
  },
  toolCard: {
    display: "grid",
    gap: 6,
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.78)",
    border: "1px solid var(--border)"
  },
  detailBlock: {
    display: "grid",
    gap: 10
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
    padding: "4px 8px",
    borderRadius: 999,
    background: "rgba(45,36,31,0.08)",
    color: "var(--muted)",
    fontSize: 12,
    fontWeight: 700
  },
  sectionLevelBadgeFine: {
    padding: "4px 8px",
    borderRadius: 999,
    background: "var(--accent-soft)",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 700
  },
  warningItem: {
    display: "grid",
    gap: 6,
    padding: 14,
    borderRadius: 18,
    background: "rgba(197,92,59,0.12)",
    border: "1px solid rgba(197,92,59,0.24)"
  },
  chunkGrid: {
    display: "grid",
    gap: 12,
    marginTop: 14
  },
  chunkCard: {
    display: "grid",
    gap: 8,
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.78)",
    border: "1px solid var(--border)"
  },
  chunkCardCollapsed: {
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.56)",
    border: "1px dashed var(--border)",
    color: "var(--muted)"
  },
  traceSummary: {
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.5
  },
  pageList: {
    display: "grid",
    gap: 12,
    marginTop: 14
  },
  pageCard: {
    display: "grid",
    gap: 10,
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.78)",
    border: "1px solid var(--border)"
  },
  pageCardCollapsed: {
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.56)",
    border: "1px dashed var(--border)",
    color: "var(--muted)"
  },
  pageMeta: {
    display: "grid",
    gap: 4
  },
  headingRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap"
  },
  headingTag: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "var(--accent-soft)",
    fontSize: 12
  },
  headingTagMuted: {
    padding: "6px 10px",
    borderRadius: 999,
    background: "rgba(45,36,31,0.08)",
    fontSize: 12,
    color: "var(--muted)"
  },
  pre: {
    margin: 0,
    padding: 14,
    borderRadius: 14,
    background: "rgba(45,36,31,0.92)",
    color: "#fff6ed",
    whiteSpace: "pre-wrap",
    lineHeight: 1.6,
    overflowX: "auto"
  },
  preCompact: {
    margin: 0,
    padding: 12,
    borderRadius: 14,
    background: "rgba(45,36,31,0.92)",
    color: "#fff6ed",
    whiteSpace: "pre-wrap",
    lineHeight: 1.5,
    overflowX: "auto",
    fontSize: 13
  },
  empty: {
    margin: "14px 0 0",
    color: "var(--muted)"
  }
};

function truncateText(text: string, maxChars: number) {
  const normalized = (text || "").trim();
  if (normalized.length <= maxChars) {
    return normalized;
  }
  return `${normalized.slice(0, maxChars).trimEnd()}...`;
}
