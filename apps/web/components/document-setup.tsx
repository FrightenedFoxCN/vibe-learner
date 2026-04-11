"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  SceneProfile,
  StudySessionRecord
} from "@vibe-learner/shared";
import type { SceneLibraryItemPayload } from "../lib/api";
import { PersonaSelector } from "./persona-selector";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onSelectPersonaId: (personaId: string) => void;
  onGenerate: (input: { file: File; objective: string }) => void;
  onOpenStudyDialog: () => void;
  canOpenStudyDialog: boolean;
  hasStudySession: boolean;
  onRenameStudyUnitTitle: (
    documentId: string,
    studyUnitId: string,
    title: string
  ) => Promise<boolean>;
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
  onSelectPersonaId,
  onGenerate,
  onOpenStudyDialog,
  canOpenStudyDialog,
  hasStudySession,
  onRenameStudyUnitTitle,
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
  const [objective, setObjective] = useState("请基于教材结构生成首轮学习计划，先给出学习章节顺序，再拆分每章的细分学习要点。");
  const [editingUnitId, setEditingUnitId] = useState("");
  const [unitTitleDraft, setUnitTitleDraft] = useState("");

  useEffect(() => {
    if (!editingUnitId || !document) {
      return;
    }
    const editingUnit = document.studyUnits.find((unit) => unit.id === editingUnitId);
    if (!editingUnit) {
      setEditingUnitId("");
      setUnitTitleDraft("");
    }
  }, [document, editingUnitId]);

  return (
    <div className="plan-setup-column" style={styles.wrap}>
      <div style={styles.sectionHead}>
        <span style={styles.sectionTitle}>计划设置</span>
        <span style={styles.sectionMeta}>先确定陪伴人格与场景，再上传教材开始分析。</span>
      </div>

      <section style={styles.card}>
        <div style={styles.cardHead}>
          <span style={styles.cardTitle}>上传前配置</span>
          <span style={styles.cardMeta}>人格、场景、章节入口</span>
        </div>

        <label style={styles.field}>
          <span style={styles.fieldLabel}>教师人格</span>
          <PersonaSelector
            personas={personas}
            selectedPersonaId={selectedPersonaId}
            onChange={onSelectPersonaId}
            compact
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

        <div style={styles.actionRow}>
          <Link href="/scene-setup" style={styles.linkButton}>
            去场景编辑
          </Link>
          <button
            type="button"
            style={{
              ...styles.secondaryButton,
              ...((!canOpenStudyDialog || isBusy) ? styles.buttonDisabled : {})
            }}
            disabled={!canOpenStudyDialog || isBusy}
            onClick={onOpenStudyDialog}
          >
            {hasStudySession ? "打开章节对话" : "创建并打开章节对话"}
          </button>
        </div>
      </section>

      <section style={styles.card}>
        <div style={styles.cardHead}>
          <span style={styles.cardTitle}>教材上传与分析</span>
          <span style={styles.cardMeta}>上传 PDF 并生成新的学习计划</span>
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
        </div>

        <button
          type="button"
          style={{
            ...styles.primaryButton,
            ...((isBusy || !file) ? styles.buttonDisabled : {})
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
      </section>

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
                {editingUnitId === unit.id ? (
                  <div style={styles.unitEditWrap}>
                    <input
                      value={unitTitleDraft}
                      onChange={(event) => setUnitTitleDraft(event.target.value)}
                      style={styles.unitTitleInput}
                      placeholder="输入学习单元标题"
                      disabled={isBusy}
                    />
                    <div style={styles.unitActionRow}>
                      <button
                        type="button"
                        style={{
                          ...styles.unitActionButtonPrimary,
                          ...((isBusy || !unitTitleDraft.trim() || unitTitleDraft.trim() === unit.title.trim())
                            ? styles.buttonDisabled
                            : {})
                        }}
                        disabled={isBusy || !unitTitleDraft.trim() || unitTitleDraft.trim() === unit.title.trim()}
                        onClick={() => {
                          if (!document) return;
                          void onRenameStudyUnitTitle(document.id, unit.id, unitTitleDraft).then((didSave) => {
                            if (didSave) {
                              setEditingUnitId("");
                              setUnitTitleDraft("");
                            }
                          });
                        }}
                      >
                        保存
                      </button>
                      <button
                        type="button"
                        style={styles.unitActionButton}
                        disabled={isBusy}
                        onClick={() => {
                          setEditingUnitId("");
                          setUnitTitleDraft("");
                        }}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={styles.unitTitleRow}>
                    <span style={styles.unitTitle}>{unit.title}</span>
                    <button
                      type="button"
                      style={styles.unitEditButton}
                      disabled={isBusy}
                      onClick={() => {
                        setEditingUnitId(unit.id);
                        setUnitTitleDraft(unit.title);
                      }}
                    >
                      编辑标题
                    </button>
                  </div>
                )}
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
    gap: 18
  },
  sectionHead: {
    display: "grid",
    gap: 4,
    paddingBottom: 4
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)"
  },
  sectionMeta: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  card: {
    display: "grid",
    gap: 14,
    padding: 16,
    border: "1px solid var(--border)",
    background: "var(--panel)"
  },
  cardHead: {
    display: "grid",
    gap: 2
  },
  cardTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  cardMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  form: {
    display: "grid",
    gap: 14
  },
  field: {
    display: "grid",
    gap: 6
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  textarea: {
    width: "100%",
    minHeight: 88,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "white",
    resize: "vertical",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)"
  },
  fileInput: {
    width: "100%",
    border: "1px solid var(--border)",
    padding: "6px 8px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13
  },
  select: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13
  },
  fieldHint: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  actionRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10
  },
  linkButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 36,
    padding: "0 14px",
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--accent)",
    fontSize: 13,
    fontWeight: 600
  },
  secondaryButton: {
    border: "1px solid var(--border-strong)",
    minHeight: 36,
    padding: "0 14px",
    background: "var(--accent-soft)",
    color: "var(--accent)",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13
  },
  primaryButton: {
    border: "none",
    minHeight: 38,
    padding: "0 18px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    justifySelf: "start"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  statusGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px 20px",
    padding: "14px 0 0",
    borderTop: "1px solid var(--border)"
  },
  statusItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline"
  },
  statusLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)",
    fontWeight: 600
  },
  statusValue: {
    fontSize: 13,
    color: "var(--ink)"
  },
  unitSection: {
    display: "grid",
    gap: 10,
    paddingTop: 18,
    borderTop: "1px solid var(--border)"
  },
  unitSectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  unitList: {
    display: "grid",
    gap: 8
  },
  unitItem: {
    display: "grid",
    gap: 2,
    padding: "10px 12px",
    background: "var(--panel)",
    border: "1px solid var(--border)"
  },
  unitTitleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10
  },
  unitTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)"
  },
  unitEditWrap: {
    display: "grid",
    gap: 8
  },
  unitTitleInput: {
    width: "100%",
    minHeight: 36,
    border: "1px solid var(--border-strong)",
    padding: "6px 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600
  },
  unitActionRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  unitActionButton: {
    minHeight: 30,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "white",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer"
  },
  unitActionButtonPrimary: {
    minHeight: 30,
    border: "none",
    padding: "0 10px",
    background: "var(--accent)",
    color: "white",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  },
  unitEditButton: {
    minHeight: 28,
    border: "1px solid var(--border)",
    padding: "0 8px",
    background: "white",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  unitMeta: {
    fontSize: 12,
    color: "var(--muted)"
  }
};

function formatDocumentSummary(document: DocumentRecord) {
  return `${document.title} · ${document.studyUnitCount || document.sections.length} 个单元`;
}

function formatSceneSummary(sceneProfile: SceneProfile) {
  const path = sceneProfile.selectedPath.join(" / ");
  return path ? `${sceneProfile.title} · ${path}` : sceneProfile.title || sceneProfile.sceneName || "未命名场景";
}

function formatSessionStatus(status: string) {
  switch (status) {
    case "active":
      return "进行中";
    case "completed":
      return "已完成";
    default:
      return status || "未知";
  }
}

function formatUnitKind(unitKind: string) {
  switch (unitKind) {
    case "chapter":
      return "章节";
    case "section":
      return "小节";
    default:
      return unitKind || "单元";
  }
}
