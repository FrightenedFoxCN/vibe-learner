"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import { CharacterShell } from "./character-shell";
import { PersonaSelector } from "./persona-selector";
import { StudyConsole } from "./study-console";
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
    <main className="study-dialog-page" style={styles.page}>
      <section style={styles.header}>
        <div style={styles.headerTitleWrap}>
          <p style={styles.eyebrow}>Chapter Dialogue</p>
          <h1 style={styles.title}>章节对话页</h1>
          <p style={styles.subtitle}>{notice}</p>
          <p style={styles.backRow}>
            <a href="/" style={styles.backLink}>返回学习工作台</a>
          </p>
        </div>
        <PersonaSelector
          personas={personas}
          selectedPersonaId={selectedPersona.id}
          onChange={setSelectedPersonaId}
        />
      </section>

      {!studySession ? (
        <section style={styles.sessionHintCard}>
          <p style={styles.sessionHintText}>当前尚未创建章节会话。先基于当前计划创建一个会话，再开始对话。</p>
          <button
            type="button"
            style={styles.primaryButton}
            disabled={isBusy || !activePlan || !activeDocument}
            onClick={() => {
              void createSessionForActivePlan();
            }}
          >
            {isBusy ? "创建中..." : "创建章节会话"}
          </button>
        </section>
      ) : null}

      <section className="study-dialog-grid" style={styles.grid}>
        <div style={styles.leftColumn}>
          <StudyConsole
            isPending={isBusy}
            onAsk={handleAsk}
            onChangeSection={(sectionId) => {
              void handleSwitchSection(sectionId);
              const nextSection = planSections.find((item) => item.id === sectionId);
              if (nextSection) {
                setPdfPage(nextSection.pageStart);
              }
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
            <strong>{activeDocument?.title ?? "未选择教材"}</strong>
            <span>当前页: p.{pdfPage}</span>
          </div>
          {activeDocument ? (
            <iframe
              title="textbook-pdf"
              src={pdfSrc}
              className="study-dialog-pdf-iframe"
              style={styles.iframe}
            />
          ) : (
            <div style={styles.emptyPdf}>请先在工作台上传教材并生成学习计划。</div>
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
    padding: "26px 22px 30px",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "flex-start",
    marginBottom: 18,
  },
  headerTitleWrap: {
    display: "grid",
    gap: 8,
  },
  eyebrow: {
    margin: 0,
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    color: "var(--muted)",
  },
  title: {
    margin: 0,
    fontSize: "clamp(1.9rem, 3.8vw, 3.2rem)",
    fontFamily: "var(--font-display), sans-serif",
  },
  subtitle: {
    margin: 0,
    color: "var(--teal)",
    fontSize: 14,
  },
  backRow: {
    margin: "2px 0 0",
  },
  backLink: {
    display: "inline-block",
    border: "1px solid var(--border)",
    borderRadius: 999,
    padding: "8px 12px",
    background: "var(--panel-strong)",
  },
  sessionHintCard: {
    marginBottom: 16,
    border: "1px solid var(--border)",
    borderRadius: 20,
    background: "var(--panel)",
    padding: 16,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sessionHintText: {
    margin: 0,
    color: "var(--muted)",
  },
  primaryButton: {
    border: 0,
    borderRadius: 12,
    minHeight: 40,
    padding: "0 14px",
    background: "var(--accent)",
    color: "white",
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 16,
    alignItems: "start",
  },
  leftColumn: {
    display: "grid",
    gap: 16,
    alignContent: "start",
  },
  pdfPane: {
    border: "1px solid var(--border)",
    borderRadius: 20,
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow)",
    padding: 12,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    height: "clamp(480px, 76vh, 980px)",
    overflow: "hidden",
  },
  pdfHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
    fontSize: 13,
    color: "var(--muted)",
  },
  iframe: {
    width: "100%",
    height: "100%",
    minHeight: 0,
    border: "1px solid var(--border)",
    borderRadius: 14,
    background: "white",
    display: "block",
  },
  emptyPdf: {
    minHeight: "100%",
    border: "1px dashed var(--border)",
    borderRadius: 14,
    display: "grid",
    placeItems: "center",
    color: "var(--muted)",
    padding: 14,
    textAlign: "center",
  },
};
