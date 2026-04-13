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
    selectedSceneProfile,
    generatePlanWorkflow,
    cancelPlanGeneration,
    selectPlan,
    createSessionForActivePlan,
    renamePlanTitle,
    updatePlanStudyChapters,
    updatePlanProgress,
    answerPlanQuestion,
    renameStudyUnitTitle,
    removePlan,
    refreshPlanSnapshot,
    handleSwitchSection,
    getPageCache,
    setPageCache,
  } = useLearningWorkspace();
  const planSetupCache = getPageCache("planSetup");

  const handleOpenStudyDialog = async () => {
    if (!studySession && activePlan) {
      await createSessionForActivePlan();
    }
    if (studySession || activePlan) {
      appNavigator.push("/study");
    }
  };

  const handleStartStudyFromPlan = async (input: {
    sectionId: string;
    chapter: string;
    page: number;
    scheduleIds: string[];
  }) => {
    if (!activePlan || !input.sectionId) {
      return;
    }
    if (input.scheduleIds.length) {
      await updatePlanProgress({
        planId: activePlan.id,
        scheduleIds: input.scheduleIds,
        status: "in_progress",
      });
    }
    await handleSwitchSection(input.sectionId);
    appNavigator.push("/study", {
      plan: activePlan.id,
      chapter: input.chapter,
      page: Math.max(1, input.page),
    });
  };

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/plan" />

      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>计划生成</h1>
        {notice ? <div style={styles.notice}>{notice}</div> : null}
      </div>

      <div className="plan-content-grid">
        <DocumentSetup
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onSelectPersonaId={setSelectedPersonaId}
          isBusy={isBusy}
          document={activeDocument}
          plan={activePlan}
          session={studySession}
          sceneLibraryItems={sceneLibraryItems}
          selectedSceneLibraryId={selectedSceneLibraryId}
          onSelectSceneLibraryId={setSelectedSceneLibraryId}
          sceneProfile={selectedSceneProfile ?? activePlan?.sceneProfile ?? studySession?.sceneProfile ?? null}
          onGenerate={(input) => { void generatePlanWorkflow(input); }}
          onInterruptGeneration={() => { void cancelPlanGeneration(); }}
          onOpenStudyDialog={() => { void handleOpenStudyDialog(); }}
          canOpenStudyDialog={Boolean(studySession || activePlan)}
          hasStudySession={Boolean(studySession)}
          onRenameStudyUnitTitle={renameStudyUnitTitle}
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
            hasSession={Boolean(studySession)}
            isBusy={isBusy}
            onCreateSession={() => { void createSessionForActivePlan(); }}
            onRenamePlan={renamePlanTitle}
            onUpdateStudyChapters={updatePlanStudyChapters}
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
    padding: "28px 32px 48px",
    display: "grid",
    gap: 24,
    alignContent: "start"
  },
  heading: {
    display: "grid",
    gap: 8
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2
  },
  pageDesc: {
    margin: 0,
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  notice: {
    width: "fit-content",
    maxWidth: "100%",
    padding: "8px 12px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--teal)",
    fontSize: 12,
    lineHeight: 1.5
  },
  planColumn: {
    display: "grid",
    gap: 24
  }
};
