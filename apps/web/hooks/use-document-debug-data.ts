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
} from "../lib/data/documents";
import { getModelToolConfig } from "../lib/data/model-tools";

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
  lastUpdatedAt: string;
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
  lastUpdatedAt: "",
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
        loading: refreshKey > 0,
        error: "",
        lastUpdatedAt: deriveLastUpdatedAt(cached),
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
        loading: true,
        lastUpdatedAt: current.lastUpdatedAt
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
        lastUpdatedAt: deriveLastUpdatedAt(nextSnapshot),
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

  const autoRefreshActive = Boolean(
    enabled
    && documentId
    && !state.loading
    && (
      !debugReady
      || state.processReport?.status === "running"
      || state.planReport?.status === "running"
    )
  );

  useEffect(() => {
    if (!autoRefreshActive) {
      return;
    }
    const delayMs = !debugReady ? 3000 : 2200;
    const timeoutId = window.setTimeout(() => {
      setRefreshKey((current) => current + 1);
    }, delayMs);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [autoRefreshActive, debugReady, documentId, state.planReport?.status, state.processReport?.status]);

  return {
    ...state,
    autoRefreshActive,
    refresh: () => setRefreshKey((current) => current + 1)
  };
}

function deriveLastUpdatedAt(snapshot: DocumentDebugSnapshot) {
  const timestamps = [
    snapshot.debugRecord?.processedAt ?? "",
    snapshot.processReport?.updatedAt ?? "",
    snapshot.planReport?.updatedAt ?? "",
  ]
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => {
      const parsed = Date.parse(value);
      return Number.isNaN(parsed) ? null : { value, parsed };
    })
    .filter((entry): entry is { value: string; parsed: number } => Boolean(entry));
  if (!timestamps.length) {
    return "";
  }
  timestamps.sort((left, right) => right.parsed - left.parsed);
  return timestamps[0].value;
}
