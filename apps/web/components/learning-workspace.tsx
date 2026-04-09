"use client";

import type { CSSProperties } from "react";
import { useEffect, useState, useTransition } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

import { CharacterShell } from "./character-shell";
import { DocumentSetup } from "./document-setup";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
import {
  createLearningPlan,
  createStudySession,
  listPersonas,
  sendStudyMessage,
  uploadAndProcessDocument
} from "../lib/api";
import { mockPlan, mockPersonas } from "../lib/mock-data";

interface LearningWorkspaceProps {
  initialPlan?: LearningPlan;
  personas?: PersonaProfile[];
}

export function LearningWorkspace({
  initialPlan = mockPlan,
  personas: initialPersonas = mockPersonas
}: LearningWorkspaceProps) {
  const [personas, setPersonas] = useState(initialPersonas);
  const [selectedPersonaId, setSelectedPersonaId] = useState(initialPersonas[0]?.id ?? "");
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [plan, setPlan] = useState<LearningPlan | null>(initialPlan);
  const [studySession, setStudySession] = useState<StudySessionRecord | null>(null);
  const [response, setResponse] = useState<StudyChatResponse | null>(null);
  const [notice, setNotice] = useState("服务未连接时会显示内置示例人格。");
  const [isPending, startTransition] = useTransition();

  const selectedPersona =
    personas.find((persona) => persona.id === selectedPersonaId) ?? personas[0];

  useEffect(() => {
    let active = true;
    startTransition(async () => {
      try {
        const remotePersonas = await listPersonas();
        if (!active || remotePersonas.length === 0) {
          return;
        }
        setPersonas(remotePersonas);
        setSelectedPersonaId((current) => current || remotePersonas[0].id);
        setNotice("当前已连接本地 AI 服务。");
      } catch {
        if (active) {
          setNotice("未连接到本地 AI 服务，当前显示内置示例数据。");
        }
      }
    });

    return () => {
      active = false;
    };
  }, []);

  const handleAsk = (message: string) => {
    if (!studySession) {
      return;
    }
    startTransition(async () => {
      const next = await sendStudyMessage({
        sessionId: studySession.id,
        message
      });
      setResponse(next);
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
          <p style={styles.notice}>{notice}</p>
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
            isBusy={isPending}
            document={document}
            plan={plan}
            session={studySession}
            onGenerate={(input) => {
              startTransition(async () => {
                const nextDocument = await uploadAndProcessDocument(input.file);
                const nextPlan = await createLearningPlan({
                  documentId: nextDocument.id,
                  personaId: selectedPersona.id,
                  objective: input.objective,
                  deadline: input.deadline,
                  studyDaysPerWeek: input.studyDaysPerWeek,
                  sessionMinutes: input.sessionMinutes
                });
                const nextSession = await createStudySession({
                  documentId: nextDocument.id,
                  personaId: selectedPersona.id,
                  sectionId: nextDocument.sections[0]?.id ?? `${nextDocument.id}:intro`
                });
                setDocument(nextDocument);
                setPlan(nextPlan);
                setStudySession(nextSession);
                setResponse(null);
              });
            }}
          />

          <article style={styles.panel}>
            <p style={styles.sectionLabel}>今日计划</p>
            <h2 style={styles.panelTitle}>{plan?.overview ?? initialPlan.overview}</h2>
            <div style={styles.taskGrid}>
              {(plan?.todayTasks ?? initialPlan.todayTasks).map((task) => (
                <div key={task} style={styles.taskCard}>
                  {task}
                </div>
              ))}
            </div>
          </article>

          <StudyConsole
            isPending={isPending}
            onAsk={handleAsk}
            session={response}
            sectionId={studySession?.sectionId ?? document?.sections[0]?.id ?? "chapter-1"}
            disabled={!studySession}
          />
        </div>

        <CharacterShell
          persona={selectedPersona}
          response={response}
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
  notice: {
    margin: "12px 0 0",
    color: "var(--teal)",
    fontSize: 14
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
