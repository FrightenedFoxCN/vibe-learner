"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentRecord, LearningPlan, SceneProfile } from "@vibe-learner/shared";
import {
  createDiagnosticId,
  diagnosticContext,
  type DiagnosticContext,
} from "../lib/diagnostics";
import { uploadDocument, processDocumentStream } from "../lib/data/documents";
import {
  cancelStreamRun,
  createLearningPlanStream,
  getPlanGenerationOperation,
  getRecoveredLearningPlan,
} from "../lib/data/learning-plans";
import { isApiHttpError } from "../lib/http-error";
import {
  classifyPlanStreamFailure,
  type PlanGenerationIdentity,
} from "../lib/plan-generation-outcome";

const PENDING_PLAN_KEY = "vibe-learner:pending-plan-generation:v1";
const CANCELLATION_WAIT_MS = 5000;

function readPendingPlan(): PlanGenerationIdentity | null {
  const parsed: unknown = JSON.parse(
    sessionStorage.getItem(PENDING_PLAN_KEY) ?? "null",
  );
  if (typeof parsed !== "object" || parsed === null) return null;
  if (
    !("clientRequestId" in parsed) ||
    typeof parsed.clientRequestId !== "string" ||
    !/^[A-Za-z0-9._:-]{1,80}$/.test(parsed.clientRequestId) ||
    !("documentId" in parsed) ||
    typeof parsed.documentId !== "string" ||
    !("personaId" in parsed) ||
    typeof parsed.personaId !== "string" ||
    !parsed.personaId
  )
    return null;
  return {
    clientRequestId: parsed.clientRequestId,
    documentId: parsed.documentId,
    personaId: parsed.personaId,
  };
}

function removeActiveMarker(marker: string) {
  try {
    if (localStorage.getItem(ACTIVE_PLAN_GENERATION_KEY) === marker)
      localStorage.removeItem(ACTIVE_PLAN_GENERATION_KEY);
  } catch {
    /* The navigation warning is best-effort. */
  }
}

function isExactNotFound(error: unknown, detail: string) {
  return (
    isApiHttpError(error) &&
    error.status === 404 &&
    typeof error.payload === "object" &&
    error.payload !== null &&
    "detail" in error.payload &&
    error.payload.detail === detail
  );
}
import { createStudyChatRequestId } from "../lib/client-request-id";
import { compactPreviewValue } from "../lib/preview";
import {
  logWorkspaceError,
  logWorkspaceInfo,
} from "../lib/learning-workspace-telemetry";
import { PLAN_GENERATED_NOTICE } from "../lib/learning-workspace-copy";
import { parsePhysicalPdfRanges, physicalPageIntent } from "../lib/planning-page-scope";
import { ACTIVE_PLAN_GENERATION_KEY } from "../lib/app-navigation";
import { withOutputLanguage } from "../lib/output-language";

export interface GeneratePlanInput {
  mode: "document" | "goal_only";
  file?: File | null;
  objective: string;
  physicalPageRanges?: string;
  outputLanguage?: string;
  processedDocument?: DocumentRecord;
}

type StreamEventItem = { stage: string; payload: Record<string, unknown> };
export interface PlanGenerationPort {
  uploadDocument: typeof uploadDocument;
  processDocumentStream: typeof processDocumentStream;
  createLearningPlanStream: typeof createLearningPlanStream;
  cancelStreamRun: typeof cancelStreamRun;
  getPlanGenerationOperation: typeof getPlanGenerationOperation;
  getRecoveredLearningPlan: typeof getRecoveredLearningPlan;
}
const defaultPort: PlanGenerationPort = {
  uploadDocument,
  processDocumentStream,
  createLearningPlanStream,
  cancelStreamRun,
  getPlanGenerationOperation,
  getRecoveredLearningPlan,
};

interface PlanGenerationOptions {
  personaId: string;
  blockedReason: string;
  resolveSceneProfile: () => SceneProfile | undefined;
  onStarted: () => void;
  onFinished: () => void;
  onNotice: (notice: string) => void;
  onDocument: (document: DocumentRecord) => void;
  onPlan: (plan: LearningPlan) => void;
}

export function usePlanGeneration(
  options: PlanGenerationOptions,
  port: PlanGenerationPort = defaultPort,
) {
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [isInterruptingPlan, setIsInterruptingPlan] = useState(false);
  const [processStreamEvents, setProcessStreamEvents] = useState<StreamEventItem[]>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<StreamEventItem[]>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const [processStreamDocumentId, setProcessStreamDocumentId] = useState("");
  const [planStreamDocumentId, setPlanStreamDocumentId] = useState("");
  const generationDiagnosticRef = useRef<DiagnosticContext | null>(null);
  const activeOperationRef = useRef<{
    controller: AbortController;
    port: PlanGenerationPort;
    request: PlanGenerationIdentity | null;
    cancellationRequested: boolean;
    cancellationSent: boolean;
    cancellationTimer?: ReturnType<typeof setTimeout>;
    marker: string;
  } | null>(null);
  const pendingPlanRef = useRef<PlanGenerationIdentity | null>(null);
  const recoveryRef = useRef<AbortController | null>(null);
  const [hasPendingPlan, setHasPendingPlan] = useState(false);
  const [isCheckingPlan, setIsCheckingPlan] = useState(false);
  const [missingPendingPlan, setMissingPendingPlan] = useState(false);
  const missingPendingPlanRef = useRef(false);
  const processStreamIdRef = useRef("");
  const planStreamIdRef = useRef("");
  const processingCompletedRef = useRef(false);
  const mountedRef = useRef(true);
  const ownsOperation = (controller: AbortController) =>
    mountedRef.current && activeOperationRef.current?.controller === controller;

  const stopActiveOperation = useCallback(async () => {
    const operation = activeOperationRef.current;
    if (!operation) return;
    const streams = new Set(
      [processStreamIdRef.current, planStreamIdRef.current]
        .map((id) => id.trim())
        .filter(Boolean),
    );
    const diagnostic = generationDiagnosticRef.current;
    const cancellation = diagnostic
      ? { ...diagnostic, action_id: createDiagnosticId() }
      : undefined;
    operation.controller.abort();
    if (operation.cancellationTimer) clearTimeout(operation.cancellationTimer);
    removeActiveMarker(operation.marker);
    await Promise.allSettled(
      [...streams].map((id) => operation.port.cancelStreamRun(id, cancellation)),
    );
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    try {
      pendingPlanRef.current = readPendingPlan();
      setHasPendingPlan(Boolean(pendingPlanRef.current));
    } catch {
      /* An invalid or unavailable recovery marker is not a request. */
    }
    return () => {
      recoveryRef.current?.abort();
      recoveryRef.current = null;
      mountedRef.current = false;
      void stopActiveOperation();
      activeOperationRef.current = null;
      generationDiagnosticRef.current = null;
    };
  }, [stopActiveOperation]);

  useEffect(() => {
    if (!isGeneratingPlan) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isGeneratingPlan]);

  const clearPendingPlan = () => {
    pendingPlanRef.current = null;
    missingPendingPlanRef.current = false;
    setHasPendingPlan(false);
    setMissingPendingPlan(false);
    try {
      sessionStorage.removeItem(PENDING_PLAN_KEY);
    } catch {
      /* Any surviving marker only offers a read-only query after reload. */
    }
  };

  const checkPendingPlan = async () => {
    const identity = pendingPlanRef.current;
    if (!identity || recoveryRef.current || !mountedRef.current) return;
    const controller = new AbortController();
    recoveryRef.current = controller;
    missingPendingPlanRef.current = false;
    setMissingPendingPlan(false);
    setIsCheckingPlan(true);
    const ownsQuery = () => mountedRef.current && recoveryRef.current === controller;
    const transport = {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
    };
    try {
      const operation = await port.getPlanGenerationOperation(identity, transport);
      if (!ownsQuery()) return;
      if (operation.status === "running") {
        options.onNotice("上次请求仍在运行。请稍后查询，不会重新发送生成请求。");
      } else if (operation.status === "committed") {
        // Resolve the current row, not the creation snapshot: it may be edited or deleted.
        const plan = await port.getRecoveredLearningPlan(
          operation.planId,
          identity,
          transport,
        );
        if (!ownsQuery()) return;
        options.onPlan(plan);
        clearPendingPlan();
        setPlanStreamStatus("completed");
        options.onNotice("已找回上次生成的学习计划。");
      } else {
        clearPendingPlan();
        setPlanStreamStatus(operation.status === "interrupted" ? "cancelled" : "error");
        options.onNotice(
          operation.status === "interrupted"
            ? "已确认上次生成已中断，未保存计划。"
            : operation.status === "uncertain"
              ? "上次请求未保存计划，无法确认模型是否完成或计费。"
              : "上次生成未保存计划。可主动发起新的生成。",
        );
      }
    } catch (error) {
      if (!ownsQuery()) return;
      if (isExactNotFound(error, "learning_plan_operation_not_found")) {
        missingPendingPlanRef.current = true;
        setMissingPendingPlan(true);
        options.onNotice("暂未查到上次请求。可稍后查询，或放弃查询后再新建计划。");
      } else if (isExactNotFound(error, "plan_not_found")) {
        clearPendingPlan();
        options.onNotice("上次生成已保存，但该计划目前不存在（可能已删除）。");
      } else {
        options.onNotice(
          "暂时无法确认上次生成结果。请稍后查询，不会重新发送生成请求。",
        );
      }
    } finally {
      if (ownsQuery()) {
        recoveryRef.current = null;
        setIsCheckingPlan(false);
      }
    }
  };

  const discardMissingPlan = () => {
    if (
      activeOperationRef.current ||
      recoveryRef.current ||
      !missingPendingPlanRef.current
    )
      return;
    clearPendingPlan();
    options.onNotice(
      "已放弃查询。原请求若延迟被接收，仍可能生成计划；新建前可先查看计划列表。",
    );
  };

  const sendPlanCancellation = (streamId: string) => {
    const operation = activeOperationRef.current;
    if (!operation || !operation.cancellationRequested || operation.cancellationSent)
      return;
    operation.cancellationSent = true;
    const diagnostic = generationDiagnosticRef.current;
    void operation.port
      .cancelStreamRun(
        streamId,
        diagnostic ? { ...diagnostic, action_id: createDiagnosticId() } : undefined,
      )
      .catch(() => operation.controller.abort());
  };

  const cancelPlanGeneration = async () => {
    const operation = activeOperationRef.current;
    if (!operation || operation.cancellationRequested) return;
    setIsInterruptingPlan(true);
    if (!operation.request) {
      options.onNotice("正在中断当前任务…");
      await stopActiveOperation();
      return;
    }
    // Do not stop reading before the first event identifies the cancellable stream.
    operation.cancellationRequested = true;
    options.onNotice("正在请求取消，等待服务确认是否已保存计划…");
    operation.cancellationTimer = setTimeout(
      () => operation.controller.abort(),
      CANCELLATION_WAIT_MS,
    );
    if (planStreamIdRef.current) sendPlanCancellation(planStreamIdRef.current);
  };

  const generatePlanWorkflow = async (input: GeneratePlanInput) => {
    if (!mountedRef.current || activeOperationRef.current || recoveryRef.current)
      return;
    if (pendingPlanRef.current) {
      options.onNotice("请先查询上次生成结果，避免重复生成。");
      return;
    }
    if (options.blockedReason) {
      options.onNotice(options.blockedReason);
      return;
    }
    const diagnostic = diagnosticContext(createDiagnosticId());
    generationDiagnosticRef.current = diagnostic;
    const abortController = new AbortController();
    // Cancel through the same transport that created this operation, even after a rerender.
    const operation = {
      controller: abortController,
      port,
      request: null as PlanGenerationIdentity | null,
      cancellationRequested: false,
      cancellationSent: false,
      cancellationTimer: undefined as ReturnType<typeof setTimeout> | undefined,
      marker: JSON.stringify({ actionId: diagnostic.action_id, mode: input.mode }),
    };
    activeOperationRef.current = operation;
    processStreamIdRef.current = "";
    planStreamIdRef.current = "";
    setIsInterruptingPlan(false);
    setIsGeneratingPlan(true);
    try {
      localStorage.setItem(ACTIVE_PLAN_GENERATION_KEY, operation.marker);
    } catch {
      /* storage is optional */
    }
    options.onStarted();
    setProcessStreamEvents([]);
    setPlanStreamEvents([]);
    setProcessStreamStatus(input.mode === "document" ? "running" : "idle");
    setPlanStreamStatus("idle");
    processingCompletedRef.current = input.mode !== "document";
    try {
      const ranges =
        input.mode === "document"
          ? parsePhysicalPdfRanges(input.physicalPageRanges ?? "")
          : [];
      const selectedScene = options.resolveSceneProfile();
      const planningIntent = withOutputLanguage(
        physicalPageIntent(ranges),
        input.outputLanguage ?? "auto",
      );
      const sceneProfile = selectedScene ? structuredClone(selectedScene) : undefined;
      let nextDocument: DocumentRecord | null = null;

      if (input.mode === "document" && input.processedDocument) {
        nextDocument = structuredClone(input.processedDocument);
        options.onDocument(nextDocument);
        processingCompletedRef.current = true;
        setProcessStreamDocumentId(nextDocument.id);
        setPlanStreamDocumentId(nextDocument.id);
        setProcessStreamStatus("completed");
      } else if (input.mode === "document") {
        if (!input.file) {
          throw new Error("missing_plan_source_document");
        }
        logWorkspaceInfo("workflow:upload:start", {
          filename: input.file.name,
          sizeBytes: input.file.size,
          personaId: options.personaId,
        });

        const uploadedDocument = await port.uploadDocument(input.file, {
          signal: abortController.signal,
          diagnostic,
        });
        abortController.signal.throwIfAborted();
        setProcessStreamDocumentId(uploadedDocument.id);
        setPlanStreamDocumentId(uploadedDocument.id);
        options.onNotice("教材已上传，正在解析。");
        logWorkspaceInfo("workflow:upload:document_uploaded", {
          documentId: uploadedDocument.id,
          status: uploadedDocument.status,
        });

        nextDocument = await port.processDocumentStream(
          uploadedDocument.id,
          {
            signal: abortController.signal,
            diagnostic,
          },
          (event) => {
            if (!ownsOperation(abortController) || abortController.signal.aborted)
              return;
            const streamId = event.operationId?.trim() ?? "";
            if (streamId) {
              processStreamIdRef.current = streamId;
            }
            setProcessStreamEvents((current) => [
              ...current.slice(-79),
              {
                stage: event.stage,
                payload: compactPreviewValue(event.payload) as Record<string, unknown>,
              },
            ]);
            setProcessStreamStatus(resolveStreamStatus(event.stage));
            options.onNotice("正在解析教材…");
            logWorkspaceInfo("workflow:upload:process_event", {
              documentId: uploadedDocument.id,
              stage: event.stage,
              ...event.payload,
            });
          },
        );
        abortController.signal.throwIfAborted();
        logWorkspaceInfo("workflow:upload:document_ready", {
          documentId: nextDocument.id,
          pageCount: nextDocument.pageCount,
          chunkCount: nextDocument.chunkCount,
          ocrStatus: nextDocument.ocrStatus,
        });
        options.onDocument(nextDocument);
        processingCompletedRef.current = true;
        options.onNotice("教材解析完成，正在生成计划。");
      } else {
        setProcessStreamDocumentId("");
        setPlanStreamDocumentId("");
        options.onNotice("正在生成计划。");
        logWorkspaceInfo("workflow:goal_only:start", {
          personaId: options.personaId,
          objectiveLength: input.objective.length,
        });
      }

      if (
        nextDocument &&
        ranges.some((range) => range.pageEnd > nextDocument.pageCount)
      )
        throw new Error(
          `限定范围超出 PDF 的 ${nextDocument.pageCount} 个物理页；未发起计划生成。`,
        );
      const planClientRequestId = createStudyChatRequestId("learning-plan");
      const identity = {
        clientRequestId: planClientRequestId,
        documentId: nextDocument?.id ?? "",
        personaId: options.personaId,
      };
      try {
        sessionStorage.setItem(PENDING_PLAN_KEY, JSON.stringify(identity));
      } catch {
        options.onNotice(
          "无法保存计划恢复记录；未发送生成请求。请允许浏览器会话存储后重试。",
        );
        return;
      }
      operation.request = identity;
      pendingPlanRef.current = identity;
      setHasPendingPlan(true);
      setPlanStreamStatus("running");
      const nextPlan = await port.createLearningPlanStream(
        {
          documentId: nextDocument?.id ?? "",
          personaId: options.personaId,
          clientRequestId: planClientRequestId,
          expectedDocumentUpdatedAt: nextDocument?.updatedAt ?? "",
          objective: input.objective,
          planningIntent,
          sceneProfileSummary: sceneProfile?.summary ?? "",
          sceneProfile,
        },
        (event) => {
          if (!ownsOperation(abortController) || abortController.signal.aborted) return;
          const streamId = event.operationId?.trim() ?? "";
          if (streamId) {
            planStreamIdRef.current = streamId;
            sendPlanCancellation(streamId);
          }
          setPlanStreamEvents((current) => [
            ...current.slice(-119),
            {
              stage: event.stage,
              payload: compactPreviewValue(event.payload) as Record<string, unknown>,
            },
          ]);
          setPlanStreamStatus(resolveStreamStatus(event.stage));
          if (!operation.cancellationRequested) options.onNotice("正在生成计划…");
          logWorkspaceInfo("workflow:plan_event", {
            documentId: nextDocument?.id ?? "",
            stage: event.stage,
            ...event.payload,
          });
        },
        {
          signal: abortController.signal,
          diagnostic,
        },
      );
      abortController.signal.throwIfAborted();
      logWorkspaceInfo("workflow:upload:plan_ready", {
        planId: nextPlan.id,
        taskCount: nextPlan.todayTasks.length,
      });
      options.onPlan(nextPlan);
      clearPendingPlan();
      options.onNotice(
        operation.cancellationRequested
          ? "取消未能阻止保存；学习计划已生成。"
          : PLAN_GENERATED_NOTICE,
      );
    } catch (error) {
      if (!ownsOperation(abortController)) return;
      if (operation.request) {
        const outcome = classifyPlanStreamFailure(error);
        if (outcome !== "unconfirmed") {
          clearPendingPlan();
          if (outcome === "cancelled") {
            setPlanStreamStatus("cancelled");
            options.onNotice("已确认计划生成中断，未保存计划。");
            return;
          }
        } else {
          setPlanStreamStatus("error");
          options.onNotice(
            "未能确认计划是否已保存。请查询上次结果，不会重新发送生成请求。",
          );
          logWorkspaceError("workflow:plan_outcome_unknown", error);
          return;
        }
      }
      if (isAbortLikeError(error)) {
        setProcessStreamStatus((current) =>
          current === "running" ? "cancelled" : current,
        );
        setPlanStreamStatus((current) =>
          current === "running" ? "cancelled" : current,
        );
        options.onNotice("已中断当前任务。");
        logWorkspaceInfo("workflow:upload:interrupted", {
          mode: input.mode,
        });
        return;
      }
      setProcessStreamStatus((current) => (current === "running" ? "error" : current));
      setPlanStreamStatus((current) => (current === "running" ? "error" : current));
      const failurePrefix =
        input.mode === "document"
          ? processingCompletedRef.current
            ? "计划生成失败（教材解析已完成）"
            : "教材解析 / OCR 失败"
          : "目标计划生成失败";
      options.onNotice(
        `${failurePrefix}：${String(error)}。可根据上方进度查看失败阶段并重试。`,
      );
      logWorkspaceError("workflow:upload:error", error);
    } finally {
      if (ownsOperation(abortController)) {
        activeOperationRef.current = null;
        generationDiagnosticRef.current = null;
        processStreamIdRef.current = "";
        planStreamIdRef.current = "";
        setIsInterruptingPlan(false);
        options.onFinished();
        setIsGeneratingPlan(false);
        if (operation.cancellationTimer) clearTimeout(operation.cancellationTimer);
        removeActiveMarker(operation.marker);
      }
    }
  };

  return {
    generatePlanWorkflow,
    cancelPlanGeneration,
    checkPendingPlan,
    discardMissingPlan,
    hasPendingPlan,
    isCheckingPlan,
    missingPendingPlan,
    isGeneratingPlan,
    isInterruptingPlan,
    processStreamEvents,
    planStreamEvents,
    processStreamStatus,
    planStreamStatus,
    processStreamDocumentId,
    planStreamDocumentId,
  };
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
