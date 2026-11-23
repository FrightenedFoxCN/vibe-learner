"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLearningWorkspace } from "../layout/learning-workspace-provider";
import { ProviderTruth } from "../ui/provider-truth";
import { StudyConsole } from "./study-console";
import { TopNav } from "../layout/top-nav";
import { PLAN_SWITCH_NOTICE } from "../../lib/learning-workspace-copy";
import {
  advanceStudySchedule,
  type StudyScheduleAdvance,
} from "../../lib/study-schedule-advance";
import { AppLink } from "../../lib/app-navigation";
import type {
  StudyConsolePageCache,
  StudyDialogPageCache,
} from "../../lib/learning-workspace-page-cache";
import { useStudyPreview } from "./use-study-preview";
import { StudyPreviewPanel } from "./study-preview-panel";
import "./study-dialog.css";

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
    chatFailure,
    queryStudyChatOperation,
    retryFailedAsk,
    refreshStudySessionAfterRejectedAdmission,
    handleSwitchSection,
    handleSubmitQuestionAttempt,
    continueAfterInteractiveQuestion,
    handleResolvePlanConfirmation,
    interruptDialogue,
    getPageCache,
    setPageCache,
  } = useLearningWorkspace();
  const studyDialogCache = getPageCache("studyDialog");
  const studyConsoleCache = getPageCache("studyConsole");

  const [selectedScheduleId, setSelectedScheduleId] = useState(
    () => studyDialogCache?.selectedScheduleId ?? "",
  );
  const [requestedPlanId, setRequestedPlanId] = useState("");
  const [requestedScheduleId, setRequestedScheduleId] = useState("");
  const [requestedPage, setRequestedPage] = useState(0);
  const [headingHeight, setHeadingHeight] = useState(112);
  const [isHydrated, setIsHydrated] = useState(false);
  const handleSwitchSectionRef = useRef(handleSwitchSection);
  handleSwitchSectionRef.current = handleSwitchSection;

  const preview = useStudyPreview({
    activeDocument,
    studySession,
    studyDialogCache,
    requestedPage,
  });
  const {
    pdfPage,
    isPdfPreviewOpen,
    previewState,
    handleOpenPdfPage,
    handleOpenCitation,
  } = preview;
  const scheduleOptions = useMemo(
    () => activePlan?.schedule ?? [],
    [activePlan?.schedule],
  );
  const currentSchedule =
    scheduleOptions.find((item) => item.id === selectedScheduleId) ??
    scheduleOptions[0] ??
    null;
  const currentScheduleId = currentSchedule?.id ?? "";
  const activeSceneProfile =
    studySession?.sceneProfile ?? activePlan?.sceneProfile ?? null;
  const resolveScheduleStartPage = useCallback(
    (scheduleId: string) => {
      if (!scheduleId) return 0;
      const scheduleItem = activePlan?.schedule.find((item) => item.id === scheduleId);
      if (!scheduleItem) return 0;
      const firstScheduleChapter = scheduleItem.scheduleChapters[0];
      if (firstScheduleChapter?.anchorPageStart) {
        return firstScheduleChapter.anchorPageStart;
      }
      const fromPlanSection = planSections.find(
        (section) => section.id === scheduleItem.unitId,
      )?.pageStart;
      if (fromPlanSection) return fromPlanSection;
      const fromStudyUnit = activeDocument?.studyUnits.find(
        (unit) => unit.id === scheduleItem.unitId,
      )?.pageStart;
      if (fromStudyUnit) return fromStudyUnit;
      const fromRawSection = activeDocument?.sections.find(
        (section) => section.id === scheduleItem.unitId,
      )?.pageStart;
      if (fromRawSection) return fromRawSection;
      return 0;
    },
    [
      activeDocument?.sections,
      activeDocument?.studyUnits,
      activePlan?.schedule,
      planSections,
    ],
  );

  const scheduleStartPage = resolveScheduleStartPage(currentScheduleId);
  const currentStudyUnitId = currentSchedule?.unitId ?? "";
  const [partialAdvance, setPartialAdvance] = useState<StudyScheduleAdvance | null>(
    null,
  );
  const scheduleScope = useRef<object | null>(null);
  const visiblePartialAdvance =
    partialAdvance?.planId === activePlan?.id &&
    partialAdvance?.currentId === currentScheduleId &&
    partialAdvance?.nextId ===
      scheduleOptions[
        scheduleOptions.findIndex((item) => item.id === currentScheduleId) + 1
      ]?.id
      ? partialAdvance
      : null;
  useEffect(() => {
    const scope = {};
    scheduleScope.current = scope;
    return () => {
      scheduleScope.current = null;
    };
  }, [activePlan?.id, currentScheduleId]);

  const navigateToSchedule = useCallback(
    async (scheduleId: string) => {
      setSelectedScheduleId(scheduleId);
      const scheduleItem = scheduleOptions.find((item) => item.id === scheduleId);
      if (!scheduleItem) return;
      const nextPage =
        scheduleItem.scheduleChapters[0]?.anchorPageStart ||
        resolveScheduleStartPage(scheduleId);
      if (nextPage > 0) {
        handleOpenPdfPage(nextPage);
      }
      if (
        studySession &&
        scheduleItem.unitId &&
        scheduleItem.unitId !== studySession.studyUnitId
      ) {
        await handleSwitchSection(scheduleItem.unitId);
      }
    },
    [
      handleOpenPdfPage,
      handleSwitchSection,
      resolveScheduleStartPage,
      scheduleOptions,
      studySession,
    ],
  );

  const handleScheduleChange = useCallback(
    (scheduleId: string) => {
      setRequestedScheduleId("");
      void navigateToSchedule(scheduleId);
    },
    [navigateToSchedule],
  );

  const handlePlanSelection = useCallback(
    (planId: string) => {
      // A manual choice supersedes a deep-link request that may still be
      // waiting for the plan history to load.
      setRequestedPlanId("");
      setRequestedScheduleId("");
      selectPlan(planId, PLAN_SWITCH_NOTICE);
    },
    [selectPlan],
  );

  const handleJumpToScheduleStart = useCallback(() => {
    if (scheduleStartPage > 0) {
      handleOpenPdfPage(scheduleStartPage);
    }
  }, [handleOpenPdfPage, scheduleStartPage]);

  const handleAskByCurrentChapter = useCallback(
    async (
      message: string,
      attachments: File[] = [],
      outputLanguage?: string,
      onCommitted?: () => void,
    ) => {
      const targetStudyUnitId = currentStudyUnitId || studySession?.studyUnitId || "";
      if (targetStudyUnitId) {
        return handleAskForSection(
          message,
          targetStudyUnitId,
          attachments,
          outputLanguage,
          onCommitted,
        );
      }
      return handleAsk(message, attachments, outputLanguage, onCommitted);
    },
    [currentStudyUnitId, handleAsk, handleAskForSection, studySession?.studyUnitId],
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
    if (!requestedPlanId) return;
    if (requestedPlanId === activePlan?.id) {
      setRequestedPlanId("");
      return;
    }
    if (!planHistoryItems.some((item) => item.id === requestedPlanId)) return;
    selectPlan(requestedPlanId, PLAN_SWITCH_NOTICE);
    setRequestedPlanId("");
  }, [activePlan?.id, planHistoryItems, requestedPlanId, selectPlan]);

  useEffect(() => {
    if (!scheduleOptions.length) {
      setSelectedScheduleId("");
      return;
    }
    if (
      requestedScheduleId &&
      scheduleOptions.some((item) => item.id === requestedScheduleId) &&
      requestedScheduleId !== selectedScheduleId
    ) {
      setSelectedScheduleId(requestedScheduleId);
      setRequestedScheduleId("");
      return;
    }
    if (
      !selectedScheduleId ||
      !scheduleOptions.some((item) => item.id === selectedScheduleId)
    ) {
      setSelectedScheduleId(scheduleOptions[0]?.id ?? "");
    }
  }, [activePlan?.id, requestedScheduleId, scheduleOptions, selectedScheduleId]);

  useEffect(() => {
    if (!studySession || !currentStudyUnitId) return;
    if (currentStudyUnitId !== studySession.studyUnitId) {
      void handleSwitchSectionRef.current(currentStudyUnitId);
    }
  }, [currentStudyUnitId, studySession]);

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

  const pageStyle = {
    ["--study-heading-offset" as string]: `${headingHeight}px`,
  } as CSSProperties;

  const runScheduleAdvance = async (advance: StudyScheduleAdvance, retry = false) => {
    const scope = scheduleScope.current;
    await advanceStudySchedule(
      advance,
      {
        update: updatePlanProgress,
        isCurrent: () => Boolean(scope && scheduleScope.current === scope),
        navigate: navigateToSchedule,
        onPartial: setPartialAdvance,
      },
      retry,
    );
  };

  const handleCompleteCurrentSchedule = async () => {
    if (!activePlan || !currentScheduleId) return;
    const currentIndex = scheduleOptions.findIndex(
      (item) => item.id === currentScheduleId,
    );
    if (currentIndex < 0) return;
    await runScheduleAdvance({
      planId: activePlan.id,
      currentId: currentScheduleId,
      nextId: scheduleOptions[currentIndex + 1]?.id ?? "",
    });
  };

  return (
    <main className="with-app-nav study-dialog-workspace" style={pageStyle}>
      <TopNav currentPath="/study" />

      <div ref={headingRef} className="study-dialog-heading">
        <div className="study-dialog-heading-row">
          <h1 className="study-dialog-page-title">章节对话</h1>
          <ProviderTruth scope="study" />
          {visiblePartialAdvance ? (
            <div role="status" className="study-dialog-notice">
              <span>本排期项已完成，但尚未确认下一项开始。你仍在当前排期项。</span>
              <button
                type="button"
                className="study-console-ghost-btn study-console-btn-disabled"
                disabled={isBusy}
                onClick={() => void runScheduleAdvance(visiblePartialAdvance, true)}
              >
                重试开始下一项
              </button>
            </div>
          ) : null}
          {notice ? (
            <div
              className="study-dialog-notice"
              role="status"
              aria-live="polite"
              data-study-action-notice
            >
              <span className="study-dialog-notice-label">操作反馈</span>
              <span>{notice}</span>
            </div>
          ) : null}
        </div>
      </div>

      <section className="study-dialog-main-stage">
        {isHydrated && !planHistoryItems.length ? (
          <div className="study-dialog-no-plan-state">
            <div className="study-dialog-no-plan-copy">
              <h2 className="study-dialog-no-plan-title">先创建或选择学习计划</h2>
              <p className="study-dialog-no-plan-description">
                章节对话需要一个学习计划来确定教材、章节和学习进度。
              </p>
            </div>
            <AppLink path="/plan" className="study-dialog-no-plan-action">
              前往计划工作区
            </AppLink>
          </div>
        ) : (
          <StudyConsole
            isPending={isBusy}
            selectedPlanId={activePlan?.id ?? ""}
            planOptions={planHistoryItems.map((item) => ({
              id: item.id,
              title: `${item.courseTitle} · ${item.documentTitle}`,
            }))}
            onSelectPlan={handlePlanSelection}
            onCreateSession={() => {
              void createSessionForActivePlan();
            }}
            showCreateSession={!studySession && Boolean(activePlan)}
            onAsk={handleAskByCurrentChapter}
            outputLanguage={
              studySession?.outputLanguage ??
              (activePlan?.outputLanguage !== "unknown"
                ? activePlan?.outputLanguage
                : "auto") ??
              "auto"
            }
            outputLanguageScope={studySession?.id ?? activePlan?.id ?? ""}
            onSubmitQuestionAttempt={handleSubmitQuestionAttempt}
            onContinueAfterQuestion={continueAfterInteractiveQuestion}
            onChangeSchedule={handleScheduleChange}
            onOpenCitation={handleOpenCitation}
            onJumpToScheduleStart={handleJumpToScheduleStart}
            onCompleteCurrentSchedule={() => {
              void handleCompleteCurrentSchedule();
            }}
            canCompleteCurrentSchedule={Boolean(
              currentScheduleId && currentSchedule?.status !== "completed",
            )}
            chatErrorMessage={chatFailure?.detail ?? ""}
            chatOperationStatus={chatFailure?.operationStatus}
            canQueryLastAsk={Boolean(chatFailure?.canQuery)}
            canResendLastAsk={Boolean(chatFailure?.canResend)}
            canRefreshSessionAfterAsk={Boolean(chatFailure?.canRefreshSession)}
            onQueryLastAsk={queryStudyChatOperation}
            onRetryLastAsk={retryFailedAsk}
            onRefreshSessionAfterAsk={refreshStudySessionAfterRejectedAdmission}
            selectedScheduleId={currentScheduleId}
            scheduleOptions={scheduleOptions.map((item) => ({
              id: item.id,
              title: item.title,
            }))}
            turns={studySession?.turns ?? []}
            session={response}
            persona={activePersona}
            sceneProfile={activeSceneProfile}
            pendingFollowUps={studySession?.pendingFollowUps ?? []}
            isDialogueInterrupted={isDialogueInterrupted}
            onInterruptDialogue={() => {
              void interruptDialogue();
            }}
            affinityState={studySession?.affinityState}
            planConfirmations={studySession?.planConfirmations ?? []}
            onResolvePlanConfirmation={handleResolvePlanConfirmation}
            chatImageUploadEnabled={chatImageUploadEnabled}
            pendingComposerInsert={preview.pendingComposerInsert}
            onConsumeComposerInsert={() => preview.setPendingComposerInsert(null)}
            canJumpToScheduleStart={scheduleStartPage > 0}
            disabled={!studySession}
            cachedState={studyConsoleCache}
            onCachedStateChange={(nextState: StudyConsolePageCache) =>
              setPageCache("studyConsole", nextState)
            }
          />
        )}
      </section>

      {isHydrated ? (
        <StudyPreviewPanel preview={preview} hasPlan={Boolean(activePlan)} />
      ) : null}
    </main>
  );
}
