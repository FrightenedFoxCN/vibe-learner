"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { useDocumentDebugData } from "../../hooks/use-document-debug-data";
import { PageDebugPanel } from "./page-debug-panel";
import { useCurrentPageDebugSnapshot } from "./page-debug-context";
import { useLearningDebugSnapshot } from "./debug-provider";
import { StudyDebugPanels } from "./study-debug-panels";
import styles from "./debug-overlay-body.module.css";

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
            className={styles.secondaryButton}
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
            <div className={styles.emptyState}>暂无调试面板。</div>
          )}
        </>
      )}
    </>
  );
}
