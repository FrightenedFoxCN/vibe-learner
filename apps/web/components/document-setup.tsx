"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  SceneProfile,
  StudySessionRecord
} from "@vibe-learner/shared";
import type { SceneLibraryItemPayload } from "../lib/api";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onGenerate: (input: { file: File; objective: string }) => void;
  isBusy: boolean;
  document: DocumentRecord | null;
  plan: LearningPlan | null;
  session: StudySessionRecord | null;
  sceneLibraryItems: SceneLibraryItemPayload[];
  selectedSceneLibraryId: string;
  onSelectSceneLibraryId: (sceneId: string) => void;
  sceneProfile?: SceneProfile | null;
}

export function DocumentSetup({
  personas,
  selectedPersonaId,
  onGenerate,
  isBusy,
  document,
  plan,
  session,
  sceneLibraryItems,
  selectedSceneLibraryId,
  onSelectSceneLibraryId,
  sceneProfile
}: DocumentSetupProps) {
  const [file, setFile] = useState<File | null>(null);
  const [objective, setObjective] = useState("请基于教材结构生成首轮学习计划，先给出主线主题，再拆分为细分学习要点。");

  const personaName = personas.find((p) => p.id === selectedPersonaId)?.name ?? "未选择";

  return (
    <div style={styles.wrap}>
      <div style={styles.sectionHead}>
        <span style={styles.sectionTitle}>上传教材</span>
        <span style={styles.personaBadge}>教师：{personaName}</span>
      </div>

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
        <label style={styles.field}>
          <span style={styles.fieldLabel}>计划使用场景</span>
          <select
            value={selectedSceneLibraryId}
            onChange={(event) => onSelectSceneLibraryId(event.target.value)}
            style={styles.select}
          >
            <option value="">不使用场景库场景</option>
            {sceneLibraryItems.map((item) => (
              <option key={item.sceneId} value={item.sceneId}>
                {item.sceneName}
              </option>
            ))}
          </select>
          <span style={styles.fieldHint}>
            {sceneProfile
              ? `当前将使用：${formatSceneSummary(sceneProfile)}`
              : "未选择场景时会回退到本地场景草稿（若存在）。"}
          </span>
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

      <div style={styles.statusGrid}>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>教材</span>
          <span style={styles.statusValue}>
            {document ? formatDocumentSummary(document) : "未上传"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>计划</span>
          <span style={styles.statusValue}>
            {plan ? `${plan.todayTasks.length} 条任务` : "未生成"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>会话</span>
          <span style={styles.statusValue}>
            {session ? formatSessionStatus(session.status) : "未创建"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>场景</span>
          <span style={styles.statusValue}>
            {sceneProfile ? formatSceneSummary(sceneProfile) : "未配置"}
          </span>
        </div>
      </div>

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
    gap: 0,
    paddingRight: 40,
    borderRight: "1px solid var(--border)",
  },
  sectionHead: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 12,
    paddingBottom: 14,
    borderBottom: "1px solid var(--border)",
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)",
  },
  personaBadge: {
    fontSize: 12,
    color: "var(--muted)",
  },
  form: {
    display: "grid",
    gap: 14,
    padding: "16px 0",
  },
  field: {
    display: "grid",
    gap: 6,
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  textarea: {
    width: "100%",
    minHeight: 80,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  fileInput: {
    width: "100%",
    border: "1px solid var(--border)",
    padding: "6px 8px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
  },
  select: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
  },
  fieldHint: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5,
  },
  button: {
    border: "none",
    height: 36,
    padding: "0 18px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    alignSelf: "start",
    justifySelf: "start",
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  statusGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px 20px",
    padding: "12px 0",
    borderTop: "1px solid var(--border)",
    marginTop: 14,
  },
  statusItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline",
  },
  statusLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  statusValue: {
    fontSize: 13,
    color: "var(--ink)",
  },
  unitSection: {
    paddingTop: 14,
    borderTop: "1px solid var(--border)",
    display: "grid",
    gap: 10,
  },
  unitSectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  unitList: {
    display: "grid",
    gap: 4,
  },
  unitItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 12,
    padding: "6px 0",
    borderBottom: "1px solid var(--border)",
  },
  unitTitle: {
    flex: 1,
    minWidth: 0,
    fontSize: 13,
    color: "var(--ink)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  unitMeta: {
    fontSize: 12,
    color: "var(--muted)",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
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

function formatSceneSummary(sceneProfile: SceneProfile) {
  const path = sceneProfile.selectedPath.join(" / ");
  return `${sceneProfile.title}${path ? ` · ${path}` : ""}`;
}

function formatUnitKind(unitKind: string) {
  if (unitKind === "chapter") return "章节";
  if (unitKind === "front_matter") return "前置材料";
  if (unitKind === "back_matter") return "附录";
  return unitKind;
}
