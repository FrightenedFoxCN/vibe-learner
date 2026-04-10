"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudySessionRecord
} from "@vibe-learner/shared";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onGenerate: (input: { file: File; objective: string }) => void;
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
  const [objective, setObjective] = useState("请基于教材结构生成首轮学习计划，先给出主线主题，再拆分为细分学习要点。");

  const personaName = personas.find((p) => p.id === selectedPersonaId)?.name ?? "未选择";

  return (
    <div style={styles.wrap}>
      {/* 标题行 */}
      <div style={styles.headerRow}>
        <h2 style={styles.title}>上传教材并生成计划</h2>
        <span style={styles.persona}>教师人格：{personaName}</span>
      </div>

      {/* 表单 */}
      <div style={styles.form}>
        <label style={styles.field}>
          <span style={styles.fieldLabel}>教材文件（PDF）</span>
          <input
            type="file"
            accept=".pdf"
            style={styles.fileInput}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label style={styles.field}>
          <span style={styles.fieldLabel}>学习目标</span>
          <textarea
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            style={styles.textarea}
          />
        </label>
      </div>

      <button
        style={{
          ...styles.button,
          ...(isBusy || !file ? styles.buttonDisabled : {})
        }}
        disabled={isBusy || !file}
        onClick={() => {
          if (!file) return;
          console.info("[vibe-learner] ui:upload_click", {
            filename: file.name,
            sizeBytes: file.size,
            selectedPersonaId
          });
          onGenerate({ file, objective });
        }}
      >
        {isBusy ? "处理中…" : "上传并生成计划"}
      </button>

      {/* 状态行 */}
      <div style={styles.statusRow}>
        <span style={styles.statusItem}>
          <span style={styles.statusKey}>教材状态</span>
          {document ? formatDocumentSummary(document) : "未上传"}
        </span>
        <span style={styles.statusItem}>
          <span style={styles.statusKey}>计划状态</span>
          {plan ? `${plan.todayTasks.length} 条任务` : "未生成"}
        </span>
        <span style={styles.statusItem}>
          <span style={styles.statusKey}>会话状态</span>
          {session ? formatSessionStatus(session.status) : "未创建"}
        </span>
      </div>

      {/* 学习单元列表 */}
      {document?.studyUnits.length ? (
        <div style={styles.unitSection}>
          <span style={styles.unitSectionLabel}>学习单元清单</span>
          <div style={styles.unitList}>
            {document.studyUnits.map((unit) => (
              <div key={unit.id} style={styles.unitItem}>
                <span style={styles.unitTitle}>{unit.title}</span>
                <span style={styles.unitMeta}>
                  p.{unit.pageStart}–{unit.pageEnd} · {formatUnitKind(unit.unitKind)}
                  {unit.includeInPlan ? "" : " · 已跳过"}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0
  },
  headerRow: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 12,
    paddingBottom: 14,
    borderBottom: "1px solid var(--border)"
  },
  title: {
    margin: 0,
    fontSize: 15,
    fontWeight: 700
  },
  persona: {
    fontSize: 12,
    color: "var(--muted)"
  },
  form: {
    display: "grid",
    gap: 14,
    padding: "16px 0"
  },
  field: {
    display: "grid",
    gap: 6,
    fontSize: 13,
    color: "var(--muted)"
  },
  fieldLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)"
  },
  textarea: {
    width: "100%",
    minHeight: 72,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)"
  },
  fileInput: {
    width: "100%",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "6px 8px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13
  },
  button: {
    border: "none",
    borderRadius: 3,
    height: 36,
    padding: "0 18px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    alignSelf: "start",
    justifySelf: "start"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  statusRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px 20px",
    padding: "14px 0",
    fontSize: 13
  },
  statusItem: {
    display: "flex",
    gap: 5,
    alignItems: "baseline",
    color: "var(--ink)"
  },
  statusKey: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  unitSection: {
    paddingTop: 14,
    borderTop: "1px solid var(--border)",
    display: "grid",
    gap: 10
  },
  unitSectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)"
  },
  unitList: {
    display: "grid",
    gap: 6
  },
  unitItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 12,
    flexWrap: "nowrap"
  },
  unitTitle: {
    flex: 1,
    minWidth: 0,
    fontSize: 13,
    color: "var(--ink)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap"
  },
  unitMeta: {
    fontSize: 12,
    color: "var(--muted)",
    whiteSpace: "nowrap",
    flexShrink: 0
  }
};

function formatDocumentSummary(document: DocumentRecord) {
  return [
    document.title,
    formatDocumentStatus(document.status),
    `${document.pageCount} 页`
  ].join(" · ");
}

function formatDocumentStatus(status: string) {
  if (status === "processed") return "解析完成";
  if (status === "processing") return "解析中";
  if (status === "uploaded") return "已上传";
  return status;
}

function formatSessionStatus(status: string) {
  if (status === "active") return "进行中";
  return status;
}

function formatUnitKind(unitKind: string) {
  if (unitKind === "chapter") return "章节";
  if (unitKind === "front_matter") return "前置材料";
  if (unitKind === "back_matter") return "附录";
  return unitKind;
}
