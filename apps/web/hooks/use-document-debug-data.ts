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
}

const EMPTY_STATE: DocumentDebugDataState = {
  debugRecord: null,
  planningContext: null,
  planningTrace: null,
  modelToolConfig: null,
  processReport: null,
  planReport: null,
  loading: false,
  error: ""
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
        error: ""
      });
    } else {
      setState((current) => ({
        ...current,
        loading: true,
        error: ""
      }));
    }

    const load = async () => {
      try {
        const [debugRecord, planningContext, planningTrace, modelToolConfig, processReport, planReport] =
          await Promise.all([
            debugReady ? getDocumentDebug(documentId) : Promise.resolve(null),
            debugReady ? getDocumentPlanningContext(documentId) : Promise.resolve(null),
            debugReady ? getDocumentPlanningTrace(documentId) : Promise.resolve(null),
            getModelToolConfig(),
            getDocumentProcessEvents(documentId),
            getDocumentPlanEvents(documentId)
          ]);
        if (cancelled) {
          return;
        }
        const nextSnapshot = {
          debugRecord,
          planningContext,
          planningTrace,
          modelToolConfig,
          processReport,
          planReport
        };
        cacheRef.current.set(documentId, nextSnapshot);
        setState({
          ...nextSnapshot,
          loading: false,
          error: ""
        });
      } catch (err) {
        if (cancelled) {
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          error: String(err)
        }));
      }
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
