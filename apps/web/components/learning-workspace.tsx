"use client";

import type { CSSProperties } from "react";
import type { LearningPlan, PersonaProfile } from "@gal-learner/shared";

import { CharacterShell } from "./character-shell";
import { DocumentSetup } from "./document-setup";
import { PlanOverview } from "./plan-overview";
import { PersonaSelector } from "./persona-selector";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";
import { mockPersonas } from "../lib/mock-data";
import { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";

interface LearningWorkspaceProps {
  initialPlan?: LearningPlan;
  personas?: PersonaProfile[];
}

export function LearningWorkspace({
  initialPlan,
  personas: initialPersonas = mockPersonas
}: LearningWorkspaceProps) {
  const {
    personas,
    selectedPersona,
    setSelectedPersonaId,
    activePlan,
    activeDocument,
    planHistory,
    planHistoryItems,
    studySession,
    response,
    notice,
    isBusy,
    isSnapshotRefreshing,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    refreshPlanSnapshot
  } = useLearningWorkspaceController({
    initialPlan,
    initialPersonas
  });

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.eyebrow}>GAL Learner v1</p>
          <h1 style={styles.title}>学习工作台</h1>
          <p style={styles.subtitle}>
            左侧处理上传、解析、计划和章节对话，右侧持续更新教师人格与结构化角色事件。
          </p>
          <p style={styles.notice}>{notice}</p>
          <p style={styles.debugLinkRow}>
            <a href="/debug" style={styles.debugLink}>
              打开解析后台
            </a>
          </p>
        </div>
        <PersonaSelector
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onChange={setSelectedPersonaId}
        />
      </section>

      <section style={styles.grid}>
        <div style={styles.studyColumn}>
          <DocumentSetup
            personas={personas}
            selectedPersonaId={selectedPersona.id}
            isBusy={isBusy}
            document={activeDocument}
            plan={activePlan}
            session={studySession}
            onGenerate={(input) => {
              void generatePlanWorkflow(input);
            }}
          />

          <PlanOverview
            plan={activePlan}
            items={planHistoryItems}
            selectedPlanId={activePlan?.id ?? ""}
            documentTitle={activeDocument?.title ?? "未关联教材"}
            personaName={personas.find((persona) => persona.id === activePlan?.personaId)?.name ?? activePlan?.personaId ?? "未关联人格"}
            planPositionLabel={activePlan ? `共 ${planHistory.length} 条` : ""}
            hasSession={Boolean(studySession)}
            isBusy={isBusy}
            isRefreshing={isSnapshotRefreshing}
            onSelectPlan={(planId) =>
              selectPlan(
                planId,
                PLAN_SWITCH_NOTICE
              )
            }
            onRefresh={() => {
              void refreshPlanSnapshot();
            }}
            onCreateSession={() => {
              void createSessionForActivePlan();
            }}
          />

          <article style={styles.studyEntryCard}>
            <p style={styles.studyEntryLabel}>章节对话</p>
            <h2 style={styles.studyEntryTitle}>进入专用章节对话页</h2>
            <p style={styles.studyEntrySummary}>
              在章节对话页中，左侧进行对话，右侧实时展示教材 PDF，并按章节自动联动页码。
            </p>
            <a href="/study" style={styles.studyEntryLink}>
              打开章节对话页
            </a>
          </article>
        </div>

        <CharacterShell
          persona={selectedPersona}
          response={response}
          pending={isBusy}
        />
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1480,
    margin: "0 auto",
    padding: "24px 20px 44px"
  },
  hero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "flex-start",
    marginBottom: 18,
    padding: "20px 22px",
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow)"
  },
  eyebrow: {
    margin: 0,
    color: "var(--accent)",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    fontSize: 12,
    fontWeight: 700
  },
  title: {
    margin: "8px 0 10px",
    fontFamily: "var(--font-display), sans-serif",
    fontSize: "clamp(1.6rem, 3.6vw, 2.8rem)",
    lineHeight: 1.2,
    maxWidth: 720
  },
  subtitle: {
    margin: 0,
    maxWidth: 760,
    color: "var(--muted)",
    fontSize: 16,
    lineHeight: 1.7
  },
  notice: {
    margin: "12px 0 0",
    color: "var(--teal)",
    fontSize: 13
  },
  debugLinkRow: {
    margin: "14px 0 0"
  },
  debugLink: {
    display: "inline-block",
    padding: "10px 14px",
    borderRadius: 14,
    background: "rgba(13, 110, 114, 0.08)",
    border: "1px solid var(--border)",
    color: "var(--accent)",
    fontWeight: 600
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
    gap: 18,
    alignItems: "start"
  },
  studyColumn: {
    display: "grid",
    gap: 18
  },
  studyEntryCard: {
    padding: 24,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)",
    display: "grid",
    gap: 10
  },
  studyEntryLabel: {
    margin: 0,
    fontSize: 12,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  studyEntryTitle: {
    margin: 0,
    fontSize: 24,
    fontFamily: "var(--font-display), sans-serif"
  },
  studyEntrySummary: {
    margin: 0,
    lineHeight: 1.7,
    color: "var(--muted)"
  },
  studyEntryLink: {
    display: "inline-block",
    width: "fit-content",
    marginTop: 2,
    borderRadius: 999,
    border: "1px solid rgba(13, 110, 114, 0.24)",
    background: "rgba(13, 110, 114, 0.1)",
    color: "var(--teal)",
    padding: "10px 14px",
    fontWeight: 600
  }
};
