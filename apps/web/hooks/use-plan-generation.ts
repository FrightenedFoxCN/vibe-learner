"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentRecord, LearningPlan, SceneProfile, StudySessionRecord } from "@vibe-learner/shared";
import { uploadDocument, processDocumentStream } from "../lib/data/documents";
import { cancelStreamRun, createLearningPlanStream } from "../lib/data/learning-plans";
import { createStudySession } from "../lib/data/study-sessions";
import { buildInitialStudySessionInput } from "../lib/learning-workspace-state";
import { createStudyChatRequestId } from "../lib/client-request-id";
import { compactPreviewValue } from "../lib/preview";
import { logWorkspaceError, logWorkspaceInfo } from "../lib/learning-workspace-telemetry";
import { PLAN_GENERATED_NOTICE, PLAN_GENERATED_SESSION_FAILED_NOTICE } from "../lib/learning-workspace-copy";

export interface GeneratePlanInput {
  mode: "document" | "goal_only";
  file?: File | null;
  objective: string;
}

type StreamEventItem = { stage: string; payload: Record<string, unknown> };
export interface PlanGenerationPort {
  uploadDocument: typeof uploadDocument;
  processDocumentStream: typeof processDocumentStream;
  createLearningPlanStream: typeof createLearningPlanStream;
  cancelStreamRun: typeof cancelStreamRun;
  createStudySession: typeof createStudySession;
}
const defaultPort: PlanGenerationPort = { uploadDocument, processDocumentStream, createLearningPlanStream, cancelStreamRun, createStudySession };

interface PlanGenerationOptions {
  personaId: string;
  blockedReason: string;
  resolveSceneProfile: () => SceneProfile | undefined;
  onStarted: () => void;
  onFinished: () => void;
  onNotice: (notice: string) => void;
  onDocument: (document: DocumentRecord) => void;
  onPlan: (plan: LearningPlan) => () => boolean;
  onSession: (session: StudySessionRecord) => void;
}

export function usePlanGeneration(options: PlanGenerationOptions, port: PlanGenerationPort = defaultPort) {
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [isInterruptingPlan, setIsInterruptingPlan] = useState(false);
  const [processStreamEvents, setProcessStreamEvents] = useState<StreamEventItem[]>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<StreamEventItem[]>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const [processStreamDocumentId, setProcessStreamDocumentId] = useState("");
  const [planStreamDocumentId, setPlanStreamDocumentId] = useState("");
  const generationAbortControllerRef = useRef<AbortController | null>(null);
  const processStreamIdRef = useRef("");
  const planStreamIdRef = useRef("");
  const mountedRef = useRef(true);
  const ownsOperation = (controller: AbortController) => mountedRef.current && generationAbortControllerRef.current === controller;

  const stopActiveOperation = async () => {
    const streams = new Set([processStreamIdRef.current, planStreamIdRef.current].map(id => id.trim()).filter(Boolean));
    generationAbortControllerRef.current?.abort();
    await Promise.allSettled([...streams].map(id => port.cancelStreamRun(id)));
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      void stopActiveOperation();
      generationAbortControllerRef.current = null;
    };
  }, []);

  const cancelPlanGeneration = async () => {
    if (!generationAbortControllerRef.current) return;
    setIsInterruptingPlan(true);
    options.onNotice("正在中断当前任务…");
    await stopActiveOperation();
  };

  const generatePlanWorkflow = async (input: GeneratePlanInput) => {
    if (!mountedRef.current) return;
    if (options.blockedReason) {
      options.onNotice(options.blockedReason);
      return;
    }
    void stopActiveOperation();
    const abortController = new AbortController();
    generationAbortControllerRef.current = abortController;
    processStreamIdRef.current = "";
    planStreamIdRef.current = "";
    setIsInterruptingPlan(false);
    setIsGeneratingPlan(true);
    options.onStarted();
    setProcessStreamEvents([]);
    setPlanStreamEvents([]);
    setProcessStreamStatus(input.mode === "document" ? "running" : "idle");
    setPlanStreamStatus("idle");
    try {
      const selectedScene = options.resolveSceneProfile();
      const sceneProfile = selectedScene ? structuredClone(selectedScene) : undefined;
      let nextDocument: DocumentRecord | null = null;

      if (input.mode === "document") {
        if (!input.file) {
          throw new Error("missing_plan_source_document");
        }
        logWorkspaceInfo("workflow:upload:start", {
          filename: input.file.name,
          sizeBytes: input.file.size,
          personaId: options.personaId
        });

        const uploadedDocument = await port.uploadDocument(input.file, {
          signal: abortController.signal,
        });
        abortController.signal.throwIfAborted();
        setProcessStreamDocumentId(uploadedDocument.id);
        setPlanStreamDocumentId(uploadedDocument.id);
        options.onNotice("教材已上传，正在解析。");
        logWorkspaceInfo("workflow:upload:document_uploaded", {
          documentId: uploadedDocument.id,
          status: uploadedDocument.status
        });

        nextDocument = await port.processDocumentStream(
          uploadedDocument.id,
          {
            signal: abortController.signal,
          },
          (event) => {
            if (!ownsOperation(abortController) || abortController.signal.aborted) return;
            const streamId = event.operationId?.trim() ?? "";
            if (streamId) {
              processStreamIdRef.current = streamId;
            }
            setProcessStreamEvents((current) => [
              ...current.slice(-79),
              {
                stage: event.stage,
                payload: compactPreviewValue(event.payload) as Record<string, unknown>
              }
            ]);
            setProcessStreamStatus(resolveStreamStatus(event.stage));
            options.onNotice("正在解析教材…");
            logWorkspaceInfo("workflow:upload:process_event", {
              documentId: uploadedDocument.id,
              stage: event.stage,
              ...event.payload
            });
          }
        );
        abortController.signal.throwIfAborted();
        logWorkspaceInfo("workflow:upload:document_ready", {
          documentId: nextDocument.id,
          pageCount: nextDocument.pageCount,
          chunkCount: nextDocument.chunkCount,
          ocrStatus: nextDocument.ocrStatus
        });
        options.onDocument(nextDocument);
        options.onNotice("教材解析完成，正在生成计划。");
      } else {
        setProcessStreamDocumentId("");
        setPlanStreamDocumentId("");
        options.onNotice("正在生成计划。");
        logWorkspaceInfo("workflow:goal_only:start", {
          personaId: options.personaId,
          objectiveLength: input.objective.length
        });
      }

      setPlanStreamStatus("running");
      const planClientRequestId = createStudyChatRequestId("learning-plan");
      const nextPlan = await port.createLearningPlanStream(
        {
          documentId: nextDocument?.id ?? "",
          personaId: options.personaId,
          clientRequestId: planClientRequestId,
          expectedDocumentUpdatedAt: nextDocument?.updatedAt ?? "",
          objective: input.objective,
          sceneProfileSummary: sceneProfile?.summary ?? "",
          sceneProfile,
        },
        (event) => {
          if (!ownsOperation(abortController) || abortController.signal.aborted) return;
          const streamId = event.operationId?.trim() ?? "";
          if (streamId) {
            planStreamIdRef.current = streamId;
          }
          setPlanStreamEvents((current) => [
            ...current.slice(-119),
            {
              stage: event.stage,
              payload: compactPreviewValue(event.payload) as Record<string, unknown>
            }
          ]);
          setPlanStreamStatus(resolveStreamStatus(event.stage));
          options.onNotice("正在生成计划…");
          logWorkspaceInfo("workflow:plan_event", {
            documentId: nextDocument?.id ?? "",
            stage: event.stage,
            ...event.payload
          });
        },
        {
          signal: abortController.signal,
        }
      );
      abortController.signal.throwIfAborted();
      logWorkspaceInfo("workflow:upload:plan_ready", {
        planId: nextPlan.id,
        taskCount: nextPlan.todayTasks.length
      });
      const isCurrentPlanView = options.onPlan(nextPlan);

      try {
        const nextSession = await port.createStudySession({
          ...buildInitialStudySessionInput({ plan: nextPlan, document: nextDocument, planId: nextPlan.id, personaId: options.personaId }),
          sceneProfile,
        });
        if (
          !ownsOperation(abortController) || abortController.signal.aborted || !isCurrentPlanView()
        ) {
          return;
        }
        options.onSession(nextSession);
        logWorkspaceInfo("workflow:upload:session_ready", { sessionId: nextSession.id, studyUnitId: nextSession.studyUnitId });
        options.onNotice(nextPlan.creationMode === "goal_only"
              ? "目标计划已生成，会话已创建。"
              : PLAN_GENERATED_NOTICE);
      } catch (sessionError) {
        if (
          !ownsOperation(abortController) || abortController.signal.aborted || !isCurrentPlanView()
        ) {
          return;
        }
        options.onNotice(PLAN_GENERATED_SESSION_FAILED_NOTICE);
        logWorkspaceError("workflow:upload:session_error", sessionError);
      }
    } catch (error) {
      if (!ownsOperation(abortController)) return;
      if (isAbortLikeError(error)) {
        setProcessStreamStatus((current) => (current === "running" ? "cancelled" : current));
        setPlanStreamStatus((current) => (current === "running" ? "cancelled" : current));
        options.onNotice("已中断当前任务。");
        logWorkspaceInfo("workflow:upload:interrupted", {
          mode: input.mode,
        });
        return;
      }
      setProcessStreamStatus((current) => (current === "running" ? "error" : current));
      setPlanStreamStatus((current) => (current === "running" ? "error" : current));
      options.onNotice(`${input.mode === "document" ? "教材处理失败" : "目标计划生成失败"}：${String(error)}`);
      logWorkspaceError("workflow:upload:error", error);
    } finally {
      if (ownsOperation(abortController)) {
        generationAbortControllerRef.current = null;
        processStreamIdRef.current = "";
        planStreamIdRef.current = "";
        setIsInterruptingPlan(false);
        options.onFinished();
        setIsGeneratingPlan(false);
      }
    }
  };

  return { generatePlanWorkflow, cancelPlanGeneration,
    isGeneratingPlan, isInterruptingPlan, processStreamEvents, planStreamEvents,
    processStreamStatus, planStreamStatus, processStreamDocumentId, planStreamDocumentId };
}

function resolveStreamStatus(stage: string) {
  if (stage === "stream_completed") {
    return "completed";
  }
  if (stage === "stream_cancelled") {
    return "cancelled";
  }
  if (stage === "stream_error") {
    return "error";
  }
  return "running";
}

function isAbortLikeError(error: unknown) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return true;
  }
  return String(error).includes("stream_interrupted");
}

