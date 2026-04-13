"use client";

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import type { Citation, LearningPlan, StudySessionRecord } from "@vibe-learner/shared";

import { useLearningWorkspace } from "./learning-workspace-provider";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
import { AppLink } from "../lib/app-navigation";
import { getAiBaseUrl } from "../lib/runtime-config";
import type {
  StudyConsolePageCache,
  StudyDialogPageCache,
  StudyDialogPreviewState,
} from "../lib/learning-workspace-page-cache";

const AI_BASE_URL = () => getAiBaseUrl();
const ProjectedPdfViewer = dynamic(
  () => import("./projected-pdf-viewer").then((module) => module.ProjectedPdfViewer),
  { ssr: false }
);
const ProjectedImageViewer = dynamic(
  () => import("./projected-image-viewer").then((module) => module.ProjectedImageViewer),
  { ssr: false }
);

type PreviewState = StudyDialogPreviewState;

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
    isDialogueInterrupted,
    chatImageUploadEnabled,
    createSessionForActivePlan,
    handleAsk,
    handleAskForSection,
    chatFailure,
    retryFailedAsk,
    handleSwitchSection,
    handleSubmitQuestionAttempt,
    handleResolvePlanConfirmation,
    interruptDialogue,
    getPageCache,
    setPageCache,
  } = useLearningWorkspace();
  const studyDialogCache = getPageCache("studyDialog");
  const studyConsoleCache = getPageCache("studyConsole");

  const [pdfPage, setPdfPage] = useState(() => studyDialogCache?.pdfPage ?? 1);
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(
    () => studyDialogCache?.isPdfPreviewOpen ?? false
  );
  const [previewState, setPreviewState] = useState<PreviewState | null>(
    () => studyDialogCache?.previewState ?? null
  );
  const [pendingComposerInsert, setPendingComposerInsert] = useState<{ id: string; text: string } | null>(null);
  const [selectedScheduleId, setSelectedScheduleId] = useState(
    () => studyDialogCache?.selectedScheduleId ?? ""
  );
  const [selectedScheduleChapterId, setSelectedScheduleChapterId] = useState(
    () => studyDialogCache?.selectedScheduleChapterId ?? ""
  );
  const [requestedPlanId, setRequestedPlanId] = useState("");
  const [requestedScheduleId, setRequestedScheduleId] = useState("");
  const [requestedScheduleChapterId, setRequestedScheduleChapterId] = useState("");
  const [requestedPage, setRequestedPage] = useState(0);

  const scheduleOptions = activePlan?.schedule ?? [];
  const currentSchedule =
    scheduleOptions.find((item) => item.id === selectedScheduleId) ??
    scheduleOptions[0] ??
    null;
  const currentScheduleId = currentSchedule?.id ?? "";
  const activeSceneProfile = studySession?.sceneProfile ?? activePlan?.sceneProfile ?? null;
  const projectedPdf = studySession?.projectedPdf ?? null;
  const scheduleChapterOptions = currentSchedule?.scheduleChapters ?? [];

  const resolveScheduleStartPage = useCallback(
    (scheduleId: string) => {
      if (!scheduleId) return 0;
      const scheduleItem = activePlan?.schedule.find((item) => item.id === scheduleId);
      if (!scheduleItem) return 0;
      const firstScheduleChapter = scheduleItem.scheduleChapters[0];
      if (firstScheduleChapter?.anchorPageStart) {
        return firstScheduleChapter.anchorPageStart;
      }
      const fromPlanSection = planSections.find((section) => section.id === scheduleItem.unitId)?.pageStart;
      if (fromPlanSection) return fromPlanSection;
      const fromStudyUnit = activeDocument?.studyUnits.find((unit) => unit.id === scheduleItem.unitId)?.pageStart;
      if (fromStudyUnit) return fromStudyUnit;
      const fromRawSection = activeDocument?.sections.find((section) => section.id === scheduleItem.unitId)?.pageStart;
      if (fromRawSection) return fromRawSection;
      return 0;
    },
    [activeDocument?.sections, activeDocument?.studyUnits, activePlan?.schedule, planSections]
  );

  const scheduleStartPage = resolveScheduleStartPage(currentScheduleId);
  const currentStudyUnitId = currentSchedule?.unitId ?? "";

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

  const handleScheduleChange = useCallback(
    (scheduleId: string) => {
      setSelectedScheduleId(scheduleId);
      setSelectedScheduleChapterId("");
      const scheduleItem = scheduleOptions.find((item) => item.id === scheduleId);
      if (!scheduleItem) return;
      const nextPage = scheduleItem.scheduleChapters[0]?.anchorPageStart || resolveScheduleStartPage(scheduleId);
      if (nextPage > 0) {
        handleOpenPdfPage(nextPage);
      }
      if (studySession && scheduleItem.unitId && scheduleItem.unitId !== studySession.studyUnitId) {
        void handleSwitchSection(scheduleItem.unitId);
      }
    },
    [handleOpenPdfPage, handleSwitchSection, resolveScheduleStartPage, scheduleOptions, studySession]
  );

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

  const handleScheduleChapterChange = useCallback(
    (scheduleChapterId: string) => {
      setSelectedScheduleChapterId(scheduleChapterId);

      if (!scheduleChapterId) {
        if (scheduleStartPage > 0) {
          handleOpenPdfPage(scheduleStartPage);
        }
        return;
      }

      const targetScheduleChapter = scheduleChapterOptions.find((item) => item.id === scheduleChapterId);
      if (targetScheduleChapter?.anchorPageStart) {
        handleOpenPdfPage(targetScheduleChapter.anchorPageStart);
      }
    },
    [handleOpenPdfPage, scheduleChapterOptions, scheduleStartPage]
  );

  const handleJumpToScheduleStart = useCallback(() => {
    setSelectedScheduleChapterId("");
    if (scheduleStartPage > 0) {
      handleOpenPdfPage(scheduleStartPage);
    }
  }, [handleOpenPdfPage, scheduleStartPage]);

  const handleAskByCurrentChapter = useCallback(
    async (message: string, attachments: File[] = []) => {
      const targetStudyUnitId = currentStudyUnitId || studySession?.studyUnitId || "";
      if (targetStudyUnitId) {
        await handleAskForSection(message, targetStudyUnitId, attachments);
        return;
      }
      await handleAsk(message, attachments);
    },
    [currentStudyUnitId, handleAsk, handleAskForSection, studySession?.studyUnitId]
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setRequestedPlanId(params.get("plan") ?? "");
    setRequestedScheduleId(params.get("schedule") ?? "");
    setRequestedScheduleChapterId(params.get("scheduleChapter") ?? "");
    setRequestedPage(Number(params.get("page") ?? "0"));
  }, []);

  useEffect(() => {
    if (!requestedPlanId || requestedPlanId === activePlan?.id) return;
    selectPlan(requestedPlanId, PLAN_SWITCH_NOTICE);
  }, [activePlan?.id, requestedPlanId, selectPlan]);

  useEffect(() => {
    if (!scheduleOptions.length) { setSelectedScheduleId(""); return; }
    if (
      requestedScheduleId &&
      scheduleOptions.some((item) => item.id === requestedScheduleId) &&
      requestedScheduleId !== selectedScheduleId
    ) {
      setSelectedScheduleId(requestedScheduleId);
      setSelectedScheduleChapterId("");
      return;
    }
    if (!selectedScheduleId || !scheduleOptions.some((item) => item.id === selectedScheduleId)) {
      setSelectedScheduleId(scheduleOptions[0]?.id ?? "");
      setSelectedScheduleChapterId("");
    }
  }, [activePlan?.id, requestedScheduleId, scheduleOptions, selectedScheduleId]);

  useEffect(() => {
    if (!selectedScheduleChapterId) return;
    if (scheduleChapterOptions.some((item) => item.id === selectedScheduleChapterId)) {
      return;
    }
    setSelectedScheduleChapterId("");
  }, [scheduleChapterOptions, selectedScheduleChapterId]);

  useEffect(() => {
    if (!requestedScheduleChapterId || !scheduleChapterOptions.length) return;
    if (!scheduleChapterOptions.some((item) => item.id === requestedScheduleChapterId)) return;
    setSelectedScheduleChapterId((current) => current || requestedScheduleChapterId);
  }, [requestedScheduleChapterId, scheduleChapterOptions]);

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
    if (projectedPdf.sourceKind === "attachment_pdf") {
      setPreviewState({
        kind: "attachment_pdf",
        sourceId: projectedPdf.sourceId,
        title: projectedPdf.title,
        page: projectedPdf.pageNumber,
        pageCount: projectedPdf.pageCount,
      });
    } else if (projectedPdf.sourceKind === "attachment_image") {
      setPreviewState({
        kind: "attachment_image",
        sourceId: projectedPdf.sourceId,
        title: projectedPdf.title,
        page: projectedPdf.pageNumber,
        pageCount: projectedPdf.pageCount,
        imageUrl: projectedPdf.imageUrl || "",
      });
    } else if (projectedPdf.sourceKind === "generated_image") {
      setPreviewState({
        kind: "generated_image",
        sourceId: projectedPdf.sourceId,
        title: projectedPdf.title,
        page: projectedPdf.pageNumber,
        pageCount: projectedPdf.pageCount,
        imageUrl: projectedPdf.imageUrl || "",
      });
    } else {
      setPreviewState({
        kind: "document",
        sourceId: projectedPdf.sourceId,
        title: projectedPdf.title,
        page: projectedPdf.pageNumber,
        pageCount: projectedPdf.pageCount,
      });
    }
    setIsPdfPreviewOpen(true);
  }, [
    projectedPdf?.imageUrl,
    projectedPdf?.pageNumber,
    projectedPdf?.pageCount,
    projectedPdf?.sourceId,
    projectedPdf?.sourceKind,
    projectedPdf?.title,
    projectedPdf?.updatedAt,
  ]);

  useEffect(() => {
    if (!studySession || !currentStudyUnitId) return;
    if (currentStudyUnitId !== studySession.studyUnitId) {
      void handleSwitchSection(currentStudyUnitId);
    }
  }, [
    currentStudyUnitId,
    handleSwitchSection,
    studySession?.id,
    studySession?.studyUnitId,
  ]);

  useEffect(() => {
    const nextCache: StudyDialogPageCache = {
      pdfPage,
      isPdfPreviewOpen,
      previewState,
      selectedScheduleId: currentScheduleId,
      selectedScheduleChapterId,
    };
    setPageCache("studyDialog", nextCache);
  }, [currentScheduleId, isPdfPreviewOpen, pdfPage, previewState, selectedScheduleChapterId, setPageCache]);

  const effectivePreview = previewState;
  const previewPage = effectivePreview?.page ?? pdfPage;
  const previewTitle = effectivePreview?.title ?? activeDocument?.title ?? "";
  const previewFileHref =
    effectivePreview?.kind === "document"
      ? `${AI_BASE_URL()}/documents/${effectivePreview.sourceId}/file`
      : effectivePreview?.kind === "generated_image"
        ? effectivePreview.imageUrl
      : (effectivePreview?.kind === "attachment_pdf" || effectivePreview?.kind === "attachment_image") && studySession?.id
        ? `${AI_BASE_URL()}/study-sessions/${studySession.id}/attachments/${effectivePreview.sourceId}/file`
        : "";
  const previewPageCount = effectivePreview?.pageCount ?? activeDocument?.pageCount ?? 0;
  const previewFileUrl =
    effectivePreview?.kind === "document"
      ? `${AI_BASE_URL()}/documents/${effectivePreview.sourceId}/file`
      : effectivePreview?.kind === "generated_image"
        ? effectivePreview.imageUrl
      : (effectivePreview?.kind === "attachment_pdf" || effectivePreview?.kind === "attachment_image") && studySession?.id
        ? `${AI_BASE_URL()}/study-sessions/${studySession.id}/attachments/${effectivePreview.sourceId}/file`
        : "";
  const previewOverlays =
    (
      effectivePreview?.kind === "attachment_pdf" ||
      effectivePreview?.kind === "attachment_image" ||
      effectivePreview?.kind === "generated_image"
    ) &&
    projectedPdf?.sourceId === effectivePreview.sourceId
      ? projectedPdf.overlays.filter((item) => item.pageNumber === previewPage)
      : [];

  return (
    <main className="with-app-nav study-dialog-page" style={styles.page}>
      <TopNav currentPath="/study" />

      {/* ── Heading ── */}
      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>章节对话</h1>
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

        <AppLink path="/plan" style={styles.toolbarLink}>返回计划生成</AppLink>
        {notice ? <span style={styles.notice}>{notice}</span> : null}
      </div>

      <section style={styles.mainStage}>
          <StudyConsole
            isPending={isBusy}
            onAsk={handleAskByCurrentChapter}
            onSubmitQuestionAttempt={handleSubmitQuestionAttempt}
            onChangeSchedule={handleScheduleChange}
            onOpenCitation={handleOpenCitation}
            onJumpToScheduleStart={handleJumpToScheduleStart}
            chatErrorMessage={chatFailure?.detail ?? ""}
            onRetryLastAsk={retryFailedAsk}
            selectedScheduleId={currentScheduleId}
            scheduleOptions={scheduleOptions.map((item) => ({ id: item.id, title: item.title }))}
            selectedScheduleChapterId={selectedScheduleChapterId}
            scheduleChapterOptions={scheduleChapterOptions}
            onChangeScheduleChapter={handleScheduleChapterChange}
            turns={studySession?.turns ?? []}
            session={response}
            persona={selectedPersona}
            sceneProfile={activeSceneProfile}
            pendingFollowUps={studySession?.pendingFollowUps ?? []}
            isDialogueInterrupted={isDialogueInterrupted}
            onInterruptDialogue={() => { void interruptDialogue(); }}
            affinityState={studySession?.affinityState}
            projectedPdf={studySession?.projectedPdf ?? null}
            planConfirmations={studySession?.planConfirmations ?? []}
            onResolvePlanConfirmation={handleResolvePlanConfirmation}
            chatImageUploadEnabled={chatImageUploadEnabled}
            pendingComposerInsert={pendingComposerInsert}
            onConsumeComposerInsert={() => setPendingComposerInsert(null)}
            canJumpToScheduleStart={scheduleStartPage > 0}
            disabled={!studySession}
            cachedState={studyConsoleCache}
            onCachedStateChange={(nextState: StudyConsolePageCache) => setPageCache("studyConsole", nextState)}
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
                      : effectivePreview.kind === "generated_image"
                        ? "AI 生成图像"
                      : "教材材料"}
                  {effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image"
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
                    if (effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image") return;
                    const nextPage = previewPage - 1;
                    setPdfPage(nextPage);
                    setPreviewState({ ...effectivePreview, page: nextPage });
                  }}
                  disabled={
                    previewPage <= 1 ||
                    effectivePreview.kind === "attachment_image" ||
                    effectivePreview.kind === "generated_image"
                  }
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
                    if (effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image") return;
                    if (previewPageCount > 0 && previewPage >= previewPageCount) return;
                    const nextPage = previewPage + 1;
                    setPdfPage(nextPage);
                    setPreviewState({ ...effectivePreview, page: nextPage });
                  }}
                  disabled={
                    effectivePreview.kind === "attachment_image" ||
                    effectivePreview.kind === "generated_image" ||
                    (previewPageCount > 0 && previewPage >= previewPageCount)
                  }
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
                  {effectivePreview?.kind === "generated_image" ? (
                    <ProjectedImageViewer
                      fileUrl={previewFileUrl}
                      title={previewTitle}
                      overlays={previewOverlays}
                      onInsertReference={(text) => {
                        setPendingComposerInsert({
                          id: `${Date.now()}:generated-image:${text.slice(0, 24)}`,
                          text,
                        });
                      }}
                    />
                  ) : effectivePreview?.kind === "attachment_image" ? (
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
            材料预览 · {(effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image") ? "图像" : `p.${previewPage}`}
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
