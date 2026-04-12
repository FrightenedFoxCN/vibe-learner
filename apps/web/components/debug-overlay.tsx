"use client";

import { usePathname } from "next/navigation";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import { useDocumentDebugData } from "../hooks/use-document-debug-data";
import { DocumentDebugPanels } from "./document-debug-panels";
import { PageDebugPanel } from "./page-debug-panel";
import { useCurrentPageDebugSnapshot } from "./page-debug-context";
import { useLearningWorkspace } from "./learning-workspace-provider";
import { useRuntimeSettings } from "./runtime-settings-provider";
import { StudyDebugPanels } from "./study-debug-panels";

const STORAGE_KEY = "vibe-debug-overlay-open";

export function DebugOverlay() {
  const pathname = usePathname();
  const { showDebugInfo } = useRuntimeSettings();
  const workspace = useLearningWorkspace();
  const pageSnapshot = useCurrentPageDebugSnapshot();
  const [open, setOpen] = useState(false);

  const activeDocumentId = workspace.activeDocument?.id ?? "";
  const debugData = useDocumentDebugData(
    activeDocumentId,
    showDebugInfo && open && pathname === "/plan" && Boolean(activeDocumentId),
    Boolean(workspace.activeDocument?.debugReady)
  );

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "1") {
      setOpen(true);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
  }, [open]);

  useEffect(() => {
    if (!showDebugInfo) {
      setOpen(false);
    }
  }, [showDebugInfo]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const title = useMemo(() => getDebugTitle(pathname), [pathname]);

  if (!showDebugInfo) {
    return null;
  }

  const pageLabel = getDebugPageLabel(pathname);

  return (
    <>
      {open ? <button type="button" style={styles.scrim} onClick={() => setOpen(false)} aria-label="关闭调试浮窗背景遮罩" /> : null}

      <div style={styles.root}>
        {!open ? (
          <button type="button" style={styles.fab} onClick={() => setOpen(true)}>
            <span style={styles.fabLabel}>Debug</span>
            <span style={styles.fabMeta}>{getFabMeta(pathname)}</span>
          </button>
        ) : null}

        {open ? (
          <section style={styles.overlay} aria-label={title}>
            <header style={styles.overlayHeader}>
              <div style={styles.headerCopy}>
                <span style={styles.title}>{title}</span>
                <span style={styles.subtitle}>
                  {pageLabel} · {workspace.activeDocument?.title ?? pageSnapshot?.title ?? "未关联上下文"}
                </span>
              </div>
              <div style={styles.headerActions}>
                {pathname === "/plan" ? (
                  <button type="button" style={styles.secondaryButton} onClick={() => debugData.refresh()}>
                    刷新
                  </button>
                ) : null}
                <button type="button" style={styles.primaryButton} onClick={() => setOpen(false)}>
                  收起
                </button>
              </div>
            </header>

            <div style={styles.overlayBody}>
              {pathname === "/plan" ? (
                <DocumentDebugPanels
                  document={workspace.activeDocument}
                  debugRecord={debugData.debugRecord}
                  debugRecordError={debugData.debugRecordError}
                  planningContext={debugData.planningContext}
                  planningContextError={debugData.planningContextError}
                  planningTrace={debugData.planningTrace}
                  planningTraceError={debugData.planningTraceError}
                  modelToolConfig={debugData.modelToolConfig}
                  modelToolConfigError={debugData.modelToolConfigError}
                  processReport={debugData.processReport}
                  processReportError={debugData.processReportError}
                  planReport={debugData.planReport}
                  planReportError={debugData.planReportError}
                  processLiveDocumentId={workspace.processStreamDocumentId}
                  processLiveEvents={workspace.processStreamEvents}
                  processLiveStatus={workspace.processStreamStatus}
                  planLiveDocumentId={workspace.planStreamDocumentId}
                  planLiveEvents={workspace.planStreamEvents}
                  planLiveStatus={workspace.planStreamStatus}
                  loading={debugData.loading}
                  error={debugData.error}
                />
              ) : pathname === "/study" ? (
                <StudyDebugPanels
                  document={workspace.activeDocument}
                  persona={workspace.selectedPersona ?? null}
                  session={workspace.studySession}
                  response={workspace.response}
                />
              ) : pageSnapshot ? (
                <PageDebugPanel
                  title={pageSnapshot.title}
                  subtitle={pageSnapshot.subtitle}
                  error={pageSnapshot.error}
                  summary={pageSnapshot.summary}
                  details={pageSnapshot.details}
                />
              ) : (
                <div style={styles.emptyState}>当前页面还没有注册调试面板。</div>
              )}
            </div>
          </section>
        ) : null}
      </div>
    </>
  );
}

const styles: Record<string, CSSProperties> = {
  root: {
    position: "fixed",
    right: 20,
    bottom: 20,
    zIndex: 90
  },
  scrim: {
    position: "fixed",
    inset: 0,
    border: "none",
    background: "rgba(13, 32, 40, 0.18)",
    zIndex: 85,
    cursor: "pointer"
  },
  fab: {
    display: "grid",
    gap: 2,
    minWidth: 88,
    padding: "12px 14px",
    border: "1px solid color-mix(in srgb, var(--accent) 28%, var(--border))",
    borderRadius: 16,
    background: "color-mix(in srgb, white 86%, var(--accent-soft))",
    boxShadow: "0 10px 28px rgba(13, 32, 40, 0.12)",
    color: "var(--ink)",
    cursor: "pointer"
  },
  fabLabel: {
    fontSize: 13,
    fontWeight: 700
  },
  fabMeta: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.08em"
  },
  overlay: {
    width: "min(92vw, 680px)",
    maxHeight: "min(78vh, 860px)",
    display: "grid",
    gridTemplateRows: "auto minmax(0, 1fr)",
    border: "1px solid var(--border)",
    borderRadius: 20,
    background: "color-mix(in srgb, white 94%, var(--panel))",
    boxShadow: "0 18px 48px rgba(13, 32, 40, 0.18)",
    overflow: "hidden",
    backdropFilter: "blur(10px)"
  },
  overlayHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    padding: "16px 18px",
    borderBottom: "1px solid var(--border)",
    background: "color-mix(in srgb, white 72%, var(--accent-soft))",
    flexWrap: "wrap"
  },
  headerCopy: {
    display: "grid",
    gap: 4,
    minWidth: 0
  },
  title: {
    fontSize: 16,
    fontWeight: 800,
    color: "var(--ink)"
  },
  subtitle: {
    fontSize: 12,
    color: "var(--muted)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "100%"
  },
  headerActions: {
    display: "flex",
    gap: 8,
    alignItems: "center"
  },
  primaryButton: {
    height: 34,
    padding: "0 12px",
    border: "1px solid var(--accent)",
    borderRadius: 10,
    background: "var(--accent)",
    color: "white",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer"
  },
  secondaryButton: {
    height: 34,
    padding: "0 12px",
    border: "1px solid var(--border)",
    borderRadius: 10,
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer"
  },
  overlayBody: {
    overflowY: "auto",
    padding: 16
  },
  emptyState: {
    border: "1px dashed var(--border)",
    borderRadius: 16,
    padding: "18px 16px",
    fontSize: 13,
    color: "var(--muted)",
    background: "var(--bg)"
  }
};

function getDebugTitle(pathname: string) {
  if (pathname === "/plan") {
    return "计划调试浮窗";
  }
  if (pathname === "/study") {
    return "章节对话调试浮窗";
  }
  if (pathname === "/settings") {
    return "设置调试浮窗";
  }
  if (pathname === "/model-usage") {
    return "用量审计调试浮窗";
  }
  if (pathname === "/persona-spectrum") {
    return "人格页调试浮窗";
  }
  if (pathname === "/scene-setup") {
    return "场景页调试浮窗";
  }
  if (pathname === "/sensory-tools") {
    return "感官工具调试浮窗";
  }
  return "调试浮窗";
}

function getDebugPageLabel(pathname: string) {
  if (pathname === "/plan") {
    return "计划生成";
  }
  if (pathname === "/study") {
    return "章节对话";
  }
  if (pathname === "/settings") {
    return "统一设置";
  }
  if (pathname === "/model-usage") {
    return "用量审计";
  }
  if (pathname === "/persona-spectrum") {
    return "人格色谱";
  }
  if (pathname === "/scene-setup") {
    return "场景搭建";
  }
  if (pathname === "/sensory-tools") {
    return "感官工具";
  }
  return pathname || "当前页面";
}

function getFabMeta(pathname: string) {
  if (pathname === "/plan") {
    return "计划页";
  }
  if (pathname === "/study") {
    return "对话页";
  }
  if (pathname === "/settings") {
    return "设置页";
  }
  if (pathname === "/model-usage") {
    return "审计页";
  }
  if (pathname === "/persona-spectrum") {
    return "人格页";
  }
  if (pathname === "/scene-setup") {
    return "场景页";
  }
  if (pathname === "/sensory-tools") {
    return "工具页";
  }
  return "页面";
}
