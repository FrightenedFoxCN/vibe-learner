"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

import { CharacterShell } from "./character-shell";
import { DocumentSetup } from "./document-setup";
import { PlanHistory } from "./plan-history";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
import {
  createLearningPlan,
  createStudySession,
  listDocuments,
  listLearningPlans,
  listPersonas,
  sendStudyMessage,
  uploadAndProcessDocument
} from "../lib/api";
import { mockPersonas } from "../lib/mock-data";

interface LearningWorkspaceProps {
  initialPlan?: LearningPlan;
  personas?: PersonaProfile[];
}

export function LearningWorkspace({
  initialPlan,
  personas: initialPersonas = mockPersonas
}: LearningWorkspaceProps) {
  const [personas, setPersonas] = useState(initialPersonas);
  const [selectedPersonaId, setSelectedPersonaId] = useState(initialPersonas[0]?.id ?? "");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [plan, setPlan] = useState<LearningPlan | null>(initialPlan ?? null);
  const [planHistory, setPlanHistory] = useState<LearningPlan[]>([]);
  const [studySession, setStudySession] = useState<StudySessionRecord | null>(null);
  const [response, setResponse] = useState<StudyChatResponse | null>(null);
  const [notice, setNotice] = useState("正在连接本地 AI 服务。未连通时仅显示内置人格，不会展示伪造计划。");
  const [isBusy, setIsBusy] = useState(false);

  const selectedPersona =
    personas.find((persona) => persona.id === selectedPersonaId) ?? personas[0];
  const activePlan = plan ?? initialPlan ?? null;
  const activeSection =
    document?.sections.find((section) => section.id === studySession?.sectionId) ?? document?.sections[0] ?? null;

  const refreshHistorySnapshot = async () => {
    const [remoteDocuments, remotePlans] = await Promise.all([
      listDocuments(),
      listLearningPlans()
    ]);
    const sortedPlans = [...remotePlans].sort((left, right) =>
      (right.createdAt || "").localeCompare(left.createdAt || "")
    );
    setDocuments(remoteDocuments);
    setPlanHistory(sortedPlans);
    if (!plan && sortedPlans[0]) {
      setPlan(sortedPlans[0]);
      setSelectedPersonaId(sortedPlans[0].personaId);
      setDocument(remoteDocuments.find((item) => item.id === sortedPlans[0].documentId) ?? null);
    }
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [remotePersonas, remoteDocuments, remotePlans] = await Promise.all([
          listPersonas(),
          listDocuments(),
          listLearningPlans()
        ]);
        if (!active || remotePersonas.length === 0) {
          return;
        }
        const sortedPlans = [...remotePlans].sort((left, right) =>
          (right.createdAt || "").localeCompare(left.createdAt || "")
        );
        setPersonas(remotePersonas);
        setDocuments(remoteDocuments);
        setPlanHistory(sortedPlans);
        setSelectedPersonaId((current) => current || remotePersonas[0].id);
        if (!plan && sortedPlans[0]) {
          setPlan(sortedPlans[0]);
          setSelectedPersonaId(sortedPlans[0].personaId);
          setDocument(remoteDocuments.find((item) => item.id === sortedPlans[0].documentId) ?? null);
        }
        setNotice("已连接本地 AI 服务，可以直接上传教材、解析并生成学习计划。");
      } catch {
        if (active) {
          setNotice("未连接到本地 AI 服务。当前只保留人格选择，教材、计划和会话都需要后端联通后才会出现。");
        }
      }
    };
    void load();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleFocus = () => {
      void refreshHistorySnapshot();
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [plan]);

  const handleAsk = (message: string) => {
    if (!studySession) {
      return;
    }
    const run = async () => {
      try {
        setIsBusy(true);
        console.info("[gal-learner] workflow:study_chat:start", {
          sessionId: studySession.id,
          messageLength: message.length
        });
        const next = await sendStudyMessage({
          sessionId: studySession.id,
          message
        });
        setResponse(next);
        console.info("[gal-learner] workflow:study_chat:done", {
          sessionId: studySession.id,
          citations: next.citations.length,
          characterEvents: next.characterEvents.length
        });
      } catch (error) {
        setNotice(`导学请求失败: ${String(error)}`);
        console.error("[gal-learner] workflow:study_chat:error", error);
      } finally {
        setIsBusy(false);
      }
    };
    void run();
  };

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
            document={document}
            plan={plan}
            session={studySession}
            onGenerate={(input) => {
              const run = async () => {
                try {
                  setIsBusy(true);
                  console.info("[gal-learner] workflow:upload:start", {
                    filename: input.file.name,
                    sizeBytes: input.file.size,
                    personaId: selectedPersona.id
                  });
                  const nextDocument = await uploadAndProcessDocument(input.file);
                  console.info("[gal-learner] workflow:upload:document_ready", {
                    documentId: nextDocument.id,
                    pageCount: nextDocument.pageCount,
                    chunkCount: nextDocument.chunkCount,
                    ocrStatus: nextDocument.ocrStatus
                  });
                  const nextPlan = await createLearningPlan({
                    documentId: nextDocument.id,
                    personaId: selectedPersona.id,
                    objective: input.objective,
                    deadline: input.deadline,
                    studyDaysPerWeek: input.studyDaysPerWeek,
                    sessionMinutes: input.sessionMinutes
                  });
                  console.info("[gal-learner] workflow:upload:plan_ready", {
                    planId: nextPlan.id,
                    taskCount: nextPlan.todayTasks.length
                  });
                  const nextSession = await createStudySession({
                    documentId: nextDocument.id,
                    personaId: selectedPersona.id,
                    sectionId: nextDocument.sections[0]?.id ?? `${nextDocument.id}:intro`
                  });
                  console.info("[gal-learner] workflow:upload:session_ready", {
                    sessionId: nextSession.id,
                    sectionId: nextSession.sectionId
                  });
                  setDocument(nextDocument);
                  setDocuments((current) => {
                    const filtered = current.filter((item) => item.id !== nextDocument.id);
                    return [nextDocument, ...filtered];
                  });
                  setPlan(nextPlan);
                  setPlanHistory((current) => [nextPlan, ...current.filter((item) => item.id !== nextPlan.id)]);
                  setStudySession(nextSession);
                  setResponse(null);
                  setNotice("教材已完成解析，并创建了新的学习计划。");
                } catch (error) {
                  setNotice(`教材处理失败: ${String(error)}`);
                  console.error("[gal-learner] workflow:upload:error", error);
                } finally {
                  setIsBusy(false);
                }
              };
              void run();
            }}
          />

          <PlanHistory
            plans={planHistory}
            documents={documents}
            personas={personas}
            selectedPlanId={activePlan?.id ?? ""}
            onSelect={(planId) => {
              const nextPlan = planHistory.find((item) => item.id === planId);
              if (!nextPlan) {
                return;
              }
              setPlan(nextPlan);
              setSelectedPersonaId(nextPlan.personaId);
              setDocument(documents.find((item) => item.id === nextPlan.documentId) ?? null);
              setStudySession(null);
              setResponse(null);
              setNotice("已切换到历史学习计划。若要继续导学，请重新创建会话或上传新教材。");
            }}
          />

          <article style={styles.panel}>
            <p style={styles.sectionLabel}>学习计划</p>
            <h2 style={styles.panelTitle}>
              {activePlan?.overview ?? "上传教材后，这里会显示模型整理过的学习安排与今日任务。"}
            </h2>
            {activePlan?.weeklyFocus.length ? (
              <div style={styles.focusRow}>
                {activePlan.weeklyFocus.map((focus) => (
                  <span key={focus} style={styles.focusChip}>
                    {focus}
                  </span>
                ))}
              </div>
            ) : null}
            <div style={styles.taskGrid}>
              {(activePlan?.todayTasks.length ? activePlan.todayTasks : ["暂无今日任务。先上传教材并生成计划。"]).map((task) => (
                <div key={task} style={styles.taskCard}>
                  {task}
                </div>
              ))}
            </div>
            {activePlan?.schedule.length ? (
              <div style={styles.scheduleBlock}>
                {activePlan.schedule.slice(0, 6).map((item) => (
                  <div key={item.id} style={styles.scheduleCard}>
                    <strong>{item.title}</strong>
                    <span>
                      {item.scheduledDate} · {item.estimatedMinutes} 分钟 · {formatActivityType(item.activityType)}
                    </span>
                    <p style={styles.scheduleFocus}>{item.focus}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p style={styles.emptyHint}>计划生成成功后，这里会展开最近几次学习安排。</p>
            )}
          </article>

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
  focusRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 16
  },
  focusChip: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(63, 140, 133, 0.12)",
    border: "1px solid rgba(63, 140, 133, 0.18)",
    fontSize: 13
  },
  taskCard: {
    padding: "16px 18px",
    borderRadius: 20,
    background: "var(--panel-strong)",
    border: "1px solid var(--border)",
    minHeight: 92,
    lineHeight: 1.5
  },
  scheduleBlock: {
    display: "grid",
    gap: 12,
    marginTop: 16
  },
  scheduleCard: {
    display: "grid",
    gap: 6,
    padding: 14,
    borderRadius: 18,
    background: "rgba(255,255,255,0.72)",
    border: "1px solid var(--border)"
  },
  scheduleFocus: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  emptyHint: {
    margin: "16px 0 0",
    color: "var(--muted)",
    lineHeight: 1.6
  }
};

function formatActivityType(activityType: string) {
  if (activityType === "learn") {
    return "学习";
  }
  if (activityType === "review") {
    return "复习";
  }
  if (activityType === "practice") {
    return "练习";
  }
  return activityType;
}
