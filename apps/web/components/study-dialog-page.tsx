"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";

import { CharacterShell } from "./character-shell";
import { useLearningWorkspace } from "./learning-workspace-provider";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { PLAN_SWITCH_NOTICE } from "../lib/learning-workspace-copy";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

export function StudyDialogPage() {
  const {
    personas,
    selectedPersona,
    setSelectedPersonaId,
    activePlan,
    activeDocument,
    planHistory,
    planHistoryItems,
    planSections,
    selectPlan,
    studySession,
    response,
    notice,
    isBusy,
    createSessionForActivePlan,
    handleAsk,
    handleAskForSection,
    handleSwitchSection,
    handleSubmitQuestionAttempt,
  } = useLearningWorkspace();

  const [pdfPage, setPdfPage] = useState(1);
  const [selectedTheme, setSelectedTheme] = useState("");

  const themeOptions = activePlan?.weeklyFocus ?? [];
  const currentTheme = selectedTheme || themeOptions[0] || "";

  const resolveSectionIdByTheme = useCallback(
    (theme: string) => {
      if (!theme) {
        return "";
      }
      const themeIndex = themeOptions.findIndex((item) => item === theme);
      const exactFocusMatch = activePlan?.schedule.find((item) => {
        const focus = item.focus?.trim() ?? "";
        return focus === theme || focus.includes(theme) || theme.includes(focus);
      });
      if (exactFocusMatch?.unitId) {
        return exactFocusMatch.unitId;
      }

      const chapterScopedUnitIds = (activePlan?.studyUnits ?? [])
        .filter((unit) => unit.includeInPlan)
        .map((unit) => unit.id);

      if (themeIndex >= 0 && chapterScopedUnitIds[themeIndex]) {
        return chapterScopedUnitIds[themeIndex];
      }

      if (themeIndex >= 0) {
        // Prefer de-duplicated chapter sequence for stable theme-to-session switching.
        if (planSections[themeIndex]?.id) {
          return planSections[themeIndex].id;
        }

        const uniqueUnitIds = Array.from(
          new Set((activePlan?.schedule ?? []).map((item) => item.unitId).filter(Boolean))
        );
        if (uniqueUnitIds[themeIndex]) {
          return uniqueUnitIds[themeIndex];
        }
      }
      return planSections[0]?.id ?? "";
    },
    [activePlan?.schedule, activePlan?.studyUnits, planSections, themeOptions]
  );

  const handleThemeChange = useCallback(
    (theme: string) => {
      setSelectedTheme(theme);
      if (!studySession) {
        return;
      }
      const nextSectionId = resolveSectionIdByTheme(theme);
      if (nextSectionId && nextSectionId !== studySession.sectionId) {
        void handleSwitchSection(nextSectionId);
      }
    },
    [handleSwitchSection, resolveSectionIdByTheme, studySession]
  );

  const handleAskByCurrentTheme = useCallback(
    async (message: string) => {
      const targetSectionId = resolveSectionIdByTheme(currentTheme);
      if (targetSectionId) {
        await handleAskForSection(message, targetSectionId);
        return;
      }
      await handleAsk(message);
    },
    [currentTheme, handleAsk, handleAskForSection, resolveSectionIdByTheme]
  );

  useEffect(() => {
    if (!themeOptions.length) {
      setSelectedTheme("");
      return;
    }
    if (!selectedTheme || !themeOptions.includes(selectedTheme)) {
      setSelectedTheme(themeOptions[0]);
    }
  }, [activePlan?.id, selectedTheme, themeOptions]);

  useEffect(() => {
    const firstPage = activeDocument?.sections[0]?.pageStart;
    if (firstPage) {
      setPdfPage(firstPage);
    }
  }, [activeDocument?.id]);

  useEffect(() => {
    if (!studySession || !currentTheme) {
      return;
    }
    const nextSectionId = resolveSectionIdByTheme(currentTheme);
    if (nextSectionId && nextSectionId !== studySession.sectionId) {
      void handleSwitchSection(nextSectionId);
    }
  }, [
    currentTheme,
    handleSwitchSection,
    resolveSectionIdByTheme,
    studySession?.id,
    studySession?.sectionId,
  ]);

  const pdfSrc = activeDocument ? `${AI_BASE_URL}/documents/${activeDocument.id}/file#page=${pdfPage}` : "";

  return (
    <main className="with-app-nav study-dialog-page" style={styles.page}>
      <TopNav currentPath="/study" />

      <div style={styles.topbar}>
        <div style={styles.topbarLeft}>
          <span style={styles.topbarTitle}>章节对话</span>
          {notice ? <span style={styles.notice}>{notice}</span> : null}
          {!studySession ? (
            <>
              <span style={styles.hint}>尚未创建会话</span>
              <button
                type="button"
                style={{ ...styles.inlineBtn, ...(isBusy || !activePlan || !activeDocument ? styles.inlineBtnDisabled : {}) }}
                disabled={isBusy || !activePlan || !activeDocument}
                onClick={() => {
                  void createSessionForActivePlan();
                }}
              >
                {isBusy ? "创建中…" : "创建会话"}
              </button>
            </>
          ) : null}
        </div>

        <div style={styles.topbarRight}>
          <label style={styles.planSwitchWrap}>
            <span style={styles.planSwitchLabel}>Weekly Plan</span>
            <select
              style={styles.planSwitchSelect}
              value={activePlan?.id ?? ""}
              onChange={(event) => selectPlan(event.target.value, PLAN_SWITCH_NOTICE)}
              disabled={!planHistory.length}
            >
              {planHistoryItems.length ? (
                planHistoryItems.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.courseTitle} · {item.documentTitle}
                  </option>
                ))
              ) : (
                <option value="">暂无 weekly plan</option>
              )}
            </select>
          </label>

          <PersonaSelector
            personas={personas}
            selectedPersonaId={selectedPersona.id}
            onChange={setSelectedPersonaId}
            compact
          />
        </div>
      </div>

      <section className="study-dialog-grid" style={styles.grid}>
        <div style={styles.leftColumn}>
          <StudyConsole
            isPending={isBusy}
            onAsk={handleAskByCurrentTheme}
            onSubmitQuestionAttempt={handleSubmitQuestionAttempt}
            onChangeTheme={handleThemeChange}
            onOpenPage={setPdfPage}
            selectedTheme={currentTheme}
            weeklyFocus={themeOptions}
            turns={studySession?.turns ?? []}
            session={response}
            disabled={!studySession}
          />
          <CharacterShell persona={selectedPersona} response={response} pending={isBusy} />
        </div>

        <aside className="study-dialog-pdf-pane" style={styles.pdfPane}>
          <div style={styles.pdfHeader}>
            <span style={styles.pdfTitle}>{activeDocument?.title ?? "未选择教材"}</span>
            <span style={styles.pdfPage}>p.{pdfPage}</span>
          </div>
          {activeDocument ? (
            <iframe title="textbook-pdf" src={pdfSrc} className="study-dialog-pdf-iframe" style={styles.iframe} />
          ) : (
            <div style={styles.emptyPdf}>请先在计划页完成教材上传并生成学习计划。</div>
          )}
        </aside>
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "20px 32px 30px",
    display: "grid",
    gap: 16,
    alignContent: "start"
  },
  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 14
  },
  topbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap"
  },
  topbarRight: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
    justifyContent: "flex-end"
  },
  topbarTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  notice: {
    fontSize: 13,
    color: "var(--teal)"
  },
  hint: {
    fontSize: 13,
    color: "var(--muted)"
  },
  inlineBtn: {
    border: "1px solid var(--border)",
    borderRadius: 3,
    height: 28,
    padding: "0 10px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 12
  },
  inlineBtnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  planSwitchWrap: {
    display: "grid",
    gap: 4
  },
  planSwitchLabel: {
    fontSize: 11,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  planSwitchSelect: {
    minHeight: 30,
    borderRadius: 3,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--ink)",
    padding: "0 8px",
    minWidth: 280,
    maxWidth: 520,
    width: "100%"
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
    gap: 40,
    alignItems: "start"
  },
  leftColumn: {
    display: "grid",
    gap: 24,
    alignContent: "start"
  },
  pdfPane: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    height: "clamp(480px, 82vh, 980px)",
    overflow: "hidden",
    borderLeft: "1px solid var(--border)",
    paddingLeft: 24
  },
  pdfHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    paddingBottom: 10,
    borderBottom: "1px solid var(--border)"
  },
  pdfTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap"
  },
  pdfPage: {
    fontSize: 12,
    color: "var(--muted)",
    whiteSpace: "nowrap",
    flexShrink: 0
  },
  iframe: {
    width: "100%",
    flex: 1,
    minHeight: 0,
    border: "none",
    background: "white",
    display: "block",
    marginTop: 10
  },
  emptyPdf: {
    flex: 1,
    display: "grid",
    placeItems: "center",
    color: "var(--muted)",
    padding: 24,
    textAlign: "center",
    fontSize: 14
  }
};
