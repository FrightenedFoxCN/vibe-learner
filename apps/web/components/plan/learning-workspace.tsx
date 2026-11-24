"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import styles from "./learning-workspace.module.css";

import { DocumentCheckpointPanel } from "./document-checkpoint-panel";
import { DocumentSetup } from "./document-setup";
import { PlanHistory } from "./plan-history";
import { PlanOverview } from "./plan-overview";
import { PlanPageScope } from "./plan-page-scope";
import { PlanRevisionPanel } from "./plan-revision-panel";
import { StudyUnitRevisionPanel } from "./study-unit-revision-panel";
import { ProviderTruth } from "../ui/provider-truth";
import { TopNav } from "../layout/top-nav";
import { useAppNavigator } from "../../lib/app-navigation";
import { studyEntryProgressIds } from "../../lib/study-schedule-advance";
import { PLAN_SWITCH_NOTICE } from "../../lib/learning-workspace-copy";
import type { PlanSetupPageCache } from "../../lib/learning-workspace-page-cache";
import { useLearningWorkspace } from "../layout/learning-workspace-provider";

export function LearningWorkspace() {
  const appNavigator = useAppNavigator();
  const headingRef = useRef<HTMLDivElement | null>(null);
  const [planHeadingHeight, setPlanHeadingHeight] = useState(72);
  const {
    personas,
    selectedPersona,
    setSelectedPersonaId,
    selectedPlanId,
    activePlan,
    activeDocument,
    planHistory,
    planHistoryItems,
    studySession,
    notice,
    isBusy,
    isGeneratingPlan,
    isInterruptingPlan,
    planGenerationBlockedReason,
    isSnapshotRefreshing,
    planStreamEvents,
    planStreamStatus,
    processStreamEvents,
    processStreamStatus,
    processStreamDocumentId,
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    generatePlanWorkflow,
    cancelPlanGeneration,
    checkPendingPlan,
    discardMissingPlan,
    hasPendingPlan,
    isCheckingPlan,
    missingPendingPlan,
    selectPlan,
    renamePlanTitle,
    updatePlanProgress,
    answerPlanQuestion,
    removePlan,
    refreshPlanSnapshot,
    revisionReadbackPending,
    triggerSessionPrelude,
    getPageCache,
    setPageCache,
  } = useLearningWorkspace();
  const planSetupCache = getPageCache("planSetup");

  useEffect(() => {
    const node = headingRef.current;
    if (!node) {
      return;
    }

    const syncHeight = () => {
      setPlanHeadingHeight(Math.ceil(node.getBoundingClientRect().height));
    };

    syncHeight();
    const observer = new ResizeObserver(syncHeight);
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  const entryScope = useRef<object | null>(null);
  useEffect(() => {
    entryScope.current = {};
    return () => {
      entryScope.current = null;
    };
  }, [activePlan?.id]);

  const handleStartStudyFromPlan = async (input: {
    studyUnitId: string;
    scheduleId: string;
    scheduleChapterId?: string;
    chapter: string;
    page: number;
    scheduleIds: string[];
  }) => {
    if (!activePlan || !input.studyUnitId || revisionReadbackPending) {
      return;
    }
    const scope = entryScope.current;
    const item = activePlan.schedule.find((entry) => entry.id === input.scheduleId);
    if (!scope || !item || item.unitId !== input.studyUnitId) return;
    const scheduleIds = studyEntryProgressIds(activePlan.schedule, input.scheduleIds);
    if (
      scheduleIds.length &&
      !(await updatePlanProgress({
        planId: activePlan.id,
        scheduleIds,
        status: "in_progress",
        expectedRevision: activePlan.revision,
      }))
    )
      return;
    if (entryScope.current !== scope) return;
    const prepared = await triggerSessionPrelude({
      studyUnitId: input.studyUnitId,
      sectionTitle: input.chapter,
      themeHint: item.focus,
    });
    if (!prepared || entryScope.current !== scope) return;
    appNavigator.push("/study", {
      plan: activePlan.id,
      schedule: input.scheduleId,
      scheduleChapter: input.scheduleChapterId ?? "",
      chapter: input.chapter,
      page: Math.max(1, input.page),
    });
  };
  const pageStyle = {
    "--plan-heading-offset": `${planHeadingHeight}px`,
  } as CSSProperties;

  return (
    <main className={`with-app-nav ${styles.page}`} style={pageStyle}>
      <TopNav currentPath="/plan" />

      <div ref={headingRef} className={styles.heading}>
        <div className={styles.headingRow}>
          <h1 className={styles.pageTitle}>计划生成</h1>
          <ProviderTruth scope="plan" />
          {notice ? <div className={styles.notice}>{notice}</div> : null}
        </div>
      </div>

      <div className={styles.contentGrid}>
        <div className={styles.planSetupShell}>
          <DocumentSetup
            personas={personas}
            selectedPersonaId={selectedPersona.id}
            onSelectPersonaId={setSelectedPersonaId}
            isBusy={isBusy}
            sceneLibraryItems={sceneLibraryItems}
            selectedSceneLibraryId={selectedSceneLibraryId}
            onSelectSceneLibraryId={setSelectedSceneLibraryId}
            onGenerate={(input) => {
              void generatePlanWorkflow(input);
            }}
            onInterruptGeneration={() => {
              void cancelPlanGeneration();
            }}
            planStreamEvents={planStreamEvents}
            planStreamStatus={planStreamStatus}
            processStreamEvents={processStreamEvents}
            processStreamStatus={processStreamStatus}
            onCheckPendingPlan={() => void checkPendingPlan()}
            onDiscardMissingPlan={discardMissingPlan}
            hasPendingPlan={hasPendingPlan}
            isCheckingPlan={isCheckingPlan}
            missingPendingPlan={missingPendingPlan}
            canInterruptGeneration={isGeneratingPlan}
            isInterruptingGeneration={isInterruptingPlan}
            generationBlockedReason={planGenerationBlockedReason}
            cachedState={planSetupCache}
            onCachedStateChange={(nextState: PlanSetupPageCache) =>
              setPageCache("planSetup", nextState)
            }
          />
        </div>

        <div className={styles.planColumn}>
          <DocumentCheckpointPanel
            documentId={processStreamDocumentId}
            status={processStreamStatus}
            blocked={isBusy || hasPendingPlan}
            onContinue={(document) =>
              void generatePlanWorkflow({
                mode: "document",
                processedDocument: document,
                objective: planSetupCache?.objective ?? "请基于教材生成学习计划",
                physicalPageRanges: planSetupCache?.physicalPageRanges,
                outputLanguage: planSetupCache?.outputLanguage,
              })
            }
          />
          {revisionReadbackPending && (
            <div className={styles.notice} role="status" aria-live="polite">
              <p>修订已提交，当前页面尚未读到新版本。请先重试读回再继续编辑。</p>
              <button
                type="button"
                disabled={isSnapshotRefreshing}
                onClick={() => void refreshPlanSnapshot()}
              >
                {isSnapshotRefreshing ? "正在读取新版本…" : "重试读取新版本"}
              </button>
            </div>
          )}
          <PlanOverview
            plan={activePlan}
            document={activeDocument}
            documentTitle={activeDocument?.title ?? "未关联教材"}
            personaName={
              personas.find((p) => p.id === activePlan?.personaId)?.name ??
              activePlan?.personaId ??
              "未关联人格"
            }
            planPositionLabel={activePlan ? `共 ${planHistory.length} 条` : ""}
            sceneProfile={
              activePlan?.sceneProfile ?? studySession?.sceneProfile ?? null
            }
            isBusy={isBusy || revisionReadbackPending}
            onRenamePlan={renamePlanTitle}
            onUpdatePlanProgress={updatePlanProgress}
            onAnswerPlanningQuestion={answerPlanQuestion}
            onStartStudyFromPlan={handleStartStudyFromPlan}
          />

          {activePlan && (
            <PlanPageScope key={`pages:${activePlan.id}`} plan={activePlan} />
          )}
          {activePlan && (
            <PlanRevisionPanel
              key={activePlan.id}
              plan={activePlan}
              onRefresh={refreshPlanSnapshot}
              readbackPending={revisionReadbackPending}
            />
          )}
          {activePlan && (
            <StudyUnitRevisionPanel
              key={`units:${activePlan.id}`}
              plan={activePlan}
              document={activeDocument}
              onRefresh={refreshPlanSnapshot}
              readbackPending={revisionReadbackPending}
            />
          )}
          <PlanHistory
            items={planHistoryItems}
            selectedPlanId={selectedPlanId}
            isRefreshing={isSnapshotRefreshing}
            isBusy={isBusy}
            onSelect={(planId) => selectPlan(planId, PLAN_SWITCH_NOTICE)}
            onRefresh={() => {
              void refreshPlanSnapshot();
            }}
            onDelete={removePlan}
          />
        </div>
      </div>
    </main>
  );
}
