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
        当前教师人格：{personas.find((persona) => persona.id === selectedPersonaId)?.name ?? "未选择"}。
        上传完成后会依次执行教材入库、OCR/文本提取、章节清理与学习计划生成。
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
          console.info("[gal-learner] ui:upload_click", {
            filename: file.name,
            sizeBytes: file.size,
            selectedPersonaId
          });
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
      <p style={styles.hint}>
        调试提示：打开浏览器控制台和后端终端，可看到上传、解析、建计划、建会话的阶段日志。
      </p>

      <div style={styles.statusGrid}>
        <div style={styles.card}>
          <strong>教材状态</strong>
          <p>{document ? formatDocumentSummary(document) : "尚未上传教材。"}</p>
        </div>
        <div style={styles.card}>
          <strong>计划状态</strong>
          <p>{plan ? `${plan.todayTasks.length} 条今日任务，${plan.schedule.length} 条日程已生成。` : "尚未生成学习计划。"}</p>
        </div>
        <div style={styles.card}>
          <strong>会话状态</strong>
          <p>{session ? `已创建章节会话，状态为 ${formatSessionStatus(session.status)}。` : "尚未创建学习会话。"}</p>
        </div>
      </div>

      {document?.studyUnits.length ? (
        <div style={styles.cleanedSectionBlock}>
          <strong>学习单元清理结果</strong>
          <div style={styles.cleanedSectionList}>
            {document.studyUnits.map((unit) => (
              <div key={unit.id} style={styles.cleanedSectionItem}>
                <span>{unit.title}</span>
                <small>
                  第 {unit.pageStart}-{unit.pageEnd} 页 · {formatUnitKind(unit.unitKind)}
                  {unit.includeInPlan ? " · 纳入计划" : " · 已跳过"}
                </small>
              </div>
            ))}
          </div>
        </div>
      ) : null}
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
  hint: {
    margin: "12px 0 0",
    fontSize: 13,
    color: "var(--muted)"
  },
  card: {
    padding: 16,
    borderRadius: 18,
    background: "rgba(255,255,255,0.76)",
    border: "1px solid var(--border)"
  },
  cleanedSectionBlock: {
    marginTop: 18,
    display: "grid",
    gap: 10
  },
  cleanedSectionList: {
    display: "grid",
    gap: 8
  },
  cleanedSectionItem: {
    padding: 12,
    borderRadius: 16,
    background: "rgba(255,255,255,0.72)",
    border: "1px solid var(--border)",
    display: "grid",
    gap: 4
  }
};

function formatDocumentSummary(document: DocumentRecord) {
  return [
    document.title,
    formatDocumentStatus(document.status),
    `${document.pageCount} 页`,
    `${document.chunkCount} 个分段`,
    `${document.studyUnitCount} 个学习单元`,
    formatOcrStatus(document.ocrStatus)
  ].join(" · ");
}

function formatDocumentStatus(status: string) {
  if (status === "processed") {
    return "解析完成";
  }
  if (status === "processing") {
    return "解析中";
  }
  if (status === "uploaded") {
    return "已上传";
  }
  return status;
}

function formatOcrStatus(status: string) {
  if (status === "fallback_used") {
    return "已使用 OCR 补救";
  }
  if (status === "completed") {
    return "文本提取完成";
  }
  if (status === "pending") {
    return "等待处理";
  }
  return status;
}

function formatSessionStatus(status: string) {
  if (status === "active") {
    return "进行中";
  }
  return status;
}

function formatUnitKind(unitKind: string) {
  if (unitKind === "chapter") {
    return "章节";
  }
  if (unitKind === "front_matter") {
    return "前置材料";
  }
  if (unitKind === "back_matter") {
    return "附录或后置材料";
  }
  return unitKind;
}
