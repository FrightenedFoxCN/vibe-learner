"use client";

import type { CSSProperties } from "react";
import type { LearningPlan, PersonaProfile } from "@gal-learner/shared";

import { CharacterShell } from "./character-shell";
import { DocumentSetup } from "./document-setup";
import { PlanOverview } from "./plan-overview";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
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
    activeSection,
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
    handleAsk,
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

          <StudyConsole
            isPending={isBusy}
            onAsk={handleAsk}
            session={response}
            sectionId={studySession?.sectionId ?? activeSection?.id ?? ""}
            sectionTitle={activeSection?.title ?? ""}
            disabled={!studySession}
          />
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
    padding: "40px 28px 60px"
  },
  hero: {
    display: "flex",
    justifyContent: "space-between",
    gap: 24,
    alignItems: "flex-start",
    marginBottom: 28
  },
  eyebrow: {
    margin: 0,
    color: "var(--accent)",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    fontSize: 13,
    fontWeight: 700
  },
  title: {
    margin: "10px 0 12px",
    fontFamily: "var(--font-display), sans-serif",
    fontSize: "clamp(2.2rem, 5vw, 4.6rem)",
    lineHeight: 1,
    maxWidth: 720
  },
  subtitle: {
    margin: 0,
    maxWidth: 760,
    color: "var(--muted)",
    fontSize: 18,
    lineHeight: 1.6
  },
  notice: {
    margin: "12px 0 0",
    color: "var(--teal)",
    fontSize: 14
  },
  debugLinkRow: {
    margin: "14px 0 0"
  },
  debugLink: {
    display: "inline-block",
    padding: "10px 14px",
    borderRadius: 999,
    background: "var(--panel-strong)",
    border: "1px solid var(--border)",
    textDecoration: "none"
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.2fr) minmax(360px, 0.8fr)",
    gap: 24
  },
  studyColumn: {
    display: "grid",
    gap: 24
  }
};
