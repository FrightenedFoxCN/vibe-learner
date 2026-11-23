import { useState } from "react";
import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { formatTimestamp } from "../../lib/format";
import { countSceneNodes } from "../../lib/scene-editor-model";
import { MaterialIcon } from "../ui/material-icon";
import { SceneSidebarSection } from "./scene-sidebar-section";
import css from "./scene-workspace.module.css";

export function ReusableNodeLibrary({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    collapsedSidebarSections,
    toggleSidebarSection,
    reusableSearchQuery,
    setReusableSearchQuery,
    filteredReusableNodes,
    insertReusableNode,
    deleteReusableNode,
    reusableActionPendingId,
  } = controller;
  const [nodeType, setNodeType] = useState("");
  const visibleNodes = filteredReusableNodes.filter(
    (item) => !nodeType || item.nodeType === nodeType,
  );
  return (
    <SceneSidebarSection
      title="可复用节点库"
      collapsed={collapsedSidebarSections.includes("reuse")}
      onToggle={() => toggleSidebarSection("reuse")}
    >
      <label className="grid gap-1.5">
        <span className={css.fieldLabel}>搜索节点</span>
        <input
          className={`${css.input} h-11 px-2.5`}
          value={reusableSearchQuery}
          onChange={(event) => setReusableSearchQuery(event.target.value)}
          placeholder="搜索标题、标签、复用说明"
        />
      </label>

      <select
        className="min-h-11 max-w-full border border-border bg-bg px-2.5 py-2 text-ink"
        aria-label="筛选节点类型"
        value={nodeType}
        onChange={(event) => setNodeType(event.target.value)}
      >
        <option value="">全部节点</option>
        <option value="layer">层级</option>
        <option value="object">物体</option>
      </select>
      <p role="status" className="m-0 text-xs/[1.6] text-muted">
        {visibleNodes.length} 个节点
      </p>
      <div className="grid max-h-80 gap-2 overflow-y-auto">
        {visibleNodes.length ? (
          visibleNodes.map((item) => (
            <article key={item.nodeId} className={css.libraryCard}>
              <div className="flex items-baseline justify-between gap-2.5">
                <strong className="text-[13px] text-ink">{item.title}</strong>
                <span className="m-0 text-[11px]/[1.4] text-muted">
                  {item.nodeType === "layer" ? "层级" : "物体"}
                </span>
              </div>
              {item.summary ? (
                <p className="m-0 text-xs/[1.5] text-muted">{item.summary}</p>
              ) : null}
              <p className="m-0 text-[11px]/[1.4] text-muted">
                {item.reuseHint || "未填写复用说明"}
              </p>
              <p className="m-0 text-[11px]/[1.4] text-muted">
                {item.tags.length ? item.tags.join(" · ") : "无标签"}
                {item.sourceSceneName ? ` · 来自 ${item.sourceSceneName}` : ""}
              </p>
              <div className="flex items-center justify-end gap-1">
                <button
                  className={css.sidebarButton}
                  type="button"
                  onClick={() => insertReusableNode(item)}
                  title="插入到当前层级"
                  aria-label="插入到当前层级"
                >
                  <MaterialIcon name="input" size={14} />
                </button>
                <details className="mt-2 border-t border-border pt-1">
                  <summary className="min-h-8 cursor-pointer py-1.5 text-xs/[1.5] text-muted">
                    删除操作
                  </summary>
                  <button
                    className={css.sidebarButton}
                    type="button"
                    disabled={reusableActionPendingId === item.nodeId}
                    onClick={() => void deleteReusableNode(item.nodeId)}
                    title={
                      reusableActionPendingId === item.nodeId
                        ? "删除中"
                        : "删除复用节点"
                    }
                    aria-label={
                      reusableActionPendingId === item.nodeId
                        ? "删除中"
                        : "删除复用节点"
                    }
                  >
                    <MaterialIcon
                      name={
                        reusableActionPendingId === item.nodeId
                          ? "hourglass_top"
                          : "delete"
                      }
                      size={14}
                    />
                  </button>
                </details>
              </div>
            </article>
          ))
        ) : (
          <p className="m-0 text-xs/[1.6] text-muted">
            没有匹配的节点，请调整搜索或筛选。
          </p>
        )}
      </div>
    </SceneSidebarSection>
  );
}

export function SavedSceneLibrary({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    collapsedSidebarSections,
    toggleSidebarSection,
    savedScenes,
    selectedSavedSceneId,
    setSelectedSavedSceneId,
    loadSavedScene,
    deleteSavedScene,
  } = controller;
  const [savedQuery, setSavedQuery] = useState("");
  const visibleScenes = savedScenes.filter((item) =>
    [item.sceneName, item.sceneSummary]
      .join(" ")
      .toLocaleLowerCase()
      .includes(savedQuery.trim().toLocaleLowerCase()),
  );
  return (
    <SceneSidebarSection
      title="已保存场景"
      collapsed={collapsedSidebarSections.includes("saved")}
      onToggle={() => toggleSidebarSection("saved")}
    >
      <input
        type="search"
        className={`${css.input} h-11 px-2.5`}
        aria-label="搜索已保存场景"
        value={savedQuery}
        onChange={(event) => setSavedQuery(event.target.value)}
        placeholder="搜索场景名称或摘要"
      />
      <p role="status" className="m-0 text-xs/[1.6] text-muted">
        {visibleScenes.length} 个场景
      </p>
      {!visibleScenes.length ? (
        <p className="m-0 text-xs/[1.6] text-muted">没有匹配的场景。</p>
      ) : null}
      {visibleScenes.length ? (
        <div className="grid w-full content-start items-start justify-start gap-1.5 self-start">
          {visibleScenes.map((item) => {
            const isSelected = selectedSavedSceneId === item.sceneId;
            return (
              <div
                key={item.sceneId}
                className={`${css.libraryCard} w-full`}
                data-selected={isSelected}
              >
                <button
                  type="button"
                  className="grid min-h-11 cursor-pointer gap-1 border-0 bg-transparent p-0 text-left"
                  onClick={() => setSelectedSavedSceneId(item.sceneId)}
                >
                  <div className="flex items-baseline justify-between gap-2.5">
                    <strong className="text-[13px] text-ink">{item.sceneName}</strong>
                    <span className="m-0 text-[11px]/[1.4] text-muted">
                      {formatTimestamp(item.updatedAt, { style: "short" })}
                    </span>
                  </div>
                  <p className="m-0 text-xs/[1.5] text-muted">
                    {item.sceneSummary || "未填写 summary"}
                  </p>
                  <p className="m-0 text-[11px]/[1.4] text-muted">
                    {item.sceneProfile?.title ?? "未生成快照"} ·{" "}
                    {countSceneNodes(item.sceneProfile?.sceneTree ?? [])} 节点
                  </p>
                </button>
                <div className="flex items-center justify-end gap-1">
                  <button
                    className={css.sidebarButton}
                    type="button"
                    onClick={() => void loadSavedScene(item.sceneId)}
                    title="载入场景"
                    aria-label="载入场景"
                  >
                    <MaterialIcon name="file_open" size={14} />
                  </button>
                  <button
                    className={css.sidebarButton}
                    data-primary={isSelected}
                    type="button"
                    onClick={() => setSelectedSavedSceneId(item.sceneId)}
                    title={isSelected ? "当前更新目标" : "作为更新目标"}
                    aria-label={isSelected ? "当前更新目标" : "作为更新目标"}
                  >
                    <MaterialIcon name="check_circle" size={14} />
                  </button>
                  <details className="mt-2 border-t border-border pt-1">
                    <summary className="min-h-8 cursor-pointer py-1.5 text-xs/[1.5] text-muted">
                      删除操作
                    </summary>
                    <button
                      className={css.sidebarButton}
                      type="button"
                      onClick={(event) =>
                        void deleteSavedScene(item.sceneId, event.currentTarget)
                      }
                      title="删除已保存场景"
                      aria-label="删除已保存场景"
                    >
                      <MaterialIcon name="delete" size={14} />
                    </button>
                  </details>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </SceneSidebarSection>
  );
}
