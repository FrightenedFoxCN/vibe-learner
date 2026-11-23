"use client";

import dynamic from "next/dynamic";
import { useEffect, type CSSProperties } from "react";
import { useDocumentDebugData } from "../../hooks/use-document-debug-data";
import { PageDebugPanel } from "./page-debug-panel";
import { useCurrentPageDebugSnapshot } from "./page-debug-context";
import { useLearningDebugSnapshot } from "./debug-provider";
import { StudyDebugPanels } from "./study-debug-panels";

const DocumentDebugPanels = dynamic(
  () => import("./document-debug-panels").then((module) => module.DocumentDebugPanels),
  { ssr: false, loading: () => <p role="status">正在加载教材诊断…</p> },
);
const DiagnosticTimeline = dynamic(
  () => import("./diagnostic-timeline").then((module) => module.DiagnosticTimeline),
  { ssr: false, loading: () => <p role="status">正在加载诊断时间线…</p> },
);

type DebugOverlayBodyProps = {
  open: boolean;
  pathname: string;
  view: "page" | "global";
  pageEvents: boolean;
  onTogglePageEvents: () => void;
  refreshRevision: number;
  onReady: (ready: boolean) => void;
};

export function DebugOverlayBody({
  open,
  pathname,
  view,
  pageEvents,
  onTogglePageEvents,
  refreshRevision,
  onReady,
}: DebugOverlayBodyProps) {
  const workspace = useLearningDebugSnapshot();
  const pageSnapshot = useCurrentPageDebugSnapshot();
  const activeDocumentId = workspace?.activeDocument?.id ?? "";
  const debugData = useDocumentDebugData(
    activeDocumentId,
    open && view === "page" && pathname === "/plan" && Boolean(activeDocumentId),
    Boolean(workspace?.activeDocument?.debugReady),
    refreshRevision,
  );

  useEffect(() => {
    onReady(true);
  }, [onReady]);
  if (!open) return null;
  return (
    <>
      {view === "global" ? (
        <DiagnosticTimeline />
      ) : (
        <>
          <button
            style={styles.secondaryButton}
            aria-expanded={pageEvents}
            onClick={onTogglePageEvents}
          >
            当前页面请求与动作
          </button>
          {pageEvents && <DiagnosticTimeline currentPageOnly />}
          {pathname === "/plan" && workspace ? (
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
          ) : pathname === "/study" && workspace ? (
            <StudyDebugPanels
              document={workspace.activeDocument}
              persona={workspace.selectedPersona ?? null}
              session={workspace.studySession}
              response={workspace.response}
            />
          ) : pageSnapshot ? (
            <PageDebugPanel
              title={pageSnapshot.title}
              error={pageSnapshot.error}
              summary={pageSnapshot.summary}
              details={pageSnapshot.details}
            />
          ) : (
            <div style={styles.emptyState}>暂无调试面板。</div>
          )}
        </>
      )}
    </>
  );
}

const styles: Record<string, CSSProperties> = {
  secondaryButton: {
    minWidth: 44,
    minHeight: 44,
    padding: "0 12px",
    border: "1px solid var(--border)",
    borderRadius: 10,
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  emptyState: {
    border: "1px dashed var(--border)",
    borderRadius: 16,
    padding: "18px 16px",
    fontSize: 13,
    color: "var(--muted)",
    background: "var(--bg)",
  },
};
