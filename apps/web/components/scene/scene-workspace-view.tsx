"use client";

import type { ReactNode } from "react";
import { MaterialIcon } from "../../components/material-icon";
import { ModelFallbackNotice } from "../../components/model-fallback-notice";
import { ProviderTruth } from "../../components/provider-truth";
import {
  type SceneObject,
  normalizeSceneTreeNodeForProfile,
  countSceneNodes,
  canDeleteLayerSafely,
  findLayerById,
} from "../../lib/scene-editor-model";
import { SceneDeleteDialog } from "./scene-delete-dialog";
import { TopNav } from "../../components/top-nav";

import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { SceneLayerCard, RewriteStateButton } from "./scene-tree-components";
import { styles, SCENE_SIDEBAR_WIDTH } from "./scene-workspace-styles";

function formatDate(value: string) {
  if (!value) {
    return "未知时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function SceneWorkspaceView({ controller }: { controller: SceneWorkspaceController }) {
  const {
    savedScenes,
    selectedSavedSceneId,
    setSelectedSavedSceneId,
    libraryError,
    reusableActionPendingId,
    reusableError,
    pageHeadingRef,
    pendingDeleteLayerId,
    reusableSearchQuery,
    setReusableSearchQuery,
    sceneLayers,
    sceneName,
    setSceneName,
    sceneSummary,
    setSceneSummary,
    selectedLayerId,
    selectedObjectId,
    updateSceneGenerationInput,
    selectedLayer,
    sceneNodeCount,
    sceneObjectCount,
    sceneKeywordInput,
    setSceneKeywordInput,
    sceneLongTextFile,
    setSceneLongTextFile,
    sceneGenerateMode,
    setSceneGenerateMode,
    sceneGenerateLayerCount,
    setSceneGenerateLayerCount,
    sceneGeneratePending,
    sceneGenerateError,
    generatedSceneCandidate,
    handleGenerateScene,
    rewriteStrength,
    setRewriteStrength,
    rewritePendingKey,
    rewriteError,
    rewriteModelRecoveries,
    lastRewrite,
    undoLastRewrite,
    rewriteLayerField,
    rewriteObjectField,
    importInputRef,
    collapsedSidebarSections,
    isCompactLayout,
    filteredReusableNodes,
    currentCollapsedNodeEditorSections,
    pageNotice,
    updateLayer,
    saveLayerToReusableLibrary,
    saveObjectToReusableLibrary,
    deleteReusableNode,
    insertReusableNode,
    addChildLayer,
    addObject,
    updateObject,
    removeObject,
    requestDeleteLayer,
    cancelDeleteLayer,
    confirmDeleteLayer,
    saveLibraryScene,
    loadSavedScene,
    deleteSavedScene,
    exportScene,
    requestImportScene,
    importSceneFromFile,
    applyGeneratedSceneCandidateToEditor,
    toggleSidebarSection,
    toggleNodeEditorSection,
    toggleLayerEditor,
    collapsedLayerIds,
    toggleLayerChildren,
    toggleObjectEditor,
    handleSelectLayer,
  } = controller;
  function renderSelectedLayerEditor(): ReactNode {
    if (!selectedLayer) {
      return <p style={styles.emptyState}>选择层级后在这里编辑。</p>;
    }

    return (
      <>
        <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
        {rewriteError ? (
          <div style={styles.rewriteControlRow}>
            <span style={styles.errorText}>{rewriteError}</span>
          </div>
        ) : null}

        <div style={styles.editorSection}>
          <button type="button" style={styles.editorSectionHeader} onClick={() => toggleNodeEditorSection("basic")}> 
            <span style={styles.panelTitle}>基础设定</span>
            <span style={styles.sidebarToggleIcon}><MaterialIcon name={currentCollapsedNodeEditorSections.includes("basic") ? "chevron_right" : "expand_more"} size={16} /></span>
          </button>
          {!currentCollapsedNodeEditorSections.includes("basic") ? (
            <div style={styles.editorSectionBody}>
        <div style={styles.formGrid}>
          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级名称</span>
            <input
              style={styles.input}
              value={selectedLayer.title}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, title: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级作用</span>
            <input
              style={styles.input}
              value={selectedLayer.scopeLabel}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, scopeLabel: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级标签</span>
            <input
              style={styles.input}
              value={selectedLayer.tags}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, tags: event.target.value }))}
              placeholder="用逗号分隔"
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>层级总述</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:summary`}
                label="层级总述"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "summary", "层级总述")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.summary}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, summary: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>氛围与感知</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:atmosphere`}
                label="氛围与感知"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "atmosphere", "氛围与感知")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.atmosphere}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, atmosphere: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>进入方式 / 过渡</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:entrance`}
                label="进入方式 / 过渡"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "entrance", "进入方式 / 过渡")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.entrance}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, entrance: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>层级规则</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:rules`}
                label="层级规则"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "rules", "层级规则")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.rules}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, rules: event.target.value }))}
            />
          </label>

        </div>
            </div>
          ) : null}
        </div>
      </>
    );
  }

  function renderObjectEditor(layerId: string, object: SceneObject): ReactNode {
    return (
      <>
        <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
        {rewriteError ? (
          <div style={styles.rewriteControlRow}>
            <span style={styles.errorText}>{rewriteError}</span>
          </div>
        ) : null}

        <div style={styles.editorSection}>
          <div style={styles.editorSectionBody}>
            <div style={styles.formGrid}>
              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabel}>物体名称</span>
                <input
                  style={styles.input}
                  value={object.name}
                  onChange={(event) => updateObject(layerId, object.id, "name", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabelRow}>
                  <span style={styles.fieldLabel}>外观 / 说明</span>
                  <RewriteStateButton
                    actionKey={`${layerId}:${object.id}:description`}
                    label="物体外观 / 说明"
                    pendingKey={rewritePendingKey}
                    lastRewrite={lastRewrite}
                    rewriteStrength={rewriteStrength}
                    onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                    onRewrite={() => void rewriteObjectField(layerId, object.id, "description", "物体外观与说明")}
                    onUndo={undoLastRewrite}
                  />
                </span>
                <textarea
                  style={styles.textarea}
                  value={object.description}
                  onChange={(event) => updateObject(layerId, object.id, "description", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabelRow}>
                  <span style={styles.fieldLabel}>交互方式</span>
                  <RewriteStateButton
                    actionKey={`${layerId}:${object.id}:interaction`}
                    label="物体交互方式"
                    pendingKey={rewritePendingKey}
                    lastRewrite={lastRewrite}
                    rewriteStrength={rewriteStrength}
                    onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                    onRewrite={() => void rewriteObjectField(layerId, object.id, "interaction", "物体交互方式")}
                    onUndo={undoLastRewrite}
                  />
                </span>
                <textarea
                  style={styles.textarea}
                  value={object.interaction}
                  onChange={(event) => updateObject(layerId, object.id, "interaction", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabel}>标签</span>
                <input
                  style={styles.input}
                  value={object.tags}
                  onChange={(event) => updateObject(layerId, object.id, "tags", event.target.value)}
                  placeholder="用逗号分隔"
                />
              </label>

            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/scene-setup" />

      <div style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 ref={pageHeadingRef} tabIndex={-1} style={styles.pageTitle}>场景搭建</h1>
          <ProviderTruth scope="scene" />
          <div style={styles.notice} role="status" aria-live="polite">{pageNotice}</div>
          {libraryError ? <p role="alert" style={styles.errorText}>部分场景库数据未能读取，请刷新页面重试。</p> : null}
        </div>
      </div>

      <div
        style={{
          ...styles.workspaceShell,
          ...(isCompactLayout ? styles.workspaceShellCompact : null),
        }}
      >
        {/* ── Panel 1: Scene Tree + Node Editor ── */}
        <div
          style={{
            ...styles.panel,
            ...(isCompactLayout ? styles.panelCompact : null),
            flex: 1,
            minWidth: 0,
          }}
        >
          <div style={styles.panelHeader}>
            <span style={styles.panelTitle}>场景树与节点编辑器</span>
            <div style={styles.panelHeaderActions}>
              <button
                style={selectedSavedSceneId ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
                type="button"
                onClick={() => void saveLibraryScene("upsert")}
                title={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
                aria-label={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
              >
                <MaterialIcon name="save" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={() => void saveLibraryScene("create")}
                title="另存为新场景"
                aria-label="另存为新场景"
              >
                <MaterialIcon name="library_add" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={requestImportScene}
                title="导入 JSON"
                aria-label="导入 JSON"
              >
                <MaterialIcon name="upload_file" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={exportScene}
                title="导出 JSON"
                aria-label="导出 JSON"
              >
                <MaterialIcon name="download" size={14} />
              </button>
            </div>
          </div>
          <div style={{ ...styles.panelBody, ...(isCompactLayout ? styles.panelBodyCompact : null) }}>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            style={styles.hiddenInput}
            onChange={(event) => void importSceneFromFile(event)}
          />
          <div style={styles.treeStack}>
            {sceneLayers.map((layer, index) => (
              <SceneLayerCard
                key={layer.id}
                layer={layer}
                index={index}
                collapsedLayerIds={collapsedLayerIds}
                onToggleChildren={toggleLayerChildren}
                selectedLayerId={selectedLayerId}
                selectedObjectId={selectedObjectId}
                onSelect={handleSelectLayer}
                onToggleEditor={toggleLayerEditor}
                onAddChild={addChildLayer}
                onAddObject={addObject}
                onSaveToReusable={(layerId) => { void saveLayerToReusableLibrary(layerId); }}
                onSelectObject={toggleObjectEditor}
                onSaveObjectToReusable={(object) => { void saveObjectToReusableLibrary(object); }}
                onRemoveObject={removeObject}
                reusableActionPendingId={reusableActionPendingId}
                onRequestDelete={requestDeleteLayer}
                canDeleteLayerForId={(layerId) => canDeleteLayerSafely(sceneLayers, layerId)}
                editorContent={renderSelectedLayerEditor()}
                renderObjectEditor={renderObjectEditor}
              />
            ))}
          </div>
          </div>
        </div>

        {/* ── Panel 3: Sidebar ── */}
        <aside
          style={{
            ...styles.sidebarPane,
            ...(isCompactLayout ? styles.sidebarPaneCompact : null),
            width: isCompactLayout ? "100%" : SCENE_SIDEBAR_WIDTH,
            flexShrink: 0,
          }}
        >
          <div style={styles.sidebarSection}>
            <div style={styles.sidebarSectionStaticHeader}>
              <span style={styles.panelTitle}>当前场景</span>
              <span style={styles.sidebarSectionMeta}>
                {sceneNodeCount} 节点 · {sceneObjectCount} 物体
              </span>
            </div>
            <div style={{ ...styles.sidebarSectionBody, ...styles.sceneMetaSectionBody }}>
              <label style={styles.sceneNameLabel}>
                <span style={styles.fieldLabel}>场景名称</span>
                <input
                  style={styles.sceneNameInput}
                  value={sceneName}
                  onChange={(event) => updateSceneGenerationInput(() => setSceneName(event.target.value))}
                  placeholder="例如：高一物理-力学基础"
                />
              </label>
              <label style={styles.sceneSummaryLabel}>
                <span style={styles.fieldLabel}>场景摘要</span>
                <textarea
                  style={styles.sceneSummaryInput}
                  value={sceneSummary}
                  onChange={(event) => updateSceneGenerationInput(() => setSceneSummary(event.target.value))}
                  placeholder="用自己的话描述这个场景。"
                />
              </label>
            </div>
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} aria-expanded={!collapsedSidebarSections.includes("generate")} onClick={() => toggleSidebarSection("generate")}>
              <span style={styles.panelTitle}>场景树生成器</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("generate") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("generate") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>层级偏好（可选）</span>
                  <input
                    style={styles.input}
                    type="number"
                    min={1}
                    step={1}
                    value={sceneGenerateLayerCount}
                    onChange={(event) => updateSceneGenerationInput(() => setSceneGenerateLayerCount(event.target.value))}
                    placeholder="留空表示不限"
                  />
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={sceneGenerateMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updateSceneGenerationInput(() => setSceneGenerateMode("keywords"))}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={sceneGenerateMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updateSceneGenerationInput(() => setSceneGenerateMode("long_text"))}
                    >
                      长文本提取
                    </button>
                  </div>
                  <button
                    style={styles.sidebarIconButton}
                    type="button"
                    disabled={sceneGeneratePending !== null}
                    onClick={() => void handleGenerateScene(sceneGenerateMode)}
                    title={
                      sceneGenerateMode === "keywords"
                        ? (sceneGeneratePending === "keywords" ? "生成中" : "根据关键词生成场景树")
                        : (sceneGeneratePending === "long_text" ? "提取中" : "根据长文本提取场景树")
                    }
                    aria-label={
                      sceneGenerateMode === "keywords"
                        ? (sceneGeneratePending === "keywords" ? "生成中" : "根据关键词生成场景树")
                        : (sceneGeneratePending === "long_text" ? "提取中" : "根据长文本提取场景树")
                    }
                  >
                    <MaterialIcon
                      name={
                        sceneGenerateMode === "keywords"
                          ? (sceneGeneratePending === "keywords" ? "hourglass_top" : "auto_awesome")
                          : (sceneGeneratePending === "long_text" ? "hourglass_top" : "description")
                      }
                      size={14}
                    />
                  </button>
                </div>
                {sceneGenerateMode === "keywords" ? (
                  <label key="keywords-mode" style={styles.fieldGroup}>
                    <input
                      style={styles.input}
                      value={sceneKeywordInput}
                      onChange={(event) => updateSceneGenerationInput(() => setSceneKeywordInput(event.target.value))}
                      placeholder="输入关键词，例如：赛博校园, 物理实验, 夜间自习, 钟楼广播"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => updateSceneGenerationInput(() => setSceneLongTextFile(event.target.files?.[0] ?? null))}
                    />
                    {sceneLongTextFile ? <span style={styles.helperText}>{sceneLongTextFile.name}</span> : null}
                  </label>
                )}
                {sceneGenerateError ? <p style={styles.errorText}>{sceneGenerateError}</p> : null}
                {generatedSceneCandidate ? (
                  <div style={styles.generatedSceneCard}>
                    <strong style={styles.generatedSceneTitle}>{generatedSceneCandidate.sceneName}</strong>
                    <p style={styles.generatedSceneSummary}>{generatedSceneCandidate.sceneSummary}</p>
                    <p style={styles.generatedSceneMeta}>
                      {generatedSceneCandidate.mode === "keywords" ? "关键词生成" : "长文本提取"} ·
                      {generatedSceneCandidate.usedModel || "unknown"} ·
                      {countSceneNodes(generatedSceneCandidate.sceneLayers.map((layer) => normalizeSceneTreeNodeForProfile(layer)))} 节点
                    </p>
                    <div style={styles.sidebarActionRow}>
                      <button
                        style={styles.sidebarIconButton}
                        type="button"
                        onClick={applyGeneratedSceneCandidateToEditor}
                        title="应用到编辑区"
                        aria-label="应用到编辑区"
                      >
                        <MaterialIcon name="input" size={14} />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} aria-expanded={!collapsedSidebarSections.includes("reuse")} onClick={() => toggleSidebarSection("reuse")}>
              <span style={styles.panelTitle}>可复用节点库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("reuse") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("reuse") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>搜索节点</span>
                  <input
                    style={styles.input}
                    value={reusableSearchQuery}
                    onChange={(event) => setReusableSearchQuery(event.target.value)}
                    placeholder="搜索标题、标签、复用说明"
                  />
                </label>
                {reusableError ? <p style={styles.errorText}>{reusableError}</p> : null}
                <div style={styles.reusableNodeList}>
                  {filteredReusableNodes.length ? filteredReusableNodes.map((item) => (
                    <article key={item.nodeId} style={styles.reusableNodeCard}>
                      <div style={styles.savedSceneTitleRow}>
                        <strong style={styles.savedSceneTitle}>{item.title}</strong>
                        <span style={styles.savedSceneMeta}>{item.nodeType === "layer" ? "层级" : "物体"}</span>
                      </div>
                      {item.summary ? <p style={styles.savedSceneSummary}>{item.summary}</p> : null}
                      <p style={styles.savedSceneMeta}>{item.reuseHint || "未填写复用说明"}</p>
                      <p style={styles.savedSceneMeta}>
                        {(item.tags.length ? item.tags.join(" · ") : "无标签")}
                        {item.sourceSceneName ? ` · 来自 ${item.sourceSceneName}` : ""}
                      </p>
                      <div style={styles.sidebarCardActions}>
                        <button
                          style={styles.sidebarIconButton}
                          type="button"
                          onClick={() => insertReusableNode(item)}
                          title="插入到当前层级"
                          aria-label="插入到当前层级"
                        >
                          <MaterialIcon name="input" size={14} />
                        </button>
                        <button
                          style={styles.sidebarIconButton}
                          type="button"
                          disabled={reusableActionPendingId === item.nodeId}
                          onClick={() => void deleteReusableNode(item.nodeId)}
                          title={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                          aria-label={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                        >
                          <MaterialIcon name={reusableActionPendingId === item.nodeId ? "hourglass_top" : "delete"} size={14} />
                        </button>
                      </div>
                    </article>
                  )) : (
                    <p style={styles.sidebarHint}>节点库还是空的。</p>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} aria-expanded={!collapsedSidebarSections.includes("saved")} onClick={() => toggleSidebarSection("saved")}>
              <span style={styles.panelTitle}>已保存场景</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("saved") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("saved") ? (
              <div style={styles.sidebarSectionBody}>
                {savedScenes.length ? (
                  <div style={styles.savedSceneList}>
                    {savedScenes.map((item) => {
                      const isSelected = selectedSavedSceneId === item.sceneId;
                      return (
                        <div key={item.sceneId} style={{ ...styles.savedSceneItem, ...(isSelected ? styles.savedSceneItemSelected : {}) }}>
                          <button
                            type="button"
                            style={styles.savedSceneBody}
                            onClick={() => setSelectedSavedSceneId(item.sceneId)}
                          >
                            <div style={styles.savedSceneTitleRow}>
                              <strong style={styles.savedSceneTitle}>{item.sceneName}</strong>
                              <span style={styles.savedSceneMeta}>{formatDate(item.updatedAt)}</span>
                            </div>
                            <p style={styles.savedSceneSummary}>{item.sceneSummary || "未填写 summary"}</p>
                            <p style={styles.savedSceneMeta}>{item.sceneProfile?.title ?? "未生成快照"} · {countSceneNodes(item.sceneProfile?.sceneTree ?? [])} 节点</p>
                          </button>
                          <div style={styles.sidebarCardActions}>
                            <button
                              style={styles.sidebarIconButton}
                              type="button"
                              onClick={() => void loadSavedScene(item.sceneId)}
                              title="载入场景"
                              aria-label="载入场景"
                            >
                              <MaterialIcon name="file_open" size={14} />
                            </button>
                            <button
                              style={isSelected ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
                              type="button"
                              onClick={() => setSelectedSavedSceneId(item.sceneId)}
                              title={isSelected ? "当前更新目标" : "作为更新目标"}
                              aria-label={isSelected ? "当前更新目标" : "作为更新目标"}
                            >
                              <MaterialIcon name="check_circle" size={14} />
                            </button>
                            <button
                              style={styles.sidebarIconButton}
                              type="button"
                              onClick={() => void deleteSavedScene(item.sceneId)}
                              title="删除已保存场景"
                              aria-label="删除已保存场景"
                            >
                              <MaterialIcon name="delete" size={14} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </aside>
      </div>

      {pendingDeleteLayerId ? (
        <SceneDeleteDialog
          layerName={findLayerById(sceneLayers, pendingDeleteLayerId)?.title ?? "当前层级"}
          onCancel={cancelDeleteLayer}
          onConfirm={confirmDeleteLayer}
          fallbackFocus={pageHeadingRef}
        />
      ) : null}

    </main>
  );
}
