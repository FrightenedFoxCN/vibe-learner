"use client";

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation, StudySessionRecord } from "@vibe-learner/shared";

import { useLearningWorkspace } from "./learning-workspace-provider";
import { MaterialIcon } from "./material-icon";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
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
  const headingRef = useRef<HTMLDivElement | null>(null);
  const {
    activePersona,
    activePlan,
    activeDocument,
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
    updatePlanProgress,
    triggerSessionPrelude,
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
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(false);
  const [previewState, setPreviewState] = useState<PreviewState | null>(
    () => studyDialogCache?.previewState ?? null
  );
  const [pendingComposerInsert, setPendingComposerInsert] = useState<{ id: string; text: string } | null>(null);
  const [selectedScheduleId, setSelectedScheduleId] = useState(
    () => studyDialogCache?.selectedScheduleId ?? ""
  );
  const [requestedPlanId, setRequestedPlanId] = useState("");
  const [requestedScheduleId, setRequestedScheduleId] = useState("");
  const [requestedPage, setRequestedPage] = useState(0);
  const [headingHeight, setHeadingHeight] = useState(112);
  const [isHydrated, setIsHydrated] = useState(false);

  const scheduleOptions = activePlan?.schedule ?? [];
  const currentSchedule =
    scheduleOptions.find((item) => item.id === selectedScheduleId) ??
    scheduleOptions[0] ??
    null;
  const currentScheduleId = currentSchedule?.id ?? "";
  const activeSceneProfile = studySession?.sceneProfile ?? activePlan?.sceneProfile ?? null;
  const projectedPdf = studySession?.projectedPdf ?? null;

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

  const navigateToSchedule = useCallback(
    async (scheduleId: string) => {
      setSelectedScheduleId(scheduleId);
      const scheduleItem = scheduleOptions.find((item) => item.id === scheduleId);
      if (!scheduleItem) return;
      const nextPage = scheduleItem.scheduleChapters[0]?.anchorPageStart || resolveScheduleStartPage(scheduleId);
      if (nextPage > 0) {
        handleOpenPdfPage(nextPage);
      }
      if (scheduleItem.unitId && (!studySession || scheduleItem.unitId !== studySession.studyUnitId)) {
        await handleSwitchSection(scheduleItem.unitId);
      }
    },
    [handleOpenPdfPage, handleSwitchSection, resolveScheduleStartPage, scheduleOptions, studySession]
  );

  const handleScheduleChange = useCallback(
    (scheduleId: string) => {
      void navigateToSchedule(scheduleId);
    },
    [navigateToSchedule]
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

  const handleJumpToScheduleStart = useCallback(() => {
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
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    const node = headingRef.current;
    if (!node) {
      return;
    }

    const syncHeight = () => {
      setHeadingHeight(Math.ceil(node.getBoundingClientRect().height));
    };

    syncHeight();
    const observer = new ResizeObserver(syncHeight);
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setRequestedPlanId(params.get("plan") ?? "");
    setRequestedScheduleId(params.get("schedule") ?? "");
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
      return;
    }
    if (!selectedScheduleId || !scheduleOptions.some((item) => item.id === selectedScheduleId)) {
      setSelectedScheduleId(scheduleOptions[0]?.id ?? "");
    }
  }, [activePlan?.id, requestedScheduleId, scheduleOptions, selectedScheduleId]);

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
      selectedScheduleChapterId: "",
    };
    setPageCache("studyDialog", nextCache);
  }, [currentScheduleId, isPdfPreviewOpen, pdfPage, previewState, setPageCache]);

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
  const pageStyle = {
    ...styles.page,
    ["--study-heading-offset" as string]: `${headingHeight}px`,
  } as CSSProperties;

  const jumpToPreviewPage = useCallback(() => {
    if (
      !effectivePreview ||
      effectivePreview.kind === "attachment_image" ||
      effectivePreview.kind === "generated_image"
    ) {
      return;
    }
    const raw = window.prompt("跳转到页码", String(previewPage));
    if (!raw) {
      return;
    }
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return;
    }
    const nextPage = previewPageCount > 0 ? Math.min(parsed, previewPageCount) : parsed;
    setPdfPage(nextPage);
    setPreviewState((current) =>
      current
        ? {
            ...current,
            page: nextPage,
          }
        : current
    );
  }, [effectivePreview, previewPage, previewPageCount]);

  const handleCompleteCurrentSchedule = useCallback(async () => {
    if (!activePlan || !currentScheduleId) {
      return;
    }
    const currentIndex = scheduleOptions.findIndex((item) => item.id === currentScheduleId);
    if (currentIndex < 0) {
      return;
    }
    const nextSchedule = scheduleOptions[currentIndex + 1] ?? null;
    const ok = await updatePlanProgress({
      planId: activePlan.id,
      scheduleIds: [currentScheduleId],
      status: "completed",
    });
    if (!ok || !nextSchedule) {
      return;
    }
    await updatePlanProgress({
      planId: activePlan.id,
      scheduleIds: [nextSchedule.id],
      status: "in_progress",
    });
    await navigateToSchedule(nextSchedule.id);
    await triggerSessionPrelude({
      studyUnitId: nextSchedule.unitId,
      sectionTitle: nextSchedule.scheduleChapters[0]?.title || nextSchedule.title,
      themeHint: nextSchedule.focus || "",
    });
  }, [activePlan, currentScheduleId, navigateToSchedule, scheduleOptions, triggerSessionPrelude, updatePlanProgress]);

  return (
    <main className="with-app-nav study-dialog-page" style={pageStyle}>
      <TopNav currentPath="/study" />

      <div ref={headingRef} style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 style={styles.pageTitle}>章节对话</h1>
          {notice ? <div style={styles.notice}>{notice}</div> : null}
        </div>
      </div>

      <section style={styles.mainStage}>
          <StudyConsole
            isPending={isBusy}
            selectedPlanId={activePlan?.id ?? ""}
            planOptions={planHistoryItems.map((item) => ({
              id: item.id,
              title: `${item.courseTitle} · ${item.documentTitle}`,
            }))}
            onSelectPlan={(planId) => selectPlan(planId, PLAN_SWITCH_NOTICE)}
            onCreateSession={() => { void createSessionForActivePlan(); }}
            showCreateSession={!studySession && Boolean(activePlan)}
            onAsk={handleAskByCurrentChapter}
            onSubmitQuestionAttempt={handleSubmitQuestionAttempt}
            onChangeSchedule={handleScheduleChange}
            onOpenCitation={handleOpenCitation}
            onJumpToScheduleStart={handleJumpToScheduleStart}
            onCompleteCurrentSchedule={() => { void handleCompleteCurrentSchedule(); }}
            canCompleteCurrentSchedule={Boolean(currentScheduleId && currentSchedule?.status !== "completed")}
            chatErrorMessage={chatFailure?.detail ?? ""}
            onRetryLastAsk={retryFailedAsk}
            selectedScheduleId={currentScheduleId}
            scheduleOptions={scheduleOptions.map((item) => ({ id: item.id, title: item.title }))}
            turns={studySession?.turns ?? []}
            session={response}
            persona={activePersona}
            sceneProfile={activeSceneProfile}
            pendingFollowUps={studySession?.pendingFollowUps ?? []}
            isDialogueInterrupted={isDialogueInterrupted}
            onInterruptDialogue={() => { void interruptDialogue(); }}
            affinityState={studySession?.affinityState}
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

      {isHydrated ? (
        effectivePreview ? (
          isPdfPreviewOpen ? (
            <aside className="study-dialog-pdf-window" style={styles.pdfWindow}>
              <div style={styles.pdfHeader}>
                <div style={styles.pdfHeaderTop}>
                  <div style={styles.pdfHeaderMeta}>
                    <span style={styles.pdfTitle}>{previewTitle}</span>
                  </div>
                  <div style={styles.pdfHeaderActions}>
                    {previewFileHref ? (
                      <a
                        href={previewFileHref}
                        target="_blank"
                        rel="noreferrer"
                        style={styles.pdfIconLink}
                        title="下载原件"
                        aria-label="下载原件"
                      >
                        <MaterialIcon name="download" size={15} />
                      </a>
                    ) : null}
                    <button
                      type="button"
                      style={{
                        ...styles.pdfIconBtn,
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
                      title="上一页"
                      aria-label="上一页"
                    >
                      <MaterialIcon name="chevron_left" size={16} />
                    </button>
                    <button
                      type="button"
                      style={{
                        ...styles.pdfIconBtn,
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
                      title="下一页"
                      aria-label="下一页"
                    >
                      <MaterialIcon name="chevron_right" size={16} />
                    </button>
                    <button
                      type="button"
                      style={styles.pdfIconBtn}
                      onClick={() => setIsPdfPreviewOpen(false)}
                      title="收拢"
                      aria-label="收拢"
                    >
                      <MaterialIcon name="close" size={15} />
                    </button>
                  </div>
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
                        onPageRequest={(delta) => {
                          if (!effectivePreview) return;
                          const nextPage = previewPage + delta;
                          if (nextPage < 1) return;
                          if (previewPageCount > 0 && nextPage > previewPageCount) return;
                          setPdfPage(nextPage);
                          setPreviewState((current) =>
                            current
                              ? {
                                  ...current,
                                  page: nextPage,
                                }
                              : current
                          );
                        }}
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
                    <div style={styles.previewMetaFloat}>
                      <span style={styles.previewMetaChip}>
                        {effectivePreview.kind === "attachment_pdf"
                          ? "会话材料"
                          : effectivePreview.kind === "attachment_image"
                            ? "会话图片"
                            : effectivePreview.kind === "generated_image"
                              ? "AI 图像"
                              : "教材材料"}
                      </span>
                      {effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image" ? (
                        <span style={styles.previewMetaChip}>图像</span>
                      ) : (
                        <button
                          type="button"
                          style={{ ...styles.previewMetaChip, ...styles.previewMetaChipButton }}
                          onClick={jumpToPreviewPage}
                          title="输入页码跳转"
                          aria-label="输入页码跳转"
                        >
                          {`${previewPage}${previewPageCount > 0 ? ` / ${previewPageCount}` : ""}`}
                        </button>
                      )}
                    </div>
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
              aria-label="打开材料预览"
              title="打开材料预览"
            >
              <MaterialIcon name="menu_book" size={16} />
              {(effectivePreview.kind === "attachment_image" || effectivePreview.kind === "generated_image") ? "图像" : `p.${previewPage}`}
            </button>
          )
        ) : (
          <div style={styles.emptyDock}>
            {activePlan
              ? "当前计划未关联教材，可直接围绕章节目标展开对话。"
              : "请先在计划页完成教材上传或目标计划生成。"}
          </div>
        )
      ) : null}
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
    width: "100%",
    maxWidth: "none",
    padding: "0 28px 48px",
    display: "grid",
    gap: 0,
    alignContent: "start",
  },
  heading: {
    display: "grid",
    gap: 8,
    position: "sticky",
    top: 0,
    zIndex: 15,
    width: "100%",
    paddingTop: 20,
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 92%, var(--bg))",
  },
  headingRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  notice: {
    width: "fit-content",
    maxWidth: "100%",
    minHeight: 24,
    padding: "0 8px",
    border: "none",
    background: "color-mix(in srgb, white 72%, var(--accent-soft))",
    color: "var(--ink-2)",
    fontSize: 12,
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center",
  },
  mainStage: {
    minWidth: 0,
    width: "100%",
    maxWidth: "none",
  },
  pdfWindow: {
    position: "fixed",
    top: "calc(var(--study-heading-offset, 112px) - 6px)",
    right: 0,
    bottom: "auto",
    zIndex: 35,
    display: "flex",
    flexDirection: "column",
    width: "min(400px, calc(100vw - 36px))",
    height: "min(82vh, calc(100vh - var(--study-heading-offset, 112px) - 20px))",
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.98)",
    boxShadow: "0 16px 40px rgba(13, 32, 40, 0.12)",
    overflow: "hidden",
  },
  pdfHeader: {
    display: "grid",
    gap: 6,
    padding: "9px 10px",
    borderBottom: "1px solid var(--border)",
    background: "var(--panel)",
  },
  pdfHeaderTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
  },
  pdfHeaderMeta: {
    display: "grid",
    gap: 0,
    minWidth: 0,
    flex: 1,
  },
  pdfHeaderActions: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexWrap: "nowrap",
    justifyContent: "flex-end",
    flexShrink: 0,
  },
  pdfTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  pdfIconBtn: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    width: 30,
    height: 30,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
  },
  pdfIconLink: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    width: 30,
    height: 30,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  pdfNavBtnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  previewStage: {
    width: "100%",
    flex: 1,
    minHeight: 0,
    background: "var(--panel)",
    overflow: "hidden",
    padding: 8,
  },
  previewCanvas: {
    position: "relative",
    width: "100%",
    height: "100%",
    background: "white",
    border: "1px solid rgba(15, 23, 42, 0.08)",
    overflow: "hidden",
  },
  previewMetaFloat: {
    position: "absolute",
    right: 10,
    bottom: 10,
    zIndex: 9,
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    justifyContent: "flex-end",
    pointerEvents: "none",
  },
  previewMetaChip: {
    display: "inline-flex",
    alignItems: "center",
    minHeight: 24,
    padding: "0 8px",
    background: "rgba(255, 255, 255, 0.92)",
    border: "1px solid rgba(148, 163, 184, 0.24)",
    boxShadow: "0 10px 24px rgba(15, 23, 42, 0.10)",
    backdropFilter: "blur(10px)",
    color: "var(--ink-2)",
    fontSize: 11,
    fontWeight: 600,
  },
  previewMetaChipButton: {
    cursor: "pointer",
    pointerEvents: "auto",
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
    top: "calc(var(--study-heading-offset, 112px) - 6px)",
    transform: "none",
    zIndex: 35,
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    minHeight: 0,
    width: "auto",
    height: 38,
    padding: "0 14px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    boxShadow: "0 12px 28px rgba(13, 32, 40, 0.10)",
  },
  emptyDock: {
    position: "fixed",
    right: 0,
    top: "calc(var(--study-heading-offset, 112px) + 20px)",
    transform: "none",
    zIndex: 20,
    width: "auto",
    maxWidth: 220,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.96)",
    color: "var(--muted)",
    fontSize: 12,
    lineHeight: 1.6,
  },
};
