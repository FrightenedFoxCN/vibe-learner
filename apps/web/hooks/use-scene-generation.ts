"use client";

import { useEffect, useRef, useState } from "react";
import type { ModelRecovery } from "@vibe-learner/shared";
import { generateSceneTree } from "../lib/data/scenes";
import { AsyncResultFence, type AsyncResultScope, type AsyncResultTicket } from "../lib/async-result-fence";
import { parseSceneImportPayload, countSceneNodes, normalizeSceneTreeNodeForProfile, type SceneLayer } from "../lib/scene-editor-model";

export function useSceneGeneration(currentSceneAsyncScope: (fieldTarget?: string) => AsyncResultScope, generate = generateSceneTree) {
  const [sceneKeywordInput, setSceneKeywordInput] = useState("");
  const [sceneLongTextFile, setSceneLongTextFile] = useState<File | null>(null);
  const [sceneGenerateMode, setSceneGenerateMode] = useState<"keywords" | "long_text">("keywords");
  const [sceneGenerateLayerCount, setSceneGenerateLayerCount] = useState("");
  const [sceneGeneratePending, setSceneGeneratePending] = useState<null | "keywords" | "long_text">(null);
  const [sceneGenerateError, setSceneGenerateError] = useState("");
  const [sceneGenerateMessage, setSceneGenerateMessage] = useState("");
  const [sceneGenerateModelRecoveries, setSceneGenerateModelRecoveries] = useState<ModelRecovery[]>([]);
  const [generatedSceneCandidate, setGeneratedSceneCandidate] = useState<{
    sceneName: string;
    sceneSummary: string;
    sceneLayers: SceneLayer[];
    selectedLayerId: string;
    collapsedLayerIds: string[];
    usedModel: string;
    usedWebSearch: boolean;
    mode: "keywords" | "long_text";
  } | null>(null);
  const sceneGenerationFenceRef = useRef(new AsyncResultFence());
  const mountedRef = useRef(true);
  const canApply = (ticket: AsyncResultTicket) => mountedRef.current && sceneGenerationFenceRef.current.decide(ticket, currentSceneAsyncScope("scene-generation-candidate")) === "apply";
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; sceneGenerationFenceRef.current.invalidate(); };
  }, []);
  function resetSceneGeneration() {
    sceneGenerationFenceRef.current.invalidate();
    setSceneGeneratePending(null);
    setGeneratedSceneCandidate(null);
    setSceneGenerateError("");
    setSceneGenerateMessage("");
    setSceneGenerateModelRecoveries([]);
  }
  async function handleGenerateScene(mode: "keywords" | "long_text") {
    if (!mountedRef.current) return;
    const requestScope = currentSceneAsyncScope("scene-generation-candidate");
    const ticket = sceneGenerationFenceRef.current.begin(requestScope);
    setSceneGenerateError("");
    setSceneGenerateMessage("");
    setSceneGenerateModelRecoveries([]);
    setSceneGeneratePending(mode);
    try {
      let inputText = "";
      if (mode === "keywords") {
        inputText = sceneKeywordInput.trim();
      } else {
        const longTextFile = sceneLongTextFile;
        if (!longTextFile) {
          setSceneGenerateError("请先上传长文本文件。");
          return;
        }
        try {
          inputText = (await longTextFile.text()).trim();
        } catch {
          if (canApply(ticket)) setSceneGenerateError("读取长文本文件失败，请重试。");
          return;
        }
      }
      if (!canApply(ticket)) return;
      if (!inputText) {
        setSceneGenerateError(mode === "keywords" ? "请先输入关键词。" : "上传文件内容为空，请更换文件。");
        return;
      }
      const layerCountText = sceneGenerateLayerCount.trim();
      let layerCount: number | null = null;
      if (layerCountText) {
        const parsedLayerCount = Number(layerCountText);
        if (!Number.isInteger(parsedLayerCount) || parsedLayerCount < 1) {
          setSceneGenerateError("层级偏好必须是大于 0 的整数，或留空交给模型决定。");
          return;
        }
        layerCount = parsedLayerCount;
      }
      const result = await generate({
        mode,
        inputText,
        layerCount,
      });
      const imported = parseSceneImportPayload({
        sceneName: result.sceneName,
        sceneSummary: result.sceneSummary,
        sceneLayers: result.sceneLayers,
        selectedLayerId: result.selectedLayerId,
        collapsedLayerIds: [],
      });
      if (!canApply(ticket)) {
        return;
      }
      setGeneratedSceneCandidate({
        ...imported,
        usedModel: result.usedModel,
        usedWebSearch: result.usedWebSearch,
        mode: result.mode,
      });
      setSceneGenerateModelRecoveries(result.modelRecoveries ?? []);
      setSceneGenerateMessage(
        `已生成 ${countSceneNodes(imported.sceneLayers.map((layer) => normalizeSceneTreeNodeForProfile(layer)))} 个节点。模型：${result.usedModel || "unknown"}${result.usedWebSearch ? "，已启用联网搜索。" : "。"}`
      );
    } catch (error) {
      if (canApply(ticket)) {
        setSceneGenerateError(String(error));
      }
    } finally {
      if (sceneGenerationFenceRef.current.settle(ticket)) {
        setSceneGeneratePending(null);
      }
    }
  }

  return {
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
    sceneGenerateMessage,
    sceneGenerateModelRecoveries,
    generatedSceneCandidate,
    handleGenerateScene,
    resetSceneGeneration,
  };
}
