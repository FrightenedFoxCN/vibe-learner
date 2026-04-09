"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type { LearningPlan, PersonaProfile } from "@gal-learner/shared";

import { CharacterShell } from "./character-shell";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
import { useStudySession } from "../lib/use-study-session";

interface LearningWorkspaceProps {
  initialPlan: LearningPlan;
  personas: PersonaProfile[];
}

const INITIAL_SECTION_ID = "chapter-1";

export function LearningWorkspace({ initialPlan, personas }: LearningWorkspaceProps) {
  const [selectedPersonaId, setSelectedPersonaId] = useState(personas[0]?.id ?? "");
  const { session, isPending, ask } = useStudySession();

  const selectedPersona =
    personas.find((persona) => persona.id === selectedPersonaId) ?? personas[0];

  const handleAsk = (message: string) => {
    ask({
      message,
      personaId: selectedPersona.id,
      sectionId: INITIAL_SECTION_ID
    });
  };

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.eyebrow}>Persona-aware Study Workspace</p>
          <h1 style={styles.title}>把教材导学和角色演出放在同一条协议上</h1>
          <p style={styles.subtitle}>
            页面左侧负责学习流程，右侧负责教师人格与角色状态。未来接入 Live2D 时，只替换角色渲染器。
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
          <article style={styles.panel}>
            <p style={styles.sectionLabel}>今日计划</p>
            <h2 style={styles.panelTitle}>{initialPlan.overview}</h2>
            <div style={styles.taskGrid}>
              {initialPlan.todayTasks.map((task) => (
                <div key={task} style={styles.taskCard}>
                  {task}
                </div>
              ))}
            </div>
          </article>

          <StudyConsole
            isPending={isPending}
            onAsk={handleAsk}
            session={session}
            sectionId={INITIAL_SECTION_ID}
          />
        </div>

        <CharacterShell
          persona={selectedPersona}
          response={session}
          pending={isPending}
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
  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.2fr) minmax(360px, 0.8fr)",
    gap: 24
  },
  studyColumn: {
    display: "grid",
    gap: 24
  },
  panel: {
    padding: 24,
    borderRadius: 28,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)",
    backdropFilter: "blur(18px)"
  },
  sectionLabel: {
    margin: 0,
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    color: "var(--muted)"
  },
  panelTitle: {
    margin: "10px 0 18px",
    fontSize: 28,
    fontFamily: "var(--font-display), sans-serif"
  },
  taskGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 12
  },
  taskCard: {
    padding: "16px 18px",
    borderRadius: 20,
    background: "var(--panel-strong)",
    border: "1px solid var(--border)",
    minHeight: 92,
    lineHeight: 1.5
  }
};
