import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ModelToolConfig,
  ModelToolConfigItem,
  ModelToolToggle,
} from "@vibe-learner/shared";

import { getModelToolConfig, updateModelToolConfig } from "../../lib/data/model-tools";
import { usePageDebugSnapshot } from "../debug/page-debug-context";
import {
  applyToggles,
  buildBatchToggles,
  countEnabledAvailable,
  selectSensoryTools,
  toolKey,
} from "./sensory-tools-model";

export function useSensoryToolsController() {
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [availability, setAvailability] = useState("");
  const [showDescriptions, setShowDescriptions] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [config, setConfig] = useState<ModelToolConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState("");
  const [error, setError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const confirmedConfigRef = useRef<ModelToolConfig | null>(null);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingTogglesRef = useRef<ModelToolToggle[][]>([]);

  const debugSnapshot = useMemo(
    () => ({
      title: "感官工具调试面板",
      subtitle: "查看工具配置和本页错误。",
      error,
      summary: [
        { label: "加载状态", value: loading ? "加载中" : "就绪" },
        { label: "阶段数", value: String(config?.stages.length ?? 0) },
        { label: "保存中", value: savingKey || "-" },
        {
          label: "可用工具",
          value: String(
            config?.stages.reduce(
              (count, stage) => count + countEnabledAvailable(stage.tools),
              0,
            ) ?? 0,
          ),
        },
      ],
      details: [
        { title: "模型工具配置", value: config },
        { title: "保存任务键", value: savingKey },
      ],
    }),
    [config, error, loading, savingKey],
  );

  usePageDebugSnapshot(debugSnapshot);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const payload = await getModelToolConfig();
        if (!cancelled) {
          confirmedConfigRef.current = payload;
          setConfig(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function publishOptimisticConfig() {
    const confirmed = confirmedConfigRef.current;
    if (confirmed) {
      setConfig(pendingTogglesRef.current.reduce(applyToggles, confirmed));
    }
  }

  function enqueueUpdate(toggles: ModelToolToggle[], key: string) {
    if (!confirmedConfigRef.current || !toggles.length) return;

    // Apply every queued intent immediately, including reversals of in-flight changes.
    pendingTogglesRef.current.push(toggles);
    publishOptimisticConfig();
    setSavingKey(key);
    setSaveMessage("");

    const run = async () => {
      setError("");
      try {
        confirmedConfigRef.current = await updateModelToolConfig(toggles);
        setSaveMessage("工具配置已保存。");
      } catch (err) {
        setError(String(err));
      } finally {
        // A failed patch drops only its own overlay. Later pending intents survive.
        pendingTogglesRef.current.shift();
        publishOptimisticConfig();
        if (pendingTogglesRef.current.length === 0) setSavingKey("");
      }
    };
    const queued = saveQueueRef.current.then(run, run);
    saveQueueRef.current = queued.catch(() => undefined);
  }

  function handleToggle(stageName: string, toolName: string, enabled: boolean) {
    enqueueUpdate([{ stageName, toolName, enabled }], toolKey(stageName, toolName));
  }

  function handleCategoryToggle(
    stageName: string,
    matchingTools: ModelToolConfigItem[],
    enabled: boolean,
  ) {
    enqueueUpdate(
      buildBatchToggles(stageName, matchingTools, enabled),
      `batch:${stageName}:${matchingTools[0]?.category ?? "unknown"}:${enabled ? "on" : "off"}`,
    );
  }

  const { stageRows, visibleCount } = selectSensoryTools(
    config?.stages ?? [],
    query,
    stageFilter,
    availability,
  );

  return {
    config,
    loading,
    savingKey,
    error,
    saveMessage,
    query,
    setQuery,
    stageFilter,
    setStageFilter,
    availability,
    setAvailability,
    showDescriptions,
    setShowDescriptions,
    batchMode,
    setBatchMode,
    stageRows,
    visibleCount,
    handleToggle,
    handleCategoryToggle,
  };
}
