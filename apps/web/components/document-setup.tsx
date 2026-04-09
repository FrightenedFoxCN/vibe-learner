"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudySessionRecord
} from "@gal-learner/shared";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onGenerate: (input: {
    file: File;
    objective: string;
    deadline: string;
    studyDaysPerWeek: number;
    sessionMinutes: number;
  }) => void;
  isBusy: boolean;
  document: DocumentRecord | null;
  plan: LearningPlan | null;
  session: StudySessionRecord | null;
}

export function DocumentSetup({
  personas,
  selectedPersonaId,
  onGenerate,
  isBusy,
  document,
  plan,
  session
}: DocumentSetupProps) {
  const [file, setFile] = useState<File | null>(null);
  const [objective, setObjective] = useState("在两周内掌握这本教材的第一章并完成一次复习。");
  const [deadline, setDeadline] = useState("2026-05-01");
  const [studyDaysPerWeek, setStudyDaysPerWeek] = useState(4);
  const [sessionMinutes, setSessionMinutes] = useState(35);

  return (
    <article style={styles.panel}>
      <p style={styles.sectionLabel}>教材启动</p>
      <h2 style={styles.title}>上传教材并生成第一版计划</h2>
      <p style={styles.summary}>
        当前教师人格：{personas.find((persona) => persona.id === selectedPersonaId)?.name ?? "未选择"}
      </p>

      <div style={styles.formGrid}>
        <label style={styles.field}>
          <span>教材 PDF</span>
          <input
            type="file"
            accept=".pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label style={styles.field}>
          <span>学习目标</span>
          <textarea
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            style={styles.textarea}
          />
        </label>
        <label style={styles.field}>
          <span>截止日期</span>
          <input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
        </label>
        <label style={styles.field}>
          <span>每周学习天数</span>
          <input
            type="number"
            min={1}
            max={7}
            value={studyDaysPerWeek}
            onChange={(event) => setStudyDaysPerWeek(Number(event.target.value))}
          />
        </label>
        <label style={styles.field}>
          <span>单次学习分钟数</span>
          <input
            type="number"
            min={10}
            max={180}
            value={sessionMinutes}
            onChange={(event) => setSessionMinutes(Number(event.target.value))}
          />
        </label>
      </div>

      <button
        style={styles.button}
        disabled={isBusy || !file}
        onClick={() => {
          if (!file) {
            return;
          }
          onGenerate({
            file,
            objective,
            deadline,
            studyDaysPerWeek,
            sessionMinutes
          });
        }}
      >
        {isBusy ? "处理中..." : "上传并生成计划"}
      </button>

      <div style={styles.statusGrid}>
        <div style={styles.card}>
          <strong>Document</strong>
          <p>{document ? `${document.title} · ${document.status}` : "尚未上传教材"}</p>
        </div>
        <div style={styles.card}>
          <strong>Plan</strong>
          <p>{plan?.overview ?? "尚未生成学习计划"}</p>
        </div>
        <div style={styles.card}>
          <strong>Session</strong>
          <p>{session ? `${session.sectionId} · ${session.status}` : "尚未创建学习会话"}</p>
        </div>
      </div>
    </article>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 28,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  sectionLabel: {
    margin: 0,
    fontSize: 12,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  title: {
    margin: "10px 0 6px",
    fontSize: 28,
    fontFamily: "var(--font-display), sans-serif"
  },
  summary: {
    margin: "0 0 18px",
    color: "var(--muted)"
  },
  formGrid: {
    display: "grid",
    gap: 14
  },
  field: {
    display: "grid",
    gap: 8
  },
  textarea: {
    width: "100%",
    minHeight: 96,
    borderRadius: 16,
    border: "1px solid var(--border)",
    padding: 14,
    resize: "vertical"
  },
  button: {
    marginTop: 18,
    border: 0,
    borderRadius: 999,
    padding: "14px 18px",
    background: "var(--teal)",
    color: "white",
    cursor: "pointer"
  },
  statusGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 12,
    marginTop: 18
  },
  card: {
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.76)",
    border: "1px solid var(--border)"
  }
};
