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
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    selectedSceneProfile,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    refreshPlanSnapshot
  } = useLearningWorkspace();

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/plan" />

      {/* ── Heading ── */}
      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>计划生成</h1>
        <p style={styles.pageDesc}>上传教材文件，AI 自动解析章节结构并生成个性化学习计划；右侧可查看与切换历史计划。</p>
      </div>

      {/* ── Toolbar ── */}
      <div style={styles.toolbar}>
        <div style={styles.toolbarField}>
          <span style={styles.toolbarLabel}>教师人格</span>
          <PersonaSelector
            personas={personas}
            selectedPersonaId={selectedPersona.id}
            onChange={setSelectedPersonaId}
            compact
          />
        </div>
        <div style={styles.toolbarField}>
          <span style={styles.toolbarLabel}>场景配置</span>
          <Link href="/scene-setup" style={styles.sceneLink}>去场景编辑</Link>
        </div>
        {notice ? <span style={styles.notice}>{notice}</span> : null}
      </div>

      {/* ── Content ── */}
      <div className="plan-content-grid">
        <DocumentSetup
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          isBusy={isBusy}
          document={activeDocument}
          plan={activePlan}
          session={studySession}
          sceneLibraryItems={sceneLibraryItems}
          selectedSceneLibraryId={selectedSceneLibraryId}
          onSelectSceneLibraryId={setSelectedSceneLibraryId}
          sceneProfile={selectedSceneProfile ?? activePlan?.sceneProfile ?? studySession?.sceneProfile ?? null}
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
          sceneProfile={activePlan?.sceneProfile ?? studySession?.sceneProfile ?? null}
          hasSession={Boolean(studySession)}
          isBusy={isBusy}
          isRefreshing={isSnapshotRefreshing}
          onSelectPlan={(planId) => selectPlan(planId, PLAN_SWITCH_NOTICE)}
          onRefresh={() => { void refreshPlanSnapshot(); }}
          onCreateSession={() => { void createSessionForActivePlan(); }}
        />

        <div style={styles.entryRow}>
          <span style={styles.entryHint}>计划生成后，前往章节对话页开始学习。</span>
          <Link href="/study" style={styles.entryLink}>前往章节对话 →</Link>
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
  sceneLink: {
    display: "inline-flex",
    alignItems: "center",
    height: 32,
    padding: "0 12px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--accent)",
    fontSize: 13,
    fontWeight: 600,
    width: "fit-content",
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
  /* Entry row */
  entryRow: {
    gridColumn: "1 / -1",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "16px 0 0",
    marginTop: 8,
    borderTop: "1px solid var(--border)",
  },
  entryHint: {
    fontSize: 13,
    color: "var(--muted)",
  },
  entryLink: {
    fontSize: 13,
    color: "var(--accent)",
    fontWeight: 600,
  },
};
