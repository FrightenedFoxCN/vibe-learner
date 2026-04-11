"use client";

import { useRouter } from "next/navigation";
import type { CSSProperties } from "react";

import { DocumentSetup } from "./document-setup";
import { PlanHistory } from "./plan-history";
import { PlanOverview } from "./plan-overview";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
import { useLearningWorkspace } from "./learning-workspace-provider";

export function LearningWorkspace() {
  const router = useRouter();
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
    isSnapshotRefreshing,
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    selectedSceneProfile,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    renamePlanTitle,
    updatePlanStudyChapters,
    renameStudyUnitTitle,
    removePlan,
    refreshPlanSnapshot
  } = useLearningWorkspace();

  const handleOpenStudyDialog = async () => {
    if (!studySession && activePlan) {
      await createSessionForActivePlan();
    }
    if (studySession || activePlan) {
      router.push("/study");
    }
  };

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/plan" />

      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>计划生成</h1>
        <p style={styles.pageDesc}>
          左侧先确认人格与场景，再上传教材开始分析；右侧集中查看、编辑和管理学习计划。
        </p>
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
          onOpenStudyDialog={() => { void handleOpenStudyDialog(); }}
          canOpenStudyDialog={Boolean(activePlan || studySession)}
          hasStudySession={Boolean(studySession)}
          onRenameStudyUnitTitle={renameStudyUnitTitle}
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
