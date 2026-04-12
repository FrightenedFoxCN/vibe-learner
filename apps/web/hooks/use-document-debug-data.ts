"use client";

import type {
  DocumentDebugRecord,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  ModelToolConfig,
  StreamReport
} from "@vibe-learner/shared";
import { useEffect, useRef, useState } from "react";

import {
  getDocumentDebug,
  getDocumentPlanEvents,
  getDocumentPlanningContext,
  getDocumentPlanningTrace,
  getDocumentProcessEvents,
  getModelToolConfig
} from "../lib/api";

interface DocumentDebugSnapshot {
  debugRecord: DocumentDebugRecord | null;
  planningContext: DocumentPlanningContext | null;
  planningTrace: DocumentPlanningTraceResponse | null;
  modelToolConfig: ModelToolConfig | null;
  processReport: StreamReport | null;
  planReport: StreamReport | null;
}

interface DocumentDebugDataState extends DocumentDebugSnapshot {
  loading: boolean;
  error: string;
  debugRecordError: string;
  planningContextError: string;
  planningTraceError: string;
  modelToolConfigError: string;
  processReportError: string;
  planReportError: string;
}

const EMPTY_STATE: DocumentDebugDataState = {
  debugRecord: null,
  planningContext: null,
  planningTrace: null,
  modelToolConfig: null,
  processReport: null,
  planReport: null,
  loading: false,
  error: "",
  debugRecordError: "",
  planningContextError: "",
  planningTraceError: "",
  modelToolConfigError: "",
  processReportError: "",
  planReportError: ""
};

export function useDocumentDebugData(documentId: string, enabled: boolean, debugReady: boolean) {
  const cacheRef = useRef<Map<string, DocumentDebugSnapshot>>(new Map());
  const [state, setState] = useState<DocumentDebugDataState>(EMPTY_STATE);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!enabled || !documentId) {
      setState((current) => ({
        ...EMPTY_STATE,
        modelToolConfig: current.modelToolConfig
      }));
      return;
    }

    let cancelled = false;
    const cached = cacheRef.current.get(documentId);
    if (cached) {
      setState({
        ...cached,
        loading: false,
        error: "",
        debugRecordError: "",
        planningContextError: "",
        planningTraceError: "",
        modelToolConfigError: "",
        processReportError: "",
        planReportError: ""
      });
    } else {
      setState((current) => ({
        ...EMPTY_STATE,
        modelToolConfig: current.modelToolConfig,
        loading: true
      }));
    }

    const load = async () => {
      const fetches = [
        {
          key: "debugRecord" as const,
          load: () => (debugReady ? getDocumentDebug(documentId) : Promise.resolve(null))
        },
        {
          key: "planningContext" as const,
          load: () => (debugReady ? getDocumentPlanningContext(documentId) : Promise.resolve(null))
        },
        {
          key: "planningTrace" as const,
          load: () => (debugReady ? getDocumentPlanningTrace(documentId) : Promise.resolve(null))
        },
        {
          key: "modelToolConfig" as const,
          load: () => getModelToolConfig()
        },
        {
          key: "processReport" as const,
          load: () => getDocumentProcessEvents(documentId)
        },
        {
          key: "planReport" as const,
          load: () => getDocumentPlanEvents(documentId)
        }
      ];

      const results = await Promise.allSettled(fetches.map((item) => item.load()));
      if (cancelled) {
        return;
      }

      const nextSnapshot: DocumentDebugSnapshot = {
        debugRecord: null,
        planningContext: null,
        planningTrace: null,
        modelToolConfig: null,
        processReport: null,
        planReport: null
      };
      const nextErrors = {
        debugRecordError: "",
        planningContextError: "",
        planningTraceError: "",
        modelToolConfigError: "",
        processReportError: "",
        planReportError: ""
      };

      results.forEach((result, index) => {
        const key = fetches[index].key;
        if (result.status === "fulfilled") {
          if (key === "debugRecord") {
            nextSnapshot.debugRecord = result.value as DocumentDebugRecord | null;
          } else if (key === "planningContext") {
            nextSnapshot.planningContext = result.value as DocumentPlanningContext | null;
          } else if (key === "planningTrace") {
            nextSnapshot.planningTrace = result.value as DocumentPlanningTraceResponse | null;
          } else if (key === "modelToolConfig") {
            nextSnapshot.modelToolConfig = result.value as ModelToolConfig | null;
          } else if (key === "processReport") {
            nextSnapshot.processReport = result.value as StreamReport | null;
          } else if (key === "planReport") {
            nextSnapshot.planReport = result.value as StreamReport | null;
          }
          return;
        }
        const errorMessage = result.reason instanceof Error ? result.reason.message : String(result.reason);
        if (key === "debugRecord") {
          nextErrors.debugRecordError = errorMessage;
        } else if (key === "planningContext") {
          nextErrors.planningContextError = errorMessage;
        } else if (key === "planningTrace") {
          nextErrors.planningTraceError = errorMessage;
        } else if (key === "modelToolConfig") {
          nextErrors.modelToolConfigError = errorMessage;
        } else if (key === "processReport") {
          nextErrors.processReportError = errorMessage;
        } else if (key === "planReport") {
          nextErrors.planReportError = errorMessage;
        }
      });

      const errorMessages = Object.values(nextErrors).filter(Boolean);
      const nextError = errorMessages.length === fetches.length ? errorMessages.join("；") : "";

      const nextState: DocumentDebugDataState = {
        ...nextSnapshot,
        loading: false,
        error: nextError,
        ...nextErrors
      };
      cacheRef.current.set(documentId, {
        debugRecord: nextState.debugRecord,
        planningContext: nextState.planningContext,
        planningTrace: nextState.planningTrace,
        modelToolConfig: nextState.modelToolConfig,
        processReport: nextState.processReport,
        planReport: nextState.planReport
      });
      setState(nextState);
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [documentId, enabled, debugReady, refreshKey]);

  return {
    ...state,
    refresh: () => setRefreshKey((current) => current + 1)
  };
}
