import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import {
  countSceneNodes,
  normalizeSceneTreeNodeForProfile,
} from "../../lib/scene-editor-model";
import { MaterialIcon } from "../ui/material-icon";
import { SceneProposalPreview } from "./scene-proposal-preview";
import { SceneSidebarSection } from "./scene-sidebar-section";
import css from "./scene-workspace.module.css";

export function SceneGenerator({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    collapsedSidebarSections,
    toggleSidebarSection,
    sceneLayers,
    updateSceneGenerationInput,
    sceneKeywordInput,
    setSceneKeywordInput,
    sceneLongTextFile,
    setSceneLongTextFile,
    sceneGenerateMode,
    setSceneGenerateMode,
    sceneGenerateLayerCount,
    setSceneGenerateLayerCount,
    sceneGeneratePending,
    generatedSceneCandidate,
    handleGenerateScene,
    applyGeneratedSceneCandidateToEditor,
  } = controller;
  return (
    <SceneSidebarSection
      title="场景树生成器"
      collapsed={collapsedSidebarSections.includes("generate")}
      onToggle={() => toggleSidebarSection("generate")}
    >
      <label className="grid gap-1.5">
        <span className={css.fieldLabel}>层级偏好（可选）</span>
        <input
          className={`${css.input} h-11 px-2.5`}
          type="number"
          min={1}
          step={1}
          value={sceneGenerateLayerCount}
          onChange={(event) =>
            updateSceneGenerationInput(() =>
              setSceneGenerateLayerCount(event.target.value),
            )
          }
          placeholder="留空表示不限"
        />
      </label>
      <div className="flex items-center justify-between gap-2">
        <div
          className={`${css.modeSwitch} inline-flex min-h-11 min-w-0 flex-1 border border-border`}
        >
          <button
            type="button"
            aria-pressed={sceneGenerateMode === "keywords"}
            className={`${css.modeButton} min-h-11 flex-1 cursor-pointer border-0 px-2.5 text-xs/[1.5]`}
            onClick={() =>
              updateSceneGenerationInput(() => setSceneGenerateMode("keywords"))
            }
          >
            关键词搜索
          </button>
          <button
            type="button"
            aria-pressed={sceneGenerateMode === "long_text"}
            className={`${css.modeButton} min-h-11 flex-1 cursor-pointer border-0 px-2.5 text-xs/[1.5]`}
            onClick={() =>
              updateSceneGenerationInput(() => setSceneGenerateMode("long_text"))
            }
          >
            长文本提取
          </button>
        </div>
        <button
          className={css.sidebarButton}
          type="button"
          disabled={sceneGeneratePending !== null}
          onClick={() => void handleGenerateScene(sceneGenerateMode)}
          title={
            sceneGenerateMode === "keywords"
              ? sceneGeneratePending === "keywords"
                ? "生成中"
                : "根据关键词生成场景树"
              : sceneGeneratePending === "long_text"
                ? "提取中"
                : "根据长文本提取场景树"
          }
          aria-label={
            sceneGenerateMode === "keywords"
              ? sceneGeneratePending === "keywords"
                ? "生成中"
                : "根据关键词生成场景树"
              : sceneGeneratePending === "long_text"
                ? "提取中"
                : "根据长文本提取场景树"
          }
        >
          <MaterialIcon
            name={
              sceneGenerateMode === "keywords"
                ? sceneGeneratePending === "keywords"
                  ? "hourglass_top"
                  : "auto_awesome"
                : sceneGeneratePending === "long_text"
                  ? "hourglass_top"
                  : "description"
            }
            size={14}
          />
        </button>
      </div>
      {sceneGenerateMode === "keywords" ? (
        <label key="keywords-mode" className="grid gap-1.5">
          <input
            className={`${css.input} h-11 px-2.5`}
            aria-label="场景生成关键词"
            value={sceneKeywordInput}
            onChange={(event) =>
              updateSceneGenerationInput(() => setSceneKeywordInput(event.target.value))
            }
            placeholder="输入关键词，例如：赛博校园, 物理实验, 夜间自习, 钟楼广播"
          />
        </label>
      ) : (
        <label key="long-text-mode" className="grid gap-1.5">
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            aria-label="场景生成长文本文件"
            className="min-h-11 w-full border border-border bg-panel px-2 py-1.5 text-xs/[1.5] text-ink"
            onChange={(event) =>
              updateSceneGenerationInput(() =>
                setSceneLongTextFile(event.target.files?.[0] ?? null),
              )
            }
          />
          {sceneLongTextFile ? (
            <span className="text-xs/[1.5] text-muted">{sceneLongTextFile.name}</span>
          ) : null}
        </label>
      )}

      {generatedSceneCandidate ? (
        <div className={css.libraryCard}>
          <strong className="text-[13px] text-ink">
            {generatedSceneCandidate.sceneName}
          </strong>
          <p className="m-0 text-xs/[1.5] text-muted">
            {generatedSceneCandidate.sceneSummary}
          </p>
          <p className="m-0 text-[11px]/[1.4] text-muted">
            {generatedSceneCandidate.mode === "keywords" ? "关键词生成" : "长文本提取"}{" "}
            ·{generatedSceneCandidate.usedModel || "unknown"} ·
            {countSceneNodes(
              generatedSceneCandidate.sceneLayers.map((layer) =>
                normalizeSceneTreeNodeForProfile(layer),
              ),
            )}{" "}
            节点
          </p>
          <SceneProposalPreview
            current={sceneLayers}
            proposed={generatedSceneCandidate.sceneLayers}
          />
          <div className="flex flex-wrap items-center justify-end gap-1">
            <button
              className={css.sidebarButton}
              type="button"
              onClick={(event) =>
                void applyGeneratedSceneCandidateToEditor(event.currentTarget)
              }
              title="应用到编辑区"
              aria-label="应用到编辑区"
            >
              <MaterialIcon name="input" size={14} />
            </button>
          </div>
        </div>
      ) : null}
    </SceneSidebarSection>
  );
}
