"use client";

import { useEffect, useRef, useState } from "react";
import type { ModelRecovery } from "@vibe-learner/shared";
import { diagnosticContext } from "../lib/diagnostics";
import { assistPersonaSlot } from "../lib/data/personas";
import { AsyncResultFence, type AsyncResultScope, type AsyncResultTicket } from "../lib/async-result-fence";
import { findLayerById, type SceneLayer, type SceneObject } from "../lib/scene-editor-model";

export type RewriteUndoEntry =
  | {
      kind: "layer";
      key: string;
      label: string;
      layerId: string;
      field: "summary" | "atmosphere" | "rules" | "entrance";
      previousValue: string;
      appliedValue: string;
      subjectId: string;
    }
  | {
      kind: "object";
      key: string;
      label: string;
      layerId: string;
      objectId: string;
      field: "description" | "interaction";
      previousValue: string;
      appliedValue: string;
      subjectId: string;
    };

interface SceneRewriteOptions {
  beginDiagnosticAction?: typeof diagnosticContext;
  sceneLayers: SceneLayer[];
  currentSceneAsyncScope: () => AsyncResultScope;
  setSceneFieldTarget: (target: string) => void;
  updateLayer: (id: string, update: (layer: SceneLayer) => SceneLayer) => void;
  updateObject: (layerId: string, objectId: string, key: keyof SceneObject, value: string) => void;
}

export function useSceneRewrite({ sceneLayers, currentSceneAsyncScope, setSceneFieldTarget, updateLayer, updateObject, beginDiagnosticAction = diagnosticContext }: SceneRewriteOptions, assist = assistPersonaSlot) {
  const [rewriteStrength, setRewriteStrength] = useState(0.6);
  const [rewritePendingKey, setRewritePendingKey] = useState("");
  const [rewriteError, setRewriteError] = useState("");
  const [rewriteModelRecoveries, setRewriteModelRecoveries] = useState<ModelRecovery[]>([]);
  const [lastRewrite, setLastRewrite] = useState<RewriteUndoEntry | null>(null);
  const rewriteFenceRef = useRef(new AsyncResultFence());
  const mountedRef = useRef(true);
  const canApply = (ticket: AsyncResultTicket) => mountedRef.current && rewriteFenceRef.current.decide(ticket, currentSceneAsyncScope()) === "apply";
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; rewriteFenceRef.current.invalidate(); };
  }, []);
  function invalidateRewrite() {
    rewriteFenceRef.current.invalidate();
    setRewritePendingKey("");
  }
  function resetRewrite() {
    invalidateRewrite();
    setLastRewrite(null);
    setRewriteError("");
    setRewriteModelRecoveries([]);
  }
  function undoLastRewrite() {
    if (!lastRewrite || rewritePendingKey) {
      return;
    }
    const layer = findLayerById(sceneLayers, lastRewrite.layerId);
    const currentValue = lastRewrite.kind === "layer"
      ? layer?.[lastRewrite.field]
      : layer?.objects.find(object => object.id === lastRewrite.objectId)?.[lastRewrite.field];
    if (currentSceneAsyncScope().subjectId !== lastRewrite.subjectId || currentValue !== lastRewrite.appliedValue) {
      setLastRewrite(null);
      setRewriteError("字段已更改，无法撤销旧重写。");
      return;
    }
    if (lastRewrite.kind === "layer") {
      updateLayer(lastRewrite.layerId, (layer) => ({
        ...layer,
        [lastRewrite.field]: lastRewrite.previousValue
      }));
    } else {
      updateObject(lastRewrite.layerId, lastRewrite.objectId, lastRewrite.field, lastRewrite.previousValue);
    }
    setLastRewrite(null);
    setRewriteError("");
  }

  async function rewriteLayerField(layerId: string, field: "summary" | "atmosphere" | "rules" | "entrance", label: string) {
    if (!mountedRef.current) return;
    const layer = findLayerById(sceneLayers, layerId);
    if (!layer) {
      return;
    }
    const sourceText = layer[field].trim();
    if (!sourceText) {
      setRewriteError("请先填写内容，再进行 AI 重写。");
      return;
    }

    const pendingKey = `${layerId}:${field}`;
    setSceneFieldTarget(pendingKey);
    setRewriteError("");
    setRewriteModelRecoveries([]);
    setRewritePendingKey(pendingKey);
    const ticket = rewriteFenceRef.current.begin(currentSceneAsyncScope());
    try {
      const previousValue = layer[field];
      const result = await assist({
        name: `场景层级 ${layer.title}`,
        summary: `${layer.scopeLabel}：${layer.summary}`,
        slot: {
          kind: "custom",
          label,
          content: layer[field],
          weight: 1,
          locked: false,
          sortOrder: 0
        },
        rewriteStrength: Number(rewriteStrength.toFixed(2))
      }, beginDiagnosticAction());
      if (!canApply(ticket)) {
        return;
      }
      updateLayer(layerId, (currentLayer) => ({
        ...currentLayer,
        [field]: result.slot.content
      }));
      setRewriteModelRecoveries(result.modelRecoveries ?? []);
      setLastRewrite({
        kind: "layer",
        key: pendingKey,
        label,
        layerId,
        field,
        previousValue,
        appliedValue: result.slot.content,
        subjectId: ticket.subjectId,
      });
    } catch (error) {
      if (canApply(ticket)) {
        setRewriteError(String(error));
      }
    } finally {
      if (rewriteFenceRef.current.settle(ticket)) {
        setRewritePendingKey("");
      }
    }
  }

  async function rewriteObjectField(layerId: string, objectId: string, field: "description" | "interaction", label: string) {
    if (!mountedRef.current) return;
    const layer = findLayerById(sceneLayers, layerId);
    const object = layer?.objects.find((item) => item.id === objectId);
    if (!layer || !object) {
      return;
    }
    const sourceText = object[field].trim();
    if (!sourceText) {
      setRewriteError("请先填写内容，再进行 AI 重写。");
      return;
    }

    const pendingKey = `${layerId}:${objectId}:${field}`;
    setSceneFieldTarget(pendingKey);
    setRewriteError("");
    setRewriteModelRecoveries([]);
    setRewritePendingKey(pendingKey);
    const ticket = rewriteFenceRef.current.begin(currentSceneAsyncScope());
    try {
      const previousValue = object[field];
      const result = await assist({
        name: `场景物体 ${object.name}`,
        summary: `${layer.title} / ${object.name}`,
        slot: {
          kind: "custom",
          label,
          content: object[field],
          weight: 1,
          locked: false,
          sortOrder: 0
        },
        rewriteStrength: Number(rewriteStrength.toFixed(2))
      }, beginDiagnosticAction());
      if (!canApply(ticket)) {
        return;
      }
      updateObject(layerId, objectId, field, result.slot.content);
      setRewriteModelRecoveries(result.modelRecoveries ?? []);
      setLastRewrite({
        kind: "object",
        key: pendingKey,
        label,
        layerId,
        objectId,
        field,
        previousValue,
        appliedValue: result.slot.content,
        subjectId: ticket.subjectId,
      });
    } catch (error) {
      if (canApply(ticket)) {
        setRewriteError(String(error));
      }
    } finally {
      if (rewriteFenceRef.current.settle(ticket)) {
        setRewritePendingKey("");
      }
    }
  }

  return {
    rewriteStrength,
    setRewriteStrength,
    rewritePendingKey,
    rewriteError,
    rewriteModelRecoveries,
    lastRewrite,
    undoLastRewrite,
    rewriteLayerField,
    rewriteObjectField,
    invalidateRewrite,
    resetRewrite,
  };
}
