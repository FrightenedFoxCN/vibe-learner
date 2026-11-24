import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { canDeleteLayerSafely } from "../../lib/scene-editor-model";
import { MaterialIcon } from "../ui/material-icon";
import { SceneLayerEditor, SceneObjectEditor } from "./scene-node-editors";
import { SceneLayerCard } from "./scene-tree-components";
import css from "./scene-workspace.module.css";

export function SceneTreePanel({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    selectedSavedSceneId,
    reusableActionPendingId,
    sceneLayers,
    selectedLayerId,
    selectedObjectId,
    importInputRef,
    isCompactLayout,
    saveLayerToReusableLibrary,
    saveObjectToReusableLibrary,
    addChildLayer,
    addObject,
    removeObject,
    requestDeleteLayer,
    saveLibraryScene,
    exportScene,
    requestImportScene,
    importSceneFromFile,
    toggleLayerEditor,
    collapsedLayerIds,
    toggleLayerChildren,
    toggleObjectEditor,
    handleSelectLayer,
  } = controller;
  return (
    <div
      className={`${css.panelSurface} flex min-h-0 min-w-0 flex-col border border-border ${isCompactLayout ? "flex-none overflow-visible" : "flex-1 overflow-hidden"}`}
    >
      <div
        className={`${css.sectionDivider} relative flex min-h-10 shrink-0 flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5`}
      >
        <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
          场景树与节点编辑器
        </span>
        <div className="inline-flex flex-wrap items-center gap-2">
          <button
            className={css.toolbarButton}
            data-primary="true"
            type="button"
            onClick={() => void saveLibraryScene("upsert")}
            title={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
            aria-label={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
          >
            <MaterialIcon name="save" size={15} />
            <span>{selectedSavedSceneId ? "更新" : "保存"}</span>
          </button>
          <button
            className={css.toolbarButton}
            type="button"
            onClick={() => void saveLibraryScene("create")}
            title="另存为新场景"
            aria-label="另存为新场景"
          >
            <MaterialIcon name="library_add" size={15} />
            <span>另存</span>
          </button>
          <button
            className={css.toolbarButton}
            type="button"
            onClick={requestImportScene}
            title="导入 JSON"
            aria-label="导入 JSON"
          >
            <MaterialIcon name="upload_file" size={15} />
            <span>导入</span>
          </button>
          <button
            className={css.toolbarButton}
            type="button"
            onClick={exportScene}
            title="导出 JSON"
            aria-label="导出 JSON"
          >
            <MaterialIcon name="download" size={15} />
            <span>导出</span>
          </button>
        </div>
      </div>
      <div
        className={`grid min-h-0 flex-1 content-start gap-3.5 px-[18px] pt-4 pb-[18px] ${isCompactLayout ? "overflow-visible" : "overflow-y-auto"}`}
      >
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          aria-label="导入场景 JSON 文件"
          className="hidden"
          onChange={(event) => void importSceneFromFile(event)}
        />
        <div className="grid gap-2">
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
              onSaveToReusable={(layerId) => {
                void saveLayerToReusableLibrary(layerId);
              }}
              onSelectObject={toggleObjectEditor}
              onSaveObjectToReusable={(object) => {
                void saveObjectToReusableLibrary(object);
              }}
              onRemoveObject={removeObject}
              reusableActionPendingId={reusableActionPendingId}
              onRequestDelete={requestDeleteLayer}
              canDeleteLayerForId={(layerId) =>
                canDeleteLayerSafely(sceneLayers, layerId)
              }
              editorContent={<SceneLayerEditor controller={controller} />}
              renderObjectEditor={(layerId, object) => (
                <SceneObjectEditor
                  controller={controller}
                  layerId={layerId}
                  object={object}
                />
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
