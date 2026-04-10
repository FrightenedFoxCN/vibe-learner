"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import { DocumentSetup } from "./document-setup";
import { PlanOverview } from "./plan-overview";
import { PersonaSelector } from "./persona-selector";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
import { useLearningWorkspace } from "./learning-workspace-provider";

export function LearningWorkspace() {
  const {
    personas,
    selectedPersona,
    setSelectedPersonaId,
    activePlan,
    activeDocument,
    planHistory,
    planHistoryItems,
    studySession,
    notice,
    isBusy,
    isSnapshotRefreshing,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    refreshPlanSnapshot
  } = useLearningWorkspace();

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/plan" />

      {/* 顶栏 */}
      <div style={styles.topbar}>
        <div style={styles.topbarLeft}>
          <span style={styles.topbarTitle}>计划生成页</span>
          {notice ? <span style={styles.notice}>{notice}</span> : null}
        </div>
        <PersonaSelector
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onChange={setSelectedPersonaId}
          compact
        />
      </div>

      <div className="plan-content-grid">
        <DocumentSetup
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          isBusy={isBusy}
          document={activeDocument}
          plan={activePlan}
          session={studySession}
          onGenerate={(input) => { void generatePlanWorkflow(input); }}
        />

        <PlanOverview
          plan={activePlan}
          items={planHistoryItems}
          selectedPlanId={activePlan?.id ?? ""}
          documentTitle={activeDocument?.title ?? "未关联教材"}
          personaName={
            personas.find((p) => p.id === activePlan?.personaId)?.name ??
            activePlan?.personaId ??
            "未关联人格"
          }
          planPositionLabel={activePlan ? `共 ${planHistory.length} 条` : ""}
          hasSession={Boolean(studySession)}
          isBusy={isBusy}
          isRefreshing={isSnapshotRefreshing}
          onSelectPlan={(planId) => selectPlan(planId, PLAN_SWITCH_NOTICE)}
          onRefresh={() => { void refreshPlanSnapshot(); }}
          onCreateSession={() => { void createSessionForActivePlan(); }}
        />

        {/* 章节对话入口 */}
        <div style={styles.entryRow}>
          <span style={styles.entryLabel}>章节对话</span>
          <Link href="/study" style={styles.entryLink}>前往章节对话页 →</Link>
        </div>
      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1280,
    margin: "0 auto",
    padding: "20px 32px 48px",
    display: "grid",
    gap: 20,
    alignContent: "start"
  },
  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 14
  },
  topbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12
  },
  topbarTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  notice: {
    fontSize: 13,
    color: "var(--teal)"
  },
  entryRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingTop: 20,
    marginTop: 20,
    borderTop: "1px solid var(--border)"
  },
  entryLabel: {
    fontSize: 13,
    color: "var(--muted)"
  },
  entryLink: {
    fontSize: 13,
    color: "var(--accent)",
    fontWeight: 600
  }
};
