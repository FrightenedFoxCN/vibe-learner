"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import { CharacterShell } from "./character-shell";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
import { TopNav } from "./top-nav";
import { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";
import { mockPersonas } from "../lib/mock-data";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

export function StudyDialogPage() {
  const {
    personas,
    selectedPersona,
    setSelectedPersonaId,
    activePlan,
    activeDocument,
    planSections,
    activeSection,
    studySession,
    response,
    notice,
    isBusy,
    createSessionForActivePlan,
    handleSwitchSection,
    handleAsk,
  } = useLearningWorkspaceController({
    initialPersonas: mockPersonas,
  });

  const [pdfPage, setPdfPage] = useState<number>(1);

  useEffect(() => {
    if (activeSection?.pageStart) {
      setPdfPage(activeSection.pageStart);
    }
  }, [activeSection?.id]);

  const pdfSrc = activeDocument
    ? `${AI_BASE_URL}/documents/${activeDocument.id}/file#page=${pdfPage}`
    : "";

  return (
    <main className="with-app-nav study-dialog-page" style={styles.page}>
      <TopNav currentPath="/study" />

      {/* 顶栏 */}
      <div style={styles.topbar}>
        <div style={styles.topbarLeft}>
          <span style={styles.topbarTitle}>章节对话</span>
          {notice ? <span style={styles.notice}>{notice}</span> : null}
          {!studySession ? (
            <>
              <span style={styles.hint}>尚未创建会话</span>
              <button
                type="button"
                style={{
                  ...styles.inlineBtn,
                  ...(isBusy || !activePlan || !activeDocument ? styles.inlineBtnDisabled : {})
                }}
                disabled={isBusy || !activePlan || !activeDocument}
                onClick={() => { void createSessionForActivePlan(); }}
              >
                {isBusy ? "创建中…" : "创建"}
              </button>
            </>
          ) : null}
        </div>
        <PersonaSelector
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onChange={setSelectedPersonaId}
          compact
        />
      </div>

      {/* 主体双栏 */}
      <section className="study-dialog-grid" style={styles.grid}>
        <div style={styles.leftColumn}>
          <StudyConsole
            isPending={isBusy}
            onAsk={handleAsk}
            onChangeSection={(sectionId) => {
              void handleSwitchSection(sectionId);
              const nextSection = planSections.find((item) => item.id === sectionId);
              if (nextSection) setPdfPage(nextSection.pageStart);
            }}
            onOpenPage={(page) => setPdfPage(page)}
            session={response}
            sectionId={studySession?.sectionId ?? activeSection?.id ?? ""}
            sectionTitle={activeSection?.title ?? ""}
            sections={planSections}
            disabled={!studySession}
          />
          <CharacterShell
            persona={selectedPersona}
            response={response}
            pending={isBusy}
          />
        </div>

        <aside className="study-dialog-pdf-pane" style={styles.pdfPane}>
          <div style={styles.pdfHeader}>
            <span style={styles.pdfTitle}>{activeDocument?.title ?? "未选择教材"}</span>
            <span style={styles.pdfPage}>p.{pdfPage}</span>
          </div>
          {activeDocument ? (
            <iframe
              title="textbook-pdf"
              src={pdfSrc}
              className="study-dialog-pdf-iframe"
              style={styles.iframe}
            />
          ) : (
            <div style={styles.emptyPdf}>请先在计划页上传教材并生成学习计划。</div>
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
