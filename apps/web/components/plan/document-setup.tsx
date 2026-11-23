"use client";

import { documentUploadError } from "../../lib/document-upload-validation";
import { outputLanguageError } from "../../lib/output-language";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { PlanSetupPageCache } from "../../lib/learning-workspace-page-cache";
import { MaterialIcon } from "../ui/material-icon";
import { parsePhysicalPdfRanges } from "../../lib/planning-page-scope";
import type { GeneratePlanInput } from "../../hooks/use-plan-generation";
import { AppLink } from "../../lib/app-navigation";

import {
  PlanGenerationFields,
  PlanTeachingContext,
  type PlanTeachingContextProps,
} from "./document-setup-fields";
import {
  DocumentProcessingProgress,
  PlanGenerationProgress,
} from "./document-setup-progress";
import type { StreamEventItem } from "./document-setup-stream-summary";
import styles from "./document-setup.module.css";

interface DocumentSetupProps extends PlanTeachingContextProps {
  onGenerate: (input: GeneratePlanInput) => void;
  onInterruptGeneration: () => void;
  isBusy: boolean;
  planStreamEvents: StreamEventItem[];
  planStreamStatus: string;
  processStreamEvents: StreamEventItem[];
  processStreamStatus: string;
  canInterruptGeneration: boolean;
  isInterruptingGeneration: boolean;
  generationBlockedReason?: string;
  cachedState?: PlanSetupPageCache;
  onCachedStateChange?: (state: PlanSetupPageCache) => void;
}

const noHydrationSubscription = () => () => {};
const clientReady = () => true;
const serverPending = () => false;

export function DocumentSetup(props: DocumentSetupProps) {
  const ready = useSyncExternalStore(
    noHydrationSubscription,
    clientReady,
    serverPending,
  );
  // Browser draft values are available only after the server/client hydration
  // snapshot agrees; mounting the form then preserves the stored preference.
  return ready ? (
    <DocumentSetupForm {...props} />
  ) : (
    <p role="status">正在恢复计划设置…</p>
  );
}

function DocumentSetupForm({
  personas,
  selectedPersonaId,
  onSelectPersonaId,
  onGenerate,
  onInterruptGeneration,
  isBusy,
  sceneLibraryItems,
  selectedSceneLibraryId,
  onSelectSceneLibraryId,
  planStreamEvents,
  planStreamStatus,
  processStreamEvents,
  processStreamStatus,
  canInterruptGeneration,
  isInterruptingGeneration,
  generationBlockedReason,
  cachedState,
  onCachedStateChange,
}: DocumentSetupProps) {
  const [file, setFile] = useState<File | null>(() => cachedState?.file ?? null);
  const [generationMode, setGenerationMode] = useState<"document" | "goal_only">(
    () => cachedState?.generationMode ?? "document",
  );
  const [objective, setObjective] = useState(
    () =>
      cachedState?.objective ??
      "请基于教材结构生成首轮学习计划，先排出清晰、可执行的学习排期。",
  );
  const [physicalPageRanges, setPhysicalPageRanges] = useState(
    () => cachedState?.physicalPageRanges ?? "",
  );
  const [outputLanguage, setOutputLanguage] = useState(
    () => cachedState?.outputLanguage ?? "auto",
  );
  const languageError = outputLanguageError(outputLanguage);
  let pageScopeError = "";
  if (generationMode === "document") {
    try {
      parsePhysicalPdfRanges(physicalPageRanges);
    } catch (error) {
      pageScopeError = error instanceof Error ? error.message : "PDF 页范围无效";
    }
  }
  const uploadError =
    generationMode === "document" && file ? documentUploadError(file) : "";

  useEffect(() => {
    onCachedStateChange?.({
      generationMode,
      objective,
      physicalPageRanges,
      outputLanguage,
      file,
    });
  }, [
    file,
    generationMode,
    objective,
    physicalPageRanges,
    outputLanguage,
    onCachedStateChange,
  ]);

  const isGenerateDisabled =
    Boolean(pageScopeError || uploadError || languageError) ||
    isBusy ||
    (generationMode === "document" && !file) ||
    Boolean(generationBlockedReason);
  const generateButtonLabel = isBusy
    ? "处理中…"
    : generationMode === "document"
      ? "生成计划"
      : "按目标生成";
  const shouldShowProcessProgress =
    generationMode === "document" &&
    (processStreamStatus !== "idle" || processStreamEvents.length > 0);

  const handleGenerate = () => {
    if (
      pageScopeError ||
      uploadError ||
      languageError ||
      (generationMode === "document" && !file)
    ) {
      return;
    }
    console.info("[vibe-learner] ui:upload_click", {
      mode: generationMode,
      filename: file?.name ?? "",
      sizeBytes: file?.size ?? 0,
      selectedPersonaId,
    });
    onGenerate({
      mode: generationMode,
      file,
      objective,
      outputLanguage,
      physicalPageRanges: generationMode === "document" ? physicalPageRanges : "",
    });
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.sectionHead}>
        <span className={styles.sectionTitle}>创建计划</span>
        <div className={styles.sectionActions}>
          <button
            type="button"
            className={styles.primaryButton}
            disabled={isGenerateDisabled}
            onClick={handleGenerate}
          >
            <MaterialIcon name="auto_awesome" size={18} />
            {generateButtonLabel}
          </button>
        </div>
      </div>

      <section className={styles.card}>
        <PlanTeachingContext
          personas={personas}
          selectedPersonaId={selectedPersonaId}
          onSelectPersonaId={onSelectPersonaId}
          sceneLibraryItems={sceneLibraryItems}
          selectedSceneLibraryId={selectedSceneLibraryId}
          onSelectSceneLibraryId={onSelectSceneLibraryId}
        />
        <PlanGenerationFields
          generationMode={generationMode}
          objective={objective}
          physicalPageRanges={physicalPageRanges}
          outputLanguage={outputLanguage}
          file={file}
          setGenerationMode={setGenerationMode}
          setObjective={setObjective}
          setPhysicalPageRanges={setPhysicalPageRanges}
          setOutputLanguage={setOutputLanguage}
          setFile={setFile}
          isBusy={isBusy}
          uploadError={uploadError}
          pageScopeError={pageScopeError}
        />

        {generationBlockedReason ? (
          <div className={styles.warningCard}>
            <span className={styles.warningTitle}>开始前需要先修正运行设置</span>
            <span className={styles.warningText}>{generationBlockedReason}</span>
            <AppLink path="/settings" className={styles.warningLink}>
              前往统一设置
            </AppLink>
          </div>
        ) : null}

        {canInterruptGeneration ? (
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isInterruptingGeneration}
            onClick={onInterruptGeneration}
          >
            <MaterialIcon name="close" size={18} />
            {isInterruptingGeneration ? "中断中…" : "中断当前任务"}
          </button>
        ) : null}

        {shouldShowProcessProgress ? (
          <DocumentProcessingProgress
            events={processStreamEvents}
            status={processStreamStatus}
          />
        ) : null}
        <PlanGenerationProgress events={planStreamEvents} status={planStreamStatus} />
      </section>
    </div>
  );
}
