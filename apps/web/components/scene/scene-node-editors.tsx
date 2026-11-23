import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import type { SceneObject } from "../../lib/scene-editor-model";
import { MaterialIcon } from "../ui/material-icon";
import { ModelFallbackNotice } from "../ui/model-fallback-notice";
import { RewriteStateButton } from "./scene-tree-components";
import css from "./scene-workspace.module.css";

const layerTextFields = [
  ["title", "层级名称"],
  ["scopeLabel", "层级作用"],
  ["tags", "层级标签"],
] as const;

const layerRewriteFields = [
  ["summary", "层级总述"],
  ["atmosphere", "氛围与感知"],
  ["entrance", "进入方式 / 过渡"],
  ["rules", "层级规则"],
] as const;

const objectRewriteFields = [
  ["description", "外观 / 说明", "物体外观 / 说明", "物体外观与说明"],
  ["interaction", "交互方式", "物体交互方式", "物体交互方式"],
] as const;

export function SceneLayerEditor({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    selectedLayer,
    updateLayer,
    rewriteLayerField,
    rewriteModelRecoveries,
    currentCollapsedNodeEditorSections,
    toggleNodeEditorSection,
  } = controller;
  if (!selectedLayer) {
    return (
      <p className="m-0 py-5 text-[13px]/[1.7] text-muted">选择层级后在这里编辑。</p>
    );
  }
  const collapsed = currentCollapsedNodeEditorSections.includes("basic");

  return (
    <>
      <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
      <div className={`${css.editorSection} grid overflow-hidden border`}>
        <button
          type="button"
          className="flex min-h-11 w-full cursor-pointer items-center justify-between border-0 bg-transparent px-2.5 py-[9px] text-left"
          aria-expanded={!collapsed}
          onClick={() => toggleNodeEditorSection("basic")}
        >
          <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
            基础设定
          </span>
          <span className="inline-flex items-center justify-center text-muted">
            <MaterialIcon
              name={collapsed ? "chevron_right" : "expand_more"}
              size={16}
            />
          </span>
        </button>
        {!collapsed ? (
          <div className="grid gap-2.5 px-2.5 pb-2.5">
            <div className="grid gap-3">
              {layerTextFields.map(([field, label]) => (
                <label key={field} className="grid gap-1.5">
                  <span className={css.fieldLabel}>{label}</span>
                  <input
                    className={`${css.input} h-11 px-2.5`}
                    value={selectedLayer[field]}
                    onChange={(event) =>
                      updateLayer(selectedLayer.id, (layer) => ({
                        ...layer,
                        [field]: event.target.value,
                      }))
                    }
                    placeholder={field === "tags" ? "用逗号分隔" : undefined}
                  />
                </label>
              ))}
              {layerRewriteFields.map(([field, label]) => (
                <SceneRewriteField
                  key={field}
                  controller={controller}
                  id={`scene-layer-${selectedLayer.id}-${field}`}
                  actionKey={`${selectedLayer.id}:${field}`}
                  label={label}
                  rewriteLabel={label}
                  value={selectedLayer[field]}
                  onChange={(value) =>
                    updateLayer(selectedLayer.id, (layer) => ({
                      ...layer,
                      [field]: value,
                    }))
                  }
                  onRewrite={() =>
                    void rewriteLayerField(selectedLayer.id, field, label)
                  }
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

export function SceneObjectEditor({
  controller,
  layerId,
  object,
}: {
  controller: SceneWorkspaceController;
  layerId: string;
  object: SceneObject;
}) {
  const { rewriteModelRecoveries, rewriteObjectField, updateObject } = controller;

  return (
    <>
      <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
      <div className={`${css.editorSection} grid overflow-hidden border`}>
        <div className="grid gap-2.5 px-2.5 pb-2.5">
          <div className="grid gap-3">
            <label className="grid gap-1.5">
              <span className={css.fieldLabel}>物体名称</span>
              <input
                className={`${css.input} h-11 px-2.5`}
                value={object.name}
                onChange={(event) =>
                  updateObject(layerId, object.id, "name", event.target.value)
                }
              />
            </label>
            {objectRewriteFields.map(([field, label, rewriteLabel, operationLabel]) => (
              <SceneRewriteField
                key={field}
                controller={controller}
                id={`scene-object-${layerId}-${object.id}-${field}`}
                actionKey={`${layerId}:${object.id}:${field}`}
                label={label}
                rewriteLabel={rewriteLabel}
                value={object[field]}
                onChange={(value) => updateObject(layerId, object.id, field, value)}
                onRewrite={() =>
                  void rewriteObjectField(layerId, object.id, field, operationLabel)
                }
              />
            ))}
            <label className="grid gap-1.5">
              <span className={css.fieldLabel}>标签</span>
              <input
                className={`${css.input} h-11 px-2.5`}
                value={object.tags}
                onChange={(event) =>
                  updateObject(layerId, object.id, "tags", event.target.value)
                }
                placeholder="用逗号分隔"
              />
            </label>
          </div>
        </div>
      </div>
    </>
  );
}

function SceneRewriteField({
  controller,
  id,
  actionKey,
  label,
  rewriteLabel,
  value,
  onChange,
  onRewrite,
}: {
  controller: SceneWorkspaceController;
  id: string;
  actionKey: string;
  label: string;
  rewriteLabel: string;
  value: string;
  onChange: (value: string) => void;
  onRewrite: () => void;
}) {
  const {
    rewritePendingKey,
    lastRewrite,
    rewriteStrength,
    updateSceneGenerationInput,
    setRewriteStrength,
    undoLastRewrite,
  } = controller;
  return (
    <label htmlFor={id} className="grid gap-1.5">
      <span className="flex items-center justify-between gap-2">
        <span className={css.fieldLabel}>{label}</span>
        <RewriteStateButton
          actionKey={actionKey}
          label={rewriteLabel}
          pendingKey={rewritePendingKey}
          lastRewrite={lastRewrite}
          rewriteStrength={rewriteStrength}
          onRewriteStrengthChange={(next) =>
            updateSceneGenerationInput(() => setRewriteStrength(next))
          }
          onRewrite={onRewrite}
          onUndo={undoLastRewrite}
        />
      </span>
      <textarea
        className={`${css.input} min-h-18 resize-y px-2.5 py-2 leading-[1.6]`}
        id={id}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
