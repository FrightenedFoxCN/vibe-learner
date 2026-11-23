import { useRef } from "react";
import type { PersonaProfile } from "@vibe-learner/shared";
import type { SceneLibraryItemPayload } from "../../lib/data/scenes";
import type { PlanSetupPageCache } from "../../lib/learning-workspace-page-cache";
import { PersonaSelector } from "../ui/persona-selector";
import { OutputLanguageField } from "../ui/output-language-field";
import styles from "./document-setup.module.css";

export interface PlanTeachingContextProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onSelectPersonaId: (personaId: string) => void;
  sceneLibraryItems: SceneLibraryItemPayload[];
  selectedSceneLibraryId: string;
  onSelectSceneLibraryId: (sceneId: string) => void;
}

export function PlanTeachingContext({
  personas,
  selectedPersonaId,
  onSelectPersonaId,
  sceneLibraryItems,
  selectedSceneLibraryId,
  onSelectSceneLibraryId,
}: PlanTeachingContextProps) {
  return (
    <div className={styles.formSection}>
      <div className={styles.field}>
        <label htmlFor="plan-persona" className={styles.fieldLabel}>
          教师人格
        </label>
        <PersonaSelector
          personas={personas}
          selectedPersonaId={selectedPersonaId}
          onChange={onSelectPersonaId}
          compact
          selectId="plan-persona"
        />
      </div>

      <div className={styles.field}>
        <label htmlFor="plan-scene" className={styles.fieldLabel}>
          计划场景
        </label>
        <select
          id="plan-scene"
          value={selectedSceneLibraryId}
          onChange={(event) => onSelectSceneLibraryId(event.target.value)}
          className={styles.select}
        >
          <option value="">不使用场景库场景</option>
          {sceneLibraryItems.map((item) => (
            <option key={item.sceneId} value={item.sceneId}>
              {item.sceneName}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

type PlanGenerationFieldsProps = Required<PlanSetupPageCache> & {
  setGenerationMode: (value: Required<PlanSetupPageCache>["generationMode"]) => void;
  setObjective: (value: Required<PlanSetupPageCache>["objective"]) => void;
  setPhysicalPageRanges: (
    value: Required<PlanSetupPageCache>["physicalPageRanges"],
  ) => void;
  setOutputLanguage: (value: Required<PlanSetupPageCache>["outputLanguage"]) => void;
  setFile: (value: Required<PlanSetupPageCache>["file"]) => void;
  isBusy: boolean;
  uploadError: string;
  pageScopeError: string;
};

export function PlanGenerationFields({
  generationMode,
  objective,
  physicalPageRanges,
  outputLanguage,
  file,
  setGenerationMode,
  setObjective,
  setPhysicalPageRanges,
  setOutputLanguage,
  setFile,
  isBusy,
  uploadError,
  pageScopeError,
}: PlanGenerationFieldsProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  return (
    <div className={`${styles.formSection} ${styles.formSectionSeparated}`}>
      <div className={styles.form}>
        <div className={styles.field}>
          <label htmlFor="plan-generation-mode" className={styles.fieldLabel}>
            创建方式
          </label>
          <select
            id="plan-generation-mode"
            value={generationMode}
            onChange={(event) =>
              setGenerationMode(
                event.target.value === "goal_only" ? "goal_only" : "document",
              )
            }
            className={styles.select}
          >
            <option value="document">教材 + 目标</option>
            <option value="goal_only">仅学习目标</option>
          </select>
        </div>
        <OutputLanguageField
          value={outputLanguage}
          onChange={setOutputLanguage}
          disabled={isBusy}
        />
        <div className={styles.field}>
          <label htmlFor="plan-document-file" className={styles.fieldLabel}>
            教材文件（PDF）
          </label>
          <input
            ref={fileInputRef}
            id="plan-document-file"
            type="file"
            accept=".pdf"
            className="sr-only"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            disabled={generationMode === "goal_only"}
          />
          <div className={styles.fileSelection} aria-live="polite">
            <button
              type="button"
              className={styles.fileButton}
              disabled={generationMode === "goal_only"}
              onClick={() => fileInputRef.current?.click()}
            >
              {file ? "更换教材" : "选择教材"}
            </button>
            <span className={styles.fileName} title={file?.name}>
              {file?.name ??
                (generationMode === "goal_only"
                  ? "仅学习目标，无需教材"
                  : "尚未选择文件")}
            </span>
          </div>
        </div>
        {generationMode === "document" && (
          <div className={styles.field}>
            <small>每份 PDF 最多 64 MiB、512 个物理页；超限请拆分或压缩后上传。</small>
            {uploadError && <p role="alert">{uploadError}</p>}
          </div>
        )}
        {generationMode === "document" && (
          <div className={styles.field}>
            <label htmlFor="plan-physical-pages" className={styles.fieldLabel}>
              PDF 物理页范围（可选）
            </label>
            <input
              id="plan-physical-pages"
              value={physicalPageRanges}
              maxLength={2000}
              onChange={(event) => setPhysicalPageRanges(event.target.value)}
              placeholder="例如 100–103, 110"
              aria-describedby="plan-physical-page-help"
              aria-invalid={Boolean(pageScopeError)}
            />
            <small id="plan-physical-page-help">
              按 PDF 阅读器从 1
              开始的页序填写；留空表示不限定。书上印刷的页码或罗马数字不能替代物理页。输入后，计划与取证工具只能使用指定页。
            </small>
            {pageScopeError && <p role="alert">{pageScopeError}</p>}
          </div>
        )}
        <div className={styles.field}>
          <label htmlFor="plan-objective" className={styles.fieldLabel}>
            学习目标
          </label>
          <textarea
            id="plan-objective"
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            className={styles.textarea}
          />
        </div>
      </div>
    </div>
  );
}
