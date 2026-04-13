"use client";

import type { CSSProperties } from "react";

import { DocumentSetup } from "./document-setup";
import { PlanHistory } from "./plan-history";
import { PlanOverview } from "./plan-overview";
import { TopNav } from "./top-nav";
import { useAppNavigator } from "../lib/app-navigation";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
import type { PlanSetupPageCache } from "../lib/learning-workspace-page-cache";
import { useLearningWorkspace } from "./learning-workspace-provider";

export function LearningWorkspace() {
  const appNavigator = useAppNavigator();
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
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    generatePlanWorkflow,
    cancelPlanGeneration,
    selectPlan,
    renamePlanTitle,
    updatePlanProgress,
    answerPlanQuestion,
    removePlan,
    refreshPlanSnapshot,
    handleSwitchSection,
    getPageCache,
    setPageCache,
  } = useLearningWorkspace();
  const planSetupCache = getPageCache("planSetup");

  const handleStartStudyFromPlan = async (input: {
    studyUnitId: string;
    scheduleId: string;
    scheduleChapterId?: string;
    chapter: string;
    page: number;
    scheduleIds: string[];
  }) => {
    if (!activePlan || !input.studyUnitId) {
      return;
    }
    if (input.scheduleIds.length) {
      await updatePlanProgress({
        planId: activePlan.id,
        scheduleIds: input.scheduleIds,
        status: "in_progress",
      });
    }
    await handleSwitchSection(input.studyUnitId);
    appNavigator.push("/study", {
      plan: activePlan.id,
      schedule: input.scheduleId,
      scheduleChapter: input.scheduleChapterId ?? "",
      chapter: input.chapter,
      page: Math.max(1, input.page),
    });
  };

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/plan" />

      <div style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 style={styles.pageTitle}>计划生成</h1>
          {notice ? <div style={styles.notice}>{notice}</div> : null}
        </div>
      </div>

      <div className="plan-content-grid">
        <DocumentSetup
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onSelectPersonaId={setSelectedPersonaId}
          isBusy={isBusy}
          sceneLibraryItems={sceneLibraryItems}
          selectedSceneLibraryId={selectedSceneLibraryId}
          onSelectSceneLibraryId={setSelectedSceneLibraryId}
          onGenerate={(input) => { void generatePlanWorkflow(input); }}
          onInterruptGeneration={() => { void cancelPlanGeneration(); }}
          planStreamEvents={planStreamEvents}
          planStreamStatus={planStreamStatus}
          canInterruptGeneration={isGeneratingPlan}
          isInterruptingGeneration={isInterruptingPlan}
          generationBlockedReason={planGenerationBlockedReason}
          cachedState={planSetupCache}
          onCachedStateChange={(nextState: PlanSetupPageCache) => setPageCache("planSetup", nextState)}
        />

        <div className="plan-main-column" style={styles.planColumn}>
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
            sceneProfile={activePlan?.sceneProfile ?? studySession?.sceneProfile ?? null}
            isBusy={isBusy}
            onRenamePlan={renamePlanTitle}
            onUpdatePlanProgress={updatePlanProgress}
            onAnswerPlanningQuestion={answerPlanQuestion}
            onStartStudyFromPlan={handleStartStudyFromPlan}
          />

          <PlanHistory
            items={planHistoryItems}
            selectedPlanId={selectedPlanId}
            isRefreshing={isSnapshotRefreshing}
            isBusy={isBusy}
            onSelect={(planId) => selectPlan(planId, PLAN_SWITCH_NOTICE)}
            onRefresh={() => { void refreshPlanSnapshot(); }}
            onDelete={(planId) => { void removePlan(planId); }}
          />
        </div>
      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "28px 32px 56px",
    display: "grid",
    gap: 22,
    alignContent: "start"
  },
  heading: {
    display: "grid",
    gap: 10,
    paddingBottom: 10,
    borderBottom: "1px solid var(--border)"
  },
  headingRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap"
  },
  pageTitle: {
    margin: 0,
    fontSize: "clamp(1.4rem, 2vw, 1.9rem)",
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2
  },
  notice: {
    width: "fit-content",
    maxWidth: "100%",
    minHeight: 28,
    padding: "0 10px",
    border: "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
    background: "color-mix(in srgb, white 84%, var(--accent-soft))",
    color: "var(--teal)",
    fontSize: 12,
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center"
  },
  planColumn: {
    display: "grid",
    gap: 18
  }
};
