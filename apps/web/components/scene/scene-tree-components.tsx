"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";
import { type SceneObject, type SceneLayer } from "../../lib/scene-editor-model";
import { type RewriteUndoEntry } from "../../hooks/use-scene-rewrite";

import { styles } from "./scene-workspace-styles";

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
  onRequestDelete: (layerId: string) => void;
  canDeleteLayerForId: (layerId: string) => boolean;
  editorContent: ReactNode;
  renderObjectEditor: (layerId: string, object: SceneObject) => ReactNode;
}) {
  const isSelected = layer.id === selectedLayerId;
  const isCollapsed = collapsedLayerIds.includes(layer.id);
  const hasChildren = layer.children.length > 0;
  const hasObjects = layer.objects.length > 0;
  const stopCardAction = (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    handler();
  };
  return (
    <div style={styles.cardGroup}>
      <article
        style={{
          ...styles.layerCard,
          ...(isSelected ? styles.layerCardActive : null)
        }}
        onClick={() => onSelect(layer.id)}
      >
        <div style={styles.layerTopRow}>
          <div style={styles.layerIndexBadge}>{String(index + 1).padStart(2, "0")}</div>
          <div style={styles.layerHeadCopy}>
            <span style={styles.layerScope}>{layer.scopeLabel}</span>
            <h2 style={styles.layerTitle}>{layer.title}</h2>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p style={styles.layerSummary}>{layer.summary}</p>

            <div style={styles.objectChipRow}>
              {layer.tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 2).map((tag) => (
                <span key={`${layer.id}:${tag}`} style={styles.tagChip}>#{tag}</span>
              ))}
              {layer.objects.slice(0, 3).map((object) => (
                <span key={object.id} style={styles.objectChip}>{object.name}</span>
              ))}
              {layer.objects.length > 3 ? <span style={styles.objectChip}>+{layer.objects.length - 3}</span> : null}
            </div>
          </>
        ) : null}

        <div style={styles.cardActions}>
          {(hasChildren || hasObjects) && onToggleChildren ? (
            <button type="button" aria-expanded={!isCollapsed}
              aria-label={`${isCollapsed ? "展开" : "收起"}${layer.title}的子层和物体`}
              style={{ ...styles.iconButton, minWidth: 44, minHeight: 44 }}
              onClick={stopCardAction(() => onToggleChildren(layer.id))}>
              <MaterialIcon name={isCollapsed ? "chevron_right" : "expand_more"} size={18} />
            </button>
          ) : null}
          <SceneIconButton icon="add_circle" label="添加子层" size="micro" variant="accent" onClick={stopCardAction(() => onAddChild(layer.id))} />
          <SceneIconButton icon="category" label="添加物体" size="micro" onClick={stopCardAction(() => onAddObject(layer.id))} />
          <SceneIconButton
            icon={reusableActionPendingId === layer.id ? "hourglass_top" : "create_new_folder"}
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
            onClick={stopCardAction(() => onRequestDelete(layer.id))}
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

      {isSelected ? <div id={`scene-node-editor-${layer.id}`} style={styles.nodeInlineEditor}>{editorContent}</div> : null}

      {(hasObjects || hasChildren) && !isCollapsed ? (
        <div style={styles.childStack}>
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
  const stopCardAction = (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    handler();
  };

  return (
    <div style={styles.cardGroup}>
      <article
        style={{
          ...styles.objectNodeCard,
          ...(isSelected ? styles.objectNodeCardActive : null),
        }}
        onClick={() => onSelect(object.id)}
      >
        <div style={styles.objectNodeTopRow}>
          <div style={styles.objectNodeBadge}>
            <MaterialIcon name="category" size={14} />
          </div>
          <div style={styles.layerHeadCopy}>
            <span style={styles.layerScope}>物体节点</span>
            <h3 style={styles.layerTitle}>{object.name}</h3>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p style={styles.layerSummary}>
              {(object.description || object.interaction || "尚未填写细节").slice(0, 96)}
              {(object.description || object.interaction || "").length > 96 ? "..." : ""}
            </p>
            <div style={styles.objectChipRow}>
              {object.tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 3).map((tag) => (
                <span key={`${object.id}:${tag}`} style={styles.tagChip}>#{tag}</span>
              ))}
            </div>
          </>
        ) : null}

        <div style={styles.cardActions}>
          <SceneIconButton
            icon={reusableActionPendingId === object.id ? "hourglass_top" : "create_new_folder"}
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
            controls={isSelected ? `scene-object-editor-${layerId}-${object.id}` : undefined}
            size="micro"
            onClick={stopCardAction(() => onSelect(object.id))}
          />
        </div>
      </article>

      {isSelected ? <div id={`scene-object-editor-${layerId}-${object.id}`} style={styles.nodeInlineEditor}>{editorContent}</div> : null}
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
  const style = {
    ...(size === "micro" ? styles.iconButtonMicro : styles.iconButton),
    ...(variant === "accent"
      ? size === "micro"
        ? styles.iconButtonMicroAccent
        : styles.iconButtonAccent
      : variant === "danger"
        ? size === "micro"
          ? styles.iconButtonMicroDanger
          : styles.iconButtonDanger
        : {}),
    minWidth: 44,
    minHeight: 44,
  };
  return (
    <button type="button" aria-label={label} aria-expanded={expanded} aria-controls={controls} title={label} style={style} onClick={onClick} disabled={disabled}>
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
    <div ref={actionGroupRef} style={styles.rewriteActionGroup} onKeyDown={(event) => {
      if (event.key === "Escape" && isStrengthOpen) {
        event.stopPropagation();
        setIsStrengthOpen(false);
        actionGroupRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    }}>
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
      {(!isPending && !isUndo && isStrengthOpen) ? (
        <div id={popoverId} ref={strengthPopoverRef} style={styles.rewritePopoverWrap}>
          <div style={styles.rewritePopover} onClick={(event) => event.stopPropagation()}>
            <div style={styles.rewritePopoverSection}>
              <span style={styles.rewritePopoverTitle}>重写强度</span>
              <span style={styles.rewritePopoverValue}>{(rewriteStrength * 100).toFixed(0)}%</span>
            </div>
            <input
              style={styles.rewriteSlider}
              aria-label={`${label}重写强度`}
              aria-valuetext={`${(rewriteStrength * 100).toFixed(0)}%`}
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              value={rewriteStrength}
              onChange={(event) => onRewriteStrengthChange(Number(event.target.value))}
            />
            <p style={styles.rewritePopoverHint}>数值越高，AI 对原始设定的改写幅度越大。</p>
            <button
              type="button"
              style={styles.rewritePopoverButton}
              onClick={(event) => {
                event.stopPropagation();
                actionGroupRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
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

