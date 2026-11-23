"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { MaterialIcon, type MaterialIconName } from "../ui/material-icon";
import { type SceneObject, type SceneLayer } from "../../lib/scene-editor-model";
import { type RewriteUndoEntry } from "../../hooks/use-scene-rewrite";

import css from "./scene-workspace.module.css";

export function SceneLayerCard({
  layer,
  index,
  selectedLayerId,
  selectedObjectId,
  collapsedLayerIds = [],
  onToggleChildren,
  onSelect,
  onToggleEditor,
  onAddChild,
  onAddObject,
  onSaveToReusable,
  onSelectObject,
  onSaveObjectToReusable,
  onRemoveObject,
  reusableActionPendingId,
  onRequestDelete,
  canDeleteLayerForId,
  editorContent,
  renderObjectEditor,
}: {
  layer: SceneLayer;
  index: number;
  selectedLayerId: string;
  selectedObjectId: string;
  collapsedLayerIds?: string[];
  onToggleChildren?: (layerId: string) => void;
  onSelect: (layerId: string) => void;
  onToggleEditor: (layerId: string) => void;
  onAddChild: (layerId: string) => void;
  onAddObject: (layerId: string) => void;
  onSaveToReusable: (layerId: string) => void;
  onSelectObject: (objectId: string) => void;
  onSaveObjectToReusable: (object: SceneObject) => void;
  onRemoveObject: (layerId: string, objectId: string) => void;
  reusableActionPendingId: string;
  onRequestDelete: (layerId: string, trigger: HTMLButtonElement) => void;
  canDeleteLayerForId: (layerId: string) => boolean;
  editorContent: ReactNode;
  renderObjectEditor: (layerId: string, object: SceneObject) => ReactNode;
}) {
  const isSelected = layer.id === selectedLayerId;
  const isCollapsed = collapsedLayerIds.includes(layer.id);
  const hasChildren = layer.children.length > 0;
  const hasObjects = layer.objects.length > 0;
  const stopCardAction =
    (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      handler();
    };
  return (
    <div className="grid gap-1.5">
      <article
        className={`${css.layerCard} grid cursor-pointer gap-2 p-3`}
        data-selected={isSelected}
        onClick={() => onSelect(layer.id)}
      >
        <div className="flex items-start gap-2">
          <div className="grid size-[22px] shrink-0 place-items-center bg-accent text-[10px] font-extrabold tracking-[0.06em] text-white">
            {String(index + 1).padStart(2, "0")}
          </div>
          <div className="grid min-w-0 gap-0.5">
            <span className="text-[10px] font-semibold tracking-[0.07em] text-muted uppercase">
              {layer.scopeLabel}
            </span>
            <h2 className="m-0 text-[13px]/[1.2] font-semibold text-ink">
              {layer.title}
            </h2>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p className="m-0 text-xs/[1.5] text-muted">{layer.summary}</p>

            <div className="flex flex-wrap gap-1">
              {layer.tags
                .split(",")
                .map((tag) => tag.trim())
                .filter(Boolean)
                .slice(0, 2)
                .map((tag) => (
                  <span
                    key={`${layer.id}:${tag}`}
                    className="border border-accent-soft bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent"
                  >
                    #{tag}
                  </span>
                ))}
              {layer.objects.slice(0, 3).map((object) => (
                <span
                  key={object.id}
                  className="border border-border bg-bg px-1.5 py-0.5 text-[10px] text-muted"
                >
                  {object.name}
                </span>
              ))}
              {layer.objects.length > 3 ? (
                <span className="border border-border bg-bg px-1.5 py-0.5 text-[10px] text-muted">
                  +{layer.objects.length - 3}
                </span>
              ) : null}
            </div>
          </>
        ) : null}

        <div className="flex flex-wrap gap-1">
          {(hasChildren || hasObjects) && onToggleChildren ? (
            <button
              type="button"
              aria-expanded={!isCollapsed}
              aria-label={`${isCollapsed ? "展开" : "收起"}${layer.title}的子层和物体`}
              className={css.treeButton}
              onClick={stopCardAction(() => onToggleChildren(layer.id))}
            >
              <MaterialIcon
                name={isCollapsed ? "chevron_right" : "expand_more"}
                size={18}
              />
            </button>
          ) : null}
          <SceneIconButton
            icon="add_circle"
            label="添加子层"
            size="micro"
            variant="accent"
            onClick={stopCardAction(() => onAddChild(layer.id))}
          />
          <SceneIconButton
            icon="category"
            label="添加物体"
            size="micro"
            onClick={stopCardAction(() => onAddObject(layer.id))}
          />
          <SceneIconButton
            icon={
              reusableActionPendingId === layer.id
                ? "hourglass_top"
                : "create_new_folder"
            }
            label="加入节点库"
            size="micro"
            onClick={stopCardAction(() => onSaveToReusable(layer.id))}
            disabled={reusableActionPendingId === layer.id}
          />
          <SceneIconButton
            icon="delete"
            label="删除当前层级"
            size="micro"
            variant="danger"
            onClick={(event) => {
              event.stopPropagation();
              onRequestDelete(layer.id, event.currentTarget);
            }}
            disabled={!canDeleteLayerForId(layer.id)}
          />
          <SceneIconButton
            icon={isSelected ? "expand_more" : "chevron_right"}
            label={isSelected ? "收起节点编辑器" : "展开节点编辑器"}
            expanded={isSelected}
            controls={isSelected ? `scene-node-editor-${layer.id}` : undefined}
            size="micro"
            onClick={stopCardAction(() => onToggleEditor(layer.id))}
          />
        </div>
      </article>

      {isSelected ? (
        <div
          id={`scene-node-editor-${layer.id}`}
          className={`${css.inlineEditor} mt-1.5 grid content-start gap-3 border-t pt-3.5`}
        >
          {editorContent}
        </div>
      ) : null}

      {(hasObjects || hasChildren) && !isCollapsed ? (
        <div className="grid gap-1.5 border-l-2 border-border pl-3">
          {layer.objects.map((object) => (
            <SceneObjectCard
              key={object.id}
              object={object}
              layerId={layer.id}
              selectedObjectId={selectedObjectId}
              onSelect={onSelectObject}
              onSaveToReusable={onSaveObjectToReusable}
              onRemove={onRemoveObject}
              reusableActionPendingId={reusableActionPendingId}
              editorContent={renderObjectEditor(layer.id, object)}
            />
          ))}
          {layer.children.map((child, childIndex) => (
            <SceneLayerCard
              key={child.id}
              layer={child}
              index={childIndex}
              collapsedLayerIds={collapsedLayerIds}
              onToggleChildren={onToggleChildren}
              selectedLayerId={selectedLayerId}
              selectedObjectId={selectedObjectId}
              onSelect={onSelect}
              onToggleEditor={onToggleEditor}
              onAddChild={onAddChild}
              onAddObject={onAddObject}
              onSaveToReusable={onSaveToReusable}
              onSelectObject={onSelectObject}
              onSaveObjectToReusable={onSaveObjectToReusable}
              onRemoveObject={onRemoveObject}
              reusableActionPendingId={reusableActionPendingId}
              onRequestDelete={onRequestDelete}
              canDeleteLayerForId={canDeleteLayerForId}
              editorContent={editorContent}
              renderObjectEditor={renderObjectEditor}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function SceneObjectCard({
  object,
  layerId,
  selectedObjectId,
  onSelect,
  onSaveToReusable,
  onRemove,
  reusableActionPendingId,
  editorContent,
}: {
  object: SceneObject;
  layerId: string;
  selectedObjectId: string;
  onSelect: (objectId: string) => void;
  onSaveToReusable: (object: SceneObject) => void;
  onRemove: (layerId: string, objectId: string) => void;
  reusableActionPendingId: string;
  editorContent: ReactNode;
}) {
  const isSelected = object.id === selectedObjectId;
  const stopCardAction =
    (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      handler();
    };

  return (
    <div className="grid gap-1.5">
      <article
        className={`${css.objectCard} grid cursor-pointer gap-2 p-3`}
        data-selected={isSelected}
        onClick={() => onSelect(object.id)}
      >
        <div className="flex items-start gap-2">
          <div
            className={`${css.objectBadge} grid size-[22px] shrink-0 place-items-center border text-accent`}
          >
            <MaterialIcon name="category" size={14} />
          </div>
          <div className="grid min-w-0 gap-0.5">
            <span className="text-[10px] font-semibold tracking-[0.07em] text-muted uppercase">
              物体节点
            </span>
            <h3 className="m-0 text-[13px]/[1.2] font-semibold text-ink">
              {object.name}
            </h3>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p className="m-0 text-xs/[1.5] text-muted">
              {(object.description || object.interaction || "尚未填写细节").slice(
                0,
                96,
              )}
              {(object.description || object.interaction || "").length > 96
                ? "..."
                : ""}
            </p>
            <div className="flex flex-wrap gap-1">
              {object.tags
                .split(",")
                .map((tag) => tag.trim())
                .filter(Boolean)
                .slice(0, 3)
                .map((tag) => (
                  <span
                    key={`${object.id}:${tag}`}
                    className="border border-accent-soft bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent"
                  >
                    #{tag}
                  </span>
                ))}
            </div>
          </>
        ) : null}

        <div className="flex flex-wrap gap-1">
          <SceneIconButton
            icon={
              reusableActionPendingId === object.id
                ? "hourglass_top"
                : "create_new_folder"
            }
            label="加入节点库"
            size="micro"
            onClick={stopCardAction(() => onSaveToReusable(object))}
            disabled={reusableActionPendingId === object.id}
          />
          <SceneIconButton
            icon="delete"
            label="删除物体"
            size="micro"
            variant="danger"
            onClick={stopCardAction(() => onRemove(layerId, object.id))}
          />
          <SceneIconButton
            icon={isSelected ? "expand_more" : "chevron_right"}
            label={isSelected ? "收起物体编辑器" : "展开物体编辑器"}
            expanded={isSelected}
            controls={
              isSelected ? `scene-object-editor-${layerId}-${object.id}` : undefined
            }
            size="micro"
            onClick={stopCardAction(() => onSelect(object.id))}
          />
        </div>
      </article>

      {isSelected ? (
        <div
          id={`scene-object-editor-${layerId}-${object.id}`}
          className={`${css.inlineEditor} mt-1.5 grid content-start gap-3 border-t pt-3.5`}
        >
          {editorContent}
        </div>
      ) : null}
    </div>
  );
}

export function SceneIconButton({
  icon,
  label,
  onClick,
  disabled = false,
  variant = "default",
  size = "small",
  expanded,
  controls,
}: {
  icon: MaterialIconName;
  label: string;
  onClick: (event: ReactMouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  variant?: "default" | "accent" | "danger";
  size?: "small" | "micro";
  expanded?: boolean;
  controls?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-expanded={expanded}
      aria-controls={controls}
      title={label}
      className={css.treeButton}
      data-size={size}
      data-variant={variant}
      onClick={onClick}
      disabled={disabled}
    >
      <MaterialIcon name={icon} size={size === "micro" ? 14 : 16} />
    </button>
  );
}

export function RewriteStateButton({
  actionKey,
  label,
  pendingKey,
  lastRewrite,
  rewriteStrength,
  onRewriteStrengthChange,
  onRewrite,
  onUndo,
}: {
  actionKey: string;
  label: string;
  pendingKey: string;
  lastRewrite: RewriteUndoEntry | null;
  rewriteStrength: number;
  onRewriteStrengthChange: (value: number) => void;
  onRewrite: () => void;
  onUndo: () => void;
}) {
  const popoverId = useId();
  const actionGroupRef = useRef<HTMLDivElement>(null);
  const [isStrengthOpen, setIsStrengthOpen] = useState(false);
  const strengthPopoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isStrengthOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!strengthPopoverRef.current?.contains(event.target as Node)) {
        setIsStrengthOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isStrengthOpen]);

  const isPending = pendingKey === actionKey;
  const isUndo = !isPending && lastRewrite?.key === actionKey;
  const icon = isPending ? "hourglass_top" : isUndo ? "undo" : "auto_awesome";
  const buttonLabel = isPending
    ? "重写中"
    : isUndo
      ? `撤销重写：${lastRewrite?.label ?? label}`
      : `AI 重写${label}`;

  useEffect(() => {
    if (isPending) {
      setIsStrengthOpen(false);
    }
  }, [isPending]);

  return (
    <div
      ref={actionGroupRef}
      className="relative inline-flex items-center gap-1"
      onKeyDown={(event) => {
        if (event.key === "Escape" && isStrengthOpen) {
          event.stopPropagation();
          setIsStrengthOpen(false);
          actionGroupRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
        }
      }}
    >
      <SceneIconButton
        icon={icon}
        label={buttonLabel}
        expanded={!isUndo && isStrengthOpen}
        controls={isStrengthOpen ? popoverId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          if (isPending) {
            return;
          }
          if (isUndo) {
            onUndo();
            return;
          }
          setIsStrengthOpen((current) => !current);
        }}
        disabled={Boolean(pendingKey)}
      />
      {!isPending && !isUndo && isStrengthOpen ? (
        <div
          id={popoverId}
          ref={strengthPopoverRef}
          className="absolute top-[calc(100%+8px)] right-0 z-20"
        >
          <div
            className={`${css.rewritePopover} relative grid w-[220px] gap-2.5 border bg-panel px-3 pt-3 pb-2.5`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs/[1.5] font-semibold text-ink">重写强度</span>
              <span className="text-xs/[1.5] font-semibold text-ink">
                {(rewriteStrength * 100).toFixed(0)}%
              </span>
            </div>
            <input
              className="min-h-11 w-full shrink-0"
              aria-label={`${label}重写强度`}
              aria-valuetext={`${(rewriteStrength * 100).toFixed(0)}%`}
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              value={rewriteStrength}
              onChange={(event) => onRewriteStrengthChange(Number(event.target.value))}
            />
            <p className="m-0 text-xs/[1.5] text-muted">
              数值越高，AI 对原始设定的改写幅度越大。
            </p>
            <button
              type="button"
              className="h-11 cursor-pointer border-0 bg-accent text-xs/[1.5] font-semibold text-white"
              onClick={(event) => {
                event.stopPropagation();
                actionGroupRef.current
                  ?.querySelector<HTMLButtonElement>("button")
                  ?.focus();
                setIsStrengthOpen(false);
                onRewrite();
              }}
            >
              开始重写
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
