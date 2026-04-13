"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import type { Citation, DocumentRecord, DocumentSection, LearningPlan, StudySessionRecord, StudyUnit } from "@vibe-learner/shared";

import { useLearningWorkspace } from "./learning-workspace-provider";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";
const ProjectedPdfViewer = dynamic(
  () => import("./projected-pdf-viewer").then((module) => module.ProjectedPdfViewer),
  { ssr: false }
);
const ProjectedImageViewer = dynamic(
  () => import("./projected-image-viewer").then((module) => module.ProjectedImageViewer),
  { ssr: false }
);

type PreviewState =
  | {
      kind: "document";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
    }
  | {
      kind: "attachment_pdf";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
    }
  | {
      kind: "attachment_image";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
    };

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
    chatImageUploadEnabled,
    createSessionForActivePlan,
    handleAsk,
    handleAskForSection,
    chatFailure,
    retryFailedAsk,
    handleSwitchSection,
    handleSubmitQuestionAttempt,
    handleResolvePlanConfirmation,
  } = useLearningWorkspace();

  const [pdfPage, setPdfPage] = useState(1);
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(false);
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const [pendingComposerInsert, setPendingComposerInsert] = useState<{ id: string; text: string } | null>(null);
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
  const projectedPdf = studySession?.projectedPdf ?? null;
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
  const chapterStartPage = resolveChapterStartPage(currentChapter);
  const chapterSectionId = resolveSectionIdByChapter(currentChapter);

  const handleOpenPdfPage = useCallback((page: number) => {
    setPdfPage(page);
    if (activeDocument) {
      setPreviewState({
        kind: "document",
        sourceId: activeDocument.id,
        title: activeDocument.title,
        page: page,
        pageCount: activeDocument.pageCount,
      });
    }
    setIsPdfPreviewOpen(true);
  }, [activeDocument]);

  const handleOpenCitation = useCallback((citation: Citation) => {
    const targetPage = Math.max(1, citation.pageStart || 1);
    if (citation.sourceKind === "attachment_pdf" && studySession?.id) {
      const attachment = resolvePreviewableAttachmentById(studySession, citation.sourceId || citation.sectionId, "pdf");
      if (attachment) {
        setPreviewState({
          kind: "attachment_pdf",
          sourceId: attachment.attachmentId,
          title: attachment.name,
          page: targetPage,
          pageCount: attachment.pageCount ?? 0,
        });
        setIsPdfPreviewOpen(true);
        return;
      }
    }
    if (citation.sourceKind === "attachment_image" && studySession?.id) {
      const attachment = resolvePreviewableAttachmentById(studySession, citation.sourceId || citation.sectionId, "image");
      if (attachment) {
        setPreviewState({
          kind: "attachment_image",
          sourceId: attachment.attachmentId,
          title: attachment.name,
          page: 1,
          pageCount: 1,
        });
        setIsPdfPreviewOpen(true);
        return;
      }
    }
    if (activeDocument) {
      setPdfPage(targetPage);
      setPreviewState({
        kind: "document",
        sourceId: activeDocument.id,
        title: activeDocument.title,
        page: targetPage,
        pageCount: activeDocument.pageCount,
      });
      setIsPdfPreviewOpen(true);
    }
  }, [activeDocument, studySession]);

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
    setSelectedSubsectionId("");
    if (chapterStartPage > 0) {
      handleOpenPdfPage(chapterStartPage);
    }
    if (studySession && chapterSectionId && chapterSectionId !== studySession.sectionId) {
      void handleSwitchSection(chapterSectionId);
    }
  }, [chapterSectionId, chapterStartPage, handleOpenPdfPage, handleSwitchSection, studySession]);

  const handleAskByCurrentChapter = useCallback(
    async (message: string, attachments: File[] = []) => {
      const targetSectionId = selectedSubsectionId || resolveSectionIdByChapter(currentChapter);
      if (targetSectionId) {
        await handleAskForSection(message, targetSectionId, attachments);
        return;
      }
      await handleAsk(message, attachments);
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
    if (projectedPdf) return;
    if (firstPage) {
      setPdfPage(firstPage);
      setPreviewState({
        kind: "document",
        sourceId: activeDocument.id,
        title: activeDocument.title,
        page: firstPage,
        pageCount: activeDocument.pageCount,
      });
      setIsPdfPreviewOpen(true);
    }
  }, [activeDocument?.id, activeDocument?.pageCount, activeDocument?.title, projectedPdf]);

  useEffect(() => {
    if (!Number.isFinite(requestedPage) || requestedPage <= 0) return;
    if (projectedPdf) return;
    setPdfPage(requestedPage);
    if (activeDocument) {
      setPreviewState({
        kind: "document",
        sourceId: activeDocument.id,
        title: activeDocument.title,
        page: requestedPage,
        pageCount: activeDocument.pageCount,
      });
    }
    setIsPdfPreviewOpen(true);
  }, [requestedPage, activeDocument?.id, activeDocument?.pageCount, activeDocument?.title, projectedPdf]);

  useEffect(() => {
    if (!projectedPdf) return;
    setPreviewState({
      kind:
        projectedPdf.sourceKind === "attachment_pdf"
          ? "attachment_pdf"
          : projectedPdf.sourceKind === "attachment_image"
            ? "attachment_image"
            : "document",
      sourceId: projectedPdf.sourceId,
      title: projectedPdf.title,
      page: projectedPdf.pageNumber,
      pageCount: projectedPdf.pageCount,
    });
    setIsPdfPreviewOpen(true);
  }, [
    projectedPdf?.pageNumber,
    projectedPdf?.pageCount,
    projectedPdf?.sourceId,
    projectedPdf?.sourceKind,
    projectedPdf?.title,
    projectedPdf?.updatedAt,
  ]);

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

  const effectivePreview = previewState;
  const previewPage = effectivePreview?.page ?? pdfPage;
  const previewTitle = effectivePreview?.title ?? activeDocument?.title ?? "";
  const previewFileHref =
    effectivePreview?.kind === "document"
      ? `${AI_BASE_URL}/documents/${effectivePreview.sourceId}/file`
      : (effectivePreview?.kind === "attachment_pdf" || effectivePreview?.kind === "attachment_image") && studySession?.id
        ? `${AI_BASE_URL}/study-sessions/${studySession.id}/attachments/${effectivePreview.sourceId}/file`
        : "";
  const previewPageCount = effectivePreview?.pageCount ?? activeDocument?.pageCount ?? 0;
  const previewFileUrl =
    effectivePreview?.kind === "document"
      ? `${AI_BASE_URL}/documents/${effectivePreview.sourceId}/file`
      : (effectivePreview?.kind === "attachment_pdf" || effectivePreview?.kind === "attachment_image") && studySession?.id
        ? `${AI_BASE_URL}/study-sessions/${studySession.id}/attachments/${effectivePreview.sourceId}/file`
        : "";
  const previewOverlays =
    (effectivePreview?.kind === "attachment_pdf" || effectivePreview?.kind === "attachment_image") &&
    projectedPdf?.sourceId === effectivePreview.sourceId
      ? projectedPdf.overlays.filter((item) => item.pageNumber === previewPage)
      : [];

  return (
    <main className="with-app-nav study-dialog-page" style={styles.page}>
      <TopNav currentPath="/study" />

      {/* ── Heading ── */}
      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>章节对话</h1>
        <p style={styles.pageDesc}>让对话成为主界面；章节切换、练习反馈与教材引用围绕同一个会话流展开，教材预览统一收进右侧浮窗。</p>
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
              ...(isBusy || !activePlan ? styles.createBtnDisabled : {})
            }}
            disabled={isBusy || !activePlan}
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
            onOpenCitation={handleOpenCitation}
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
            pendingFollowUps={studySession?.pendingFollowUps ?? []}
            affinityState={studySession?.affinityState}
            projectedPdf={studySession?.projectedPdf ?? null}
            planConfirmations={studySession?.planConfirmations ?? []}
            onResolvePlanConfirmation={handleResolvePlanConfirmation}
            chatImageUploadEnabled={chatImageUploadEnabled}
            pendingComposerInsert={pendingComposerInsert}
            onConsumeComposerInsert={() => setPendingComposerInsert(null)}
            canJumpToChapterStart={chapterStartPage > 0}
            disabled={!studySession}
          />
      </section>

      {effectivePreview ? (
        isPdfPreviewOpen ? (
          <aside className="study-dialog-pdf-window" style={styles.pdfWindow}>
            <div style={styles.pdfHeader}>
              <div style={styles.pdfHeaderMeta}>
                <span style={styles.pdfTitle}>{previewTitle}</span>
                <span style={styles.pdfSubtitle}>
                  {effectivePreview.kind === "attachment_pdf"
                    ? "会话材料"
                    : effectivePreview.kind === "attachment_image"
                      ? "会话图片"
                      : "教材材料"}
                  {effectivePreview.kind === "attachment_image"
                    ? " · 可框选引用与标注"
                    : ` · 第 ${previewPage} 页${previewPageCount > 0 ? ` / ${previewPageCount}` : ""}`}
                </span>
              </div>
              <div style={styles.pdfHeaderActions}>
                <button
                  type="button"
                  style={{
                    ...styles.pdfNavBtn,
                    ...(previewPage <= 1 ? styles.pdfNavBtnDisabled : {})
                  }}
                  onClick={() => {
                    if (!effectivePreview || previewPage <= 1) return;
                    if (effectivePreview.kind === "attachment_image") return;
                    const nextPage = previewPage - 1;
                    setPdfPage(nextPage);
                    setPreviewState({ ...effectivePreview, page: nextPage });
                  }}
                  disabled={previewPage <= 1 || effectivePreview.kind === "attachment_image"}
                >
                  上一页
                </button>
                <button
                  type="button"
                  style={{
                    ...styles.pdfNavBtn,
                    ...(previewPageCount > 0 && previewPage >= previewPageCount ? styles.pdfNavBtnDisabled : {})
                  }}
                  onClick={() => {
                    if (!effectivePreview) return;
                    if (effectivePreview.kind === "attachment_image") return;
                    if (previewPageCount > 0 && previewPage >= previewPageCount) return;
                    const nextPage = previewPage + 1;
                    setPdfPage(nextPage);
                    setPreviewState({ ...effectivePreview, page: nextPage });
                  }}
                  disabled={effectivePreview.kind === "attachment_image" || (previewPageCount > 0 && previewPage >= previewPageCount)}
                >
                  下一页
                </button>
                {previewFileHref ? (
                  <a href={previewFileHref} target="_blank" rel="noreferrer" style={styles.pdfOpenLink}>
                    打开原件
                  </a>
                ) : null}
                <button
                  type="button"
                  style={styles.pdfCollapseBtn}
                  onClick={() => setIsPdfPreviewOpen(false)}
                >
                  收拢
                </button>
              </div>
            </div>
            <div style={styles.previewStage}>
              {previewFileUrl ? (
                <div style={styles.previewCanvas}>
                  {effectivePreview?.kind === "attachment_image" ? (
                    <ProjectedImageViewer
                      fileUrl={previewFileUrl}
                      title={previewTitle}
                      overlays={previewOverlays}
                      onInsertReference={(text) => {
                        setPendingComposerInsert({
                          id: `${Date.now()}:image:${text.slice(0, 24)}`,
                          text,
                        });
                      }}
                    />
                  ) : (
                    <ProjectedPdfViewer
                      fileUrl={previewFileUrl}
                      title={previewTitle}
                      pageNumber={previewPage}
                      overlays={previewOverlays}
                      onPageCountChange={(pageCount) => {
                        if (!effectivePreview) return;
                        setPreviewState((current) =>
                          current
                            ? {
                                ...current,
                                pageCount,
                              }
                            : current
                        );
                      }}
                      onInsertReference={(text) => {
                        setPendingComposerInsert({
                          id: `${Date.now()}:${previewPage}:${text.slice(0, 24)}`,
                          text,
                        });
                      }}
                    />
                  )}
                </div>
              ) : (
                <div style={styles.previewEmptyState}>当前页暂时无法渲染。</div>
              )}
            </div>
          </aside>
        ) : (
          <button
            type="button"
            className="study-dialog-pdf-dock"
            style={styles.pdfDock}
            onClick={() => setIsPdfPreviewOpen(true)}
          >
            材料预览 · {effectivePreview.kind === "attachment_image" ? "图像" : `p.${previewPage}`}
          </button>
        )
      ) : (
        <div style={styles.emptyDock}>
          {activePlan
            ? "当前计划未关联教材，可直接围绕章节目标展开对话。"
            : "请先在计划页完成教材上传或目标计划生成。"}
        </div>
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

function resolvePreviewableAttachmentById(
  session: StudySessionRecord | null | undefined,
  attachmentId: string,
  kind?: "pdf" | "image"
) {
  const normalizedId = attachmentId.trim();
  if (!session || !normalizedId) {
    return null;
  }
  for (const turn of session.turns) {
    const match = turn.learnerAttachments?.find(
      (attachment) =>
        attachment.attachmentId === normalizedId &&
        attachment.previewable &&
        (!kind || attachment.kind === kind)
    );
    if (match) {
      return match;
    }
  }
  return null;
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
    width: "min(430px, calc(100vw - 36px))",
    height: "min(72vh, calc(100vh - 120px))",
    border: "1px solid var(--border)",
    borderRadius: 18,
    background: "rgba(255, 255, 255, 0.98)",
    boxShadow: "0 20px 56px rgba(13, 32, 40, 0.14)",
    overflow: "hidden",
  },
  pdfHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    padding: "12px 12px 10px",
    borderBottom: "1px solid var(--border)",
    background: "rgba(246, 249, 250, 0.96)",
  },
  pdfHeaderMeta: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  pdfHeaderActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "flex-end",
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
  pdfNavBtn: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    height: 32,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  pdfNavBtnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  pdfOpenLink: {
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 700,
    textDecoration: "none",
    padding: "6px 2px",
  },
  previewStage: {
    width: "100%",
    flex: 1,
    minHeight: 0,
    background: "linear-gradient(180deg, #f1f5f7 0%, #e4ebef 100%)",
    overflow: "auto",
    padding: 12,
  },
  previewCanvas: {
    position: "relative",
    width: "100%",
    background: "white",
    border: "1px solid rgba(15, 23, 42, 0.08)",
    borderRadius: 14,
    boxShadow: "0 12px 24px rgba(15, 23, 42, 0.10)",
    overflow: "hidden",
  },
  overlayBox: {
    position: "absolute",
    border: "2px solid #FACC15",
    boxSizing: "border-box",
    pointerEvents: "none",
  },
  overlayLabel: {
    position: "absolute",
    left: 0,
    top: -24,
    maxWidth: 220,
    color: "#0f172a",
    fontSize: 11,
    fontWeight: 700,
    lineHeight: 1.2,
    padding: "4px 6px",
    borderRadius: 6,
    boxShadow: "0 8px 18px rgba(15, 23, 42, 0.12)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  previewEmptyState: {
    minHeight: 280,
    display: "grid",
    placeItems: "center",
    color: "var(--muted)",
    fontSize: 13,
  },
  pdfDock: {
    position: "fixed",
    right: 0,
    top: 30,
    transform: "none",
    zIndex: 35,
    border: "1px solid rgba(10, 103, 114, 0.18)",
    background: "rgba(10, 103, 114, 0.94)",
    color: "white",
    minHeight: 0,
    width: "auto",
    height: 42,
    padding: "0 14px",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    boxShadow: "0 14px 32px rgba(10, 103, 114, 0.16)",
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
