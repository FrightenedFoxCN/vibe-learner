"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import type { DocumentRecord, DocumentSection, LearningPlan, StudyUnit } from "@vibe-learner/shared";

import { useLearningWorkspace } from "./learning-workspace-provider";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

export function StudyDialogPage() {
  const {
    selectedPersona,
    activePlan,
    activeDocument,
    planHistory,
    planHistoryItems,
    planSections,
    selectPlan,
    studySession,
    response,
    notice,
    isBusy,
    createSessionForActivePlan,
    handleAsk,
    handleAskForSection,
    chatFailure,
    retryFailedAsk,
    handleSwitchSection,
    handleSubmitQuestionAttempt,
  } = useLearningWorkspace();

  const [pdfPage, setPdfPage] = useState(1);
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(false);
  const [selectedChapter, setSelectedChapter] = useState("");
  const [selectedSubsectionId, setSelectedSubsectionId] = useState("");
  const [requestedPlanId, setRequestedPlanId] = useState("");
  const [requestedChapter, setRequestedChapter] = useState("");
  const [requestedSubsectionId, setRequestedSubsectionId] = useState("");
  const [requestedPage, setRequestedPage] = useState(0);

  const chapterOptions = activePlan?.studyChapters ?? [];
  const currentChapter = selectedChapter || chapterOptions[0] || "";
  const activeSceneProfile = studySession?.sceneProfile ?? activePlan?.sceneProfile ?? null;
  const activeSceneSourceLabel = studySession?.sceneProfile
    ? "会话副本"
    : activePlan?.sceneProfile
      ? "学习计划"
      : "";
  const currentChapterStudyUnit = resolveStudyUnitByChapter(activePlan, currentChapter);
  const subsectionOptions = resolveSubsectionsForStudyUnit(activeDocument, currentChapterStudyUnit);

  const resolveSectionIdByChapter = useCallback(
    (chapter: string) => {
      if (!chapter) return "";
      const chapterIndex = chapterOptions.findIndex((item) => item === chapter);
      const exactFocusMatch = activePlan?.schedule.find((item) => {
        const focus = item.focus?.trim() ?? "";
        return focus === chapter || focus.includes(chapter) || chapter.includes(focus);
      });
      if (exactFocusMatch?.unitId) return exactFocusMatch.unitId;

      const chapterScopedUnitIds = (activePlan?.studyUnits ?? [])
        .filter((unit) => unit.includeInPlan)
        .map((unit) => unit.id);

      if (chapterIndex >= 0 && chapterScopedUnitIds[chapterIndex]) {
        return chapterScopedUnitIds[chapterIndex];
      }
      if (chapterIndex >= 0) {
        if (planSections[chapterIndex]?.id) return planSections[chapterIndex].id;
        const uniqueUnitIds = Array.from(
          new Set((activePlan?.schedule ?? []).map((item) => item.unitId).filter(Boolean))
        );
        if (uniqueUnitIds[chapterIndex]) return uniqueUnitIds[chapterIndex];
      }
      return planSections[0]?.id ?? "";
    },
    [activePlan?.schedule, activePlan?.studyUnits, chapterOptions, planSections]
  );

  const handleChapterChange = useCallback(
    (chapter: string) => {
      setSelectedChapter(chapter);
      setSelectedSubsectionId("");
      if (!studySession) return;
      const nextSectionId = resolveSectionIdByChapter(chapter);
      if (nextSectionId && nextSectionId !== studySession.sectionId) {
        void handleSwitchSection(nextSectionId);
      }
    },
    [handleSwitchSection, resolveSectionIdByChapter, studySession]
  );

  const resolveChapterStartPage = useCallback(
    (chapter: string) => {
      const sectionId = resolveSectionIdByChapter(chapter);
      if (!sectionId) return 0;
      const fromPlanSection = planSections.find((section) => section.id === sectionId)?.pageStart;
      if (fromPlanSection) return fromPlanSection;
      const fromStudyUnit = activeDocument?.studyUnits.find((unit) => unit.id === sectionId)?.pageStart;
      if (fromStudyUnit) return fromStudyUnit;
      const fromRawSection = activeDocument?.sections.find((section) => section.id === sectionId)?.pageStart;
      if (fromRawSection) return fromRawSection;
      return 0;
    },
    [activeDocument?.sections, activeDocument?.studyUnits, planSections, resolveSectionIdByChapter]
  );

  const handleOpenPdfPage = useCallback((page: number) => {
    setPdfPage(page);
    setIsPdfPreviewOpen(true);
  }, []);

  const handleSubsectionChange = useCallback(
    (subsectionId: string) => {
      setSelectedSubsectionId(subsectionId);

      if (!subsectionId) {
        const chapterSectionId = resolveSectionIdByChapter(currentChapter);
        const chapterStartPage = resolveChapterStartPage(currentChapter);
        if (chapterStartPage > 0) {
          handleOpenPdfPage(chapterStartPage);
        }
        if (studySession && chapterSectionId && chapterSectionId !== studySession.sectionId) {
          void handleSwitchSection(chapterSectionId);
        }
        return;
      }

      const targetSubsection = subsectionOptions.find((section) => section.id === subsectionId);
      if (targetSubsection) {
        handleOpenPdfPage(targetSubsection.pageStart);
      }
      if (studySession && subsectionId !== studySession.sectionId) {
        void handleSwitchSection(subsectionId);
      }
    },
    [
      currentChapter,
      handleOpenPdfPage,
      handleSwitchSection,
      resolveChapterStartPage,
      resolveSectionIdByChapter,
      studySession,
      subsectionOptions
    ]
  );

  const handleJumpToChapterStart = useCallback(() => {
    const nextPage = resolveChapterStartPage(currentChapter);
    if (nextPage > 0) handleOpenPdfPage(nextPage);
  }, [currentChapter, handleOpenPdfPage, resolveChapterStartPage]);

  const handleAskByCurrentChapter = useCallback(
    async (message: string) => {
      const targetSectionId = selectedSubsectionId || resolveSectionIdByChapter(currentChapter);
      if (targetSectionId) {
        await handleAskForSection(message, targetSectionId);
        return;
      }
      await handleAsk(message);
    },
    [currentChapter, handleAsk, handleAskForSection, resolveSectionIdByChapter, selectedSubsectionId]
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setRequestedPlanId(params.get("plan") ?? "");
    setRequestedChapter(params.get("chapter") ?? "");
    setRequestedSubsectionId(params.get("subsection") ?? "");
    setRequestedPage(Number(params.get("page") ?? "0"));
  }, []);

  useEffect(() => {
    if (!requestedPlanId || requestedPlanId === activePlan?.id) return;
    selectPlan(requestedPlanId, PLAN_SWITCH_NOTICE);
  }, [activePlan?.id, requestedPlanId, selectPlan]);

  useEffect(() => {
    if (!chapterOptions.length) { setSelectedChapter(""); return; }
    if (requestedChapter && chapterOptions.includes(requestedChapter) && requestedChapter !== selectedChapter) {
      setSelectedChapter(requestedChapter);
      setSelectedSubsectionId("");
      return;
    }
    if (!selectedChapter || !chapterOptions.includes(selectedChapter)) {
      setSelectedChapter(chapterOptions[0]);
      setSelectedSubsectionId("");
    }
  }, [activePlan?.id, chapterOptions, requestedChapter, selectedChapter]);

  useEffect(() => {
    if (!selectedSubsectionId) return;
    if (subsectionOptions.some((section) => section.id === selectedSubsectionId)) {
      return;
    }
    setSelectedSubsectionId("");
  }, [selectedSubsectionId, subsectionOptions]);

  useEffect(() => {
    if (!requestedSubsectionId || !subsectionOptions.length) return;
    if (!subsectionOptions.some((section) => section.id === requestedSubsectionId)) return;
    setSelectedSubsectionId((current) => current || requestedSubsectionId);
  }, [requestedSubsectionId, subsectionOptions]);

  useEffect(() => {
    const firstPage = activeDocument?.sections[0]?.pageStart;
    if (firstPage) {
      setPdfPage(firstPage);
      setIsPdfPreviewOpen(true);
    }
  }, [activeDocument?.id]);

  useEffect(() => {
    if (!Number.isFinite(requestedPage) || requestedPage <= 0) return;
    setPdfPage(requestedPage);
    setIsPdfPreviewOpen(true);
  }, [requestedPage, activeDocument?.id]);

  useEffect(() => {
    if (!studySession || !currentChapter) return;
    const nextSectionId = selectedSubsectionId || resolveSectionIdByChapter(currentChapter);
    if (nextSectionId && nextSectionId !== studySession.sectionId) {
      void handleSwitchSection(nextSectionId);
    }
  }, [
    currentChapter,
    handleSwitchSection,
    resolveSectionIdByChapter,
    selectedSubsectionId,
    studySession?.id,
    studySession?.sectionId,
  ]);

  const pdfSrc = activeDocument ? `${AI_BASE_URL}/documents/${activeDocument.id}/file#page=${pdfPage}` : "";

  return (
    <main className="with-app-nav study-dialog-page" style={styles.page}>
      <TopNav currentPath="/study" />

      {/* ── Heading ── */}
      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>章节对话</h1>
        <p style={styles.pageDesc}>让对话成为主界面；章节切换、练习反馈与教材引用围绕同一个会话流展开，教材预览收进可收拢浮窗。</p>
      </div>

      {/* ── Toolbar ── */}
      <div style={styles.toolbar}>
        <div style={styles.toolbarField}>
          <span style={styles.toolbarLabel}>学习计划</span>
          <select
            style={styles.planSelect}
            value={activePlan?.id ?? ""}
            onChange={(event) => selectPlan(event.target.value, PLAN_SWITCH_NOTICE)}
            disabled={!planHistory.length}
          >
            {planHistoryItems.length ? (
              planHistoryItems.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.courseTitle} · {item.documentTitle}
                </option>
              ))
            ) : (
              <option value="">暂无学习计划</option>
            )}
          </select>
        </div>

        {!studySession ? (
          <button
            type="button"
            style={{
              ...styles.createBtn,
              ...(isBusy || !activePlan || !activeDocument ? styles.createBtnDisabled : {})
            }}
            disabled={isBusy || !activePlan || !activeDocument}
            onClick={() => { void createSessionForActivePlan(); }}
          >
            {isBusy ? "创建中…" : "创建会话"}
          </button>
        ) : null}

        <Link href="/plan" style={styles.toolbarLink}>返回计划生成</Link>
        {notice ? <span style={styles.notice}>{notice}</span> : null}
      </div>

      <section style={styles.mainStage}>
          <StudyConsole
            isPending={isBusy}
            onAsk={handleAskByCurrentChapter}
            onSubmitQuestionAttempt={handleSubmitQuestionAttempt}
            onChangeChapter={handleChapterChange}
            onOpenPage={handleOpenPdfPage}
            onJumpToChapterStart={handleJumpToChapterStart}
            chatErrorMessage={chatFailure?.detail ?? ""}
            onRetryLastAsk={retryFailedAsk}
            selectedChapter={currentChapter}
            studyChapters={chapterOptions}
            selectedSubsectionId={selectedSubsectionId}
            subsectionOptions={subsectionOptions}
            onChangeSubsection={handleSubsectionChange}
            turns={studySession?.turns ?? []}
            session={response}
            persona={selectedPersona}
            sceneProfile={activeSceneProfile}
            sceneSourceLabel={activeSceneSourceLabel}
            sceneInstanceId={studySession?.sceneInstanceId ?? ""}
            onTogglePdfPreview={() => setIsPdfPreviewOpen((current) => !current)}
            isPdfPreviewOpen={isPdfPreviewOpen}
            canOpenPdfPreview={Boolean(activeDocument)}
            disabled={!studySession}
          />
      </section>

      {activeDocument ? (
        isPdfPreviewOpen ? (
          <aside className="study-dialog-pdf-window" style={styles.pdfWindow}>
            <div style={styles.pdfHeader}>
              <div style={styles.pdfHeaderMeta}>
                <span style={styles.pdfTitle}>{activeDocument.title}</span>
                <span style={styles.pdfSubtitle}>第 {pdfPage} 页</span>
              </div>
              <button
                type="button"
                style={styles.pdfCollapseBtn}
                onClick={() => setIsPdfPreviewOpen(false)}
              >
                收拢
              </button>
            </div>
            <iframe title="textbook-pdf" src={pdfSrc} className="study-dialog-pdf-iframe" style={styles.iframe} />
          </aside>
        ) : (
          <button
            type="button"
            className="study-dialog-pdf-dock"
            style={styles.pdfDock}
            onClick={() => setIsPdfPreviewOpen(true)}
          >
            教材浮窗 · p.{pdfPage}
          </button>
        )
      ) : (
        <div style={styles.emptyDock}>请先在计划页完成教材上传并生成学习计划。</div>
      )}
    </main>
  );
}

function resolveStudyUnitByChapter(
  plan: LearningPlan | null,
  chapter: string
): StudyUnit | null {
  if (!plan || !chapter) {
    return null;
  }

  const chapterIndex = plan.studyChapters.findIndex((item) => item === chapter);
  const exactFocusMatch = plan.schedule.find((item) => {
    const focus = item.focus?.trim() ?? "";
    return focus === chapter || focus.includes(chapter) || chapter.includes(focus);
  });
  if (exactFocusMatch?.unitId) {
    const matchedUnit = plan.studyUnits.find((unit) => unit.id === exactFocusMatch.unitId);
    if (matchedUnit) {
      return matchedUnit;
    }
  }

  const chapterScopedUnits = plan.studyUnits.filter((unit) => unit.includeInPlan);
  if (chapterIndex >= 0 && chapterScopedUnits[chapterIndex]) {
    return chapterScopedUnits[chapterIndex];
  }

  if (chapterIndex >= 0) {
    const uniqueUnitIds = Array.from(new Set(plan.schedule.map((item) => item.unitId).filter(Boolean)));
    const fallbackUnitId = uniqueUnitIds[chapterIndex];
    if (fallbackUnitId) {
      return plan.studyUnits.find((unit) => unit.id === fallbackUnitId) ?? null;
    }
  }

  return null;
}

function resolveSubsectionsForStudyUnit(
  document: DocumentRecord | null,
  studyUnit: StudyUnit | null
): DocumentSection[] {
  if (!document || !studyUnit) {
    return [];
  }

  const sectionMap = new Map(document.sections.map((section) => [section.id, section]));
  const directMatches = studyUnit.sourceSectionIds
    .map((sectionId) => sectionMap.get(sectionId))
    .filter((section): section is DocumentSection => Boolean(section));
  const scopeSections = directMatches.length ? directMatches : [studyUnit];
  const candidates = document.sections
    .filter((section) =>
      scopeSections.some((scope) =>
        Math.max(scope.pageStart, section.pageStart) <= Math.min(scope.pageEnd, section.pageEnd)
      )
    )
    .filter((section) => section.level >= 2)
    .sort((left, right) =>
      left.pageStart - right.pageStart ||
      left.level - right.level ||
      left.pageEnd - right.pageEnd ||
      left.id.localeCompare(right.id)
    );

  return candidates.filter(
    (section, index) => candidates.findIndex((candidate) => candidate.id === section.id) === index
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "28px 32px 16px",
    display: "grid",
    gap: 0,
    alignContent: "start",
  },
  /* Heading */
  heading: {
    display: "grid",
    gap: 6,
    paddingBottom: 16,
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  pageDesc: {
    margin: 0,
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  /* Toolbar */
  toolbar: {
    display: "flex",
    alignItems: "flex-end",
    gap: 20,
    paddingBottom: 20,
    paddingTop: 4,
    marginBottom: 24,
    borderBottom: "1px solid var(--border)",
    flexWrap: "wrap",
  },
  toolbarField: {
    display: "grid",
    gap: 5,
  },
  toolbarLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  notice: {
    fontSize: 12,
    color: "var(--teal)",
    alignSelf: "center",
    paddingBottom: 2,
  },
  planSelect: {
    height: 32,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--ink)",
    padding: "0 8px",
    minWidth: 260,
    maxWidth: 480,
    fontSize: 13,
  },
  createBtn: {
    border: "1px solid var(--accent)",
    height: 32,
    padding: "0 14px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
  },
  createBtnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  toolbarLink: {
    fontSize: 12,
    color: "var(--accent)",
    fontWeight: 600,
    alignSelf: "center",
    paddingBottom: 2,
  },
  mainStage: {
    minWidth: 0,
  },
  pdfWindow: {
    position: "fixed",
    top: 30,
    right: 0,
    bottom: "auto",
    zIndex: 35,
    display: "flex",
    flexDirection: "column",
    width: "min(440px, calc(100vw - 40px))",
    height: "min(72vh, calc(100vh - 120px))",
    border: "1px solid var(--border)",
    borderTop: "1px solid var(--border)",
    borderRadius: 20,
    background: "color-mix(in srgb, white 94%, var(--panel))",
    boxShadow: "0 28px 72px rgba(13, 32, 40, 0.18)",
    overflow: "hidden",
  },
  pdfHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    padding: "14px 14px 12px",
    borderBottom: "1px solid var(--border)",
    background: "linear-gradient(180deg, #fbfdfe 0%, #f3f7f8 100%)",
  },
  pdfHeaderMeta: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  pdfTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  pdfSubtitle: {
    fontSize: 12,
    color: "var(--muted)",
  },
  pdfCollapseBtn: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink-2)",
    height: 32,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  iframe: {
    width: "100%",
    flex: 1,
    minHeight: 0,
    border: "none",
    background: "white",
    display: "block",
  },
  pdfDock: {
    position: "fixed",
    right: 0,
    top: 30,
    transform: "none",
    zIndex: 35,
    border: "1px solid var(--accent)",
    background: "var(--accent)",
    color: "white",
    minHeight: 0,
    width: "auto",
    height: 42,
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    boxShadow: "0 18px 44px rgba(10, 103, 114, 0.2)",
    borderRadius: 999,
    letterSpacing: "0.03em",
  },
  emptyDock: {
    position: "fixed",
    right: 0,
    top: 60,
    transform: "none",
    zIndex: 20,
    width: "auto",
    maxWidth: 220,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    borderRadius: 16,
    background: "rgba(255, 255, 255, 0.96)",
    color: "var(--muted)",
    fontSize: 12,
    lineHeight: 1.6,
  },
};
