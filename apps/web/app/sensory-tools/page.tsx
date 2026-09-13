"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { ModelToolConfig, ModelToolConfigItem, ModelToolStageConfig } from "@vibe-learner/shared";

import { AsyncFeedback } from "../../components/async-feedback";
import { TopNav } from "../../components/top-nav";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import { getModelToolConfig, updateModelToolConfig } from "../../lib/data/model-tools";

export default function SensoryToolsPage() {
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
  const feedbackAction = useRef<Element | null>(null);
  const configRef = useRef<ModelToolConfig | null>(null);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingSaveCountRef = useRef(0);

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
          value: String(config?.stages.reduce((count, stage) => count + stage.tools.filter((tool) => tool.enabled && tool.available).length, 0) ?? 0)
        }
      ],
      details: [
        { title: "模型工具配置", value: config },
        { title: "保存任务键", value: savingKey }
      ]
    }),
    [config, error, loading, savingKey]
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
          configRef.current = payload;
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
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleToggle(stage: ModelToolStageConfig, tool: ModelToolConfigItem, checked: boolean) {
    if (!config) {
      return;
    }
    await handleBatchUpdate(
      {
        config,
        configRef,
        saveQueueRef,
        pendingSaveCountRef,
        setConfig,
        setSavingKey,
        setError,
        setSaveMessage
      },
      [
        {
          stageName: stage.name,
          toolName: tool.name,
          enabled: checked
        }
      ],
      `${stage.name}:${tool.name}`
    );
  }

  async function handleCategoryToggle(
    stage: ModelToolStageConfig,
    tools: ModelToolConfigItem[],
    enabled: boolean
  ) {
    if (!config) {
      return;
    }
    const toggles = buildBatchToggles(stage, tools, enabled);
    await handleBatchUpdate(
      {
        config,
        configRef,
        saveQueueRef,
        pendingSaveCountRef,
        setConfig,
        setSavingKey,
        setError,
        setSaveMessage
      },
      toggles,
      `batch:${stage.name}:${tools[0]?.category ?? "unknown"}:${enabled ? "on" : "off"}`
    );
  }

  const matchesTool = (tool: ModelToolConfigItem) =>
    [tool.label, tool.name, tool.description, tool.categoryLabel].join(" ").toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()) &&
    (!availability || (availability === "available" ? tool.available : !tool.available));
  const visibleStages = config?.stages.filter(stage => !stageFilter || stage.name === stageFilter) ?? [];
  const visibleCount = visibleStages.reduce((count, stage) => count + stage.tools.filter(matchesTool).length, 0);

  return (
    <main onClickCapture={(event) => { feedbackAction.current = (event.target as Element).closest("button, input"); }} className="with-app-nav sensory-tools-page" style={styles.page}>
      <TopNav currentPath="/sensory-tools" />

      <header style={styles.header}>
        <h1 style={styles.title}>感官工具</h1>
      </header>

      <AsyncFeedback actionRef={feedbackAction} pending={Boolean(savingKey)} error={error ? `配置操作失败：${error}` : ""}
        message={loading ? "正在加载工具配置…" : savingKey ? "正在保存工具配置…" : saveMessage || "更改后自动保存。"} />

      {!loading && config ? (
        <section style={styles.stageList}>
          <div className="library-toolbar">
            <label>搜索工具<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="名称、用途或分类" /></label>
            <label>工作阶段<select value={stageFilter} onChange={event => setStageFilter(event.target.value)}><option value="">全部阶段</option>{config.stages.map(stage => <option key={stage.name} value={stage.name}>{stage.label}</option>)}</select></label>
            <label>可用性<select value={availability} onChange={event => setAvailability(event.target.value)}><option value="">全部工具</option><option value="available">可用</option><option value="unavailable">不可用</option></select></label>
            <label className="library-inline-option"><input className="sensory-checkbox" type="checkbox" checked={showDescriptions} onChange={event => setShowDescriptions(event.target.checked)} />展开用途说明</label>
            <button type="button" aria-pressed={batchMode} onClick={() => setBatchMode(value => !value)}>批量管理</button>
            <p role="status">找到 {visibleCount} 个工具</p>
          </div>
          {batchMode ? <p className="library-hint">批量操作仅影响当前筛选结果中的可用工具；阶段关闭时，启用工具不会开启阶段。</p> : null}
          {!visibleCount ? <p className="library-empty">没有匹配的工具，请调整搜索或筛选。</p> : null}
          {visibleStages.map((stage) => (

            <article key={stage.name} hidden={!stage.tools.some(matchesTool)} style={{ ...styles.stageCard, ...(!stage.tools.some(matchesTool) ? { display: "none" } : {}) }}>
              <div style={styles.stageHeader}>
                <div>
                  <h2 style={styles.stageTitle}>
                    {stage.label}
                    <span style={styles.stageCount}>({buildStageToolSummary(stage)})</span>
                  </h2>
                  <p style={styles.stageDesc}>{stage.description}</p>
                </div>
                <StageBadge enabled={stage.stageEnabled} reason={stage.stageDisabledReason} />
              </div>

              <div className="sensory-category-grid" style={styles.categoryWrap}>
                {groupByCategory(stage.tools).map((group) => (
                  <div key={`${stage.name}:${group.category}`} style={{ ...styles.categoryCard, ...(!group.tools.some(matchesTool) ? { display: "none" } : {}) }}>
                    <div style={styles.categoryHeader}>
                      <div style={styles.categoryTitle}>{group.label}</div>
                      {batchMode ? <div style={styles.categoryActions}>
                        <button
                          type="button"
                          style={styles.categoryActionBtn}
                          disabled={Boolean(savingKey)}
                          onClick={() =>
                            handleCategoryToggle(stage, group.tools.filter(matchesTool), true)
                          }
                        >
                          启用筛选结果
                        </button>
                        <button
                          type="button"
                          style={styles.categoryActionBtn}
                          disabled={Boolean(savingKey)}
                          onClick={() =>
                            handleCategoryToggle(stage, group.tools.filter(matchesTool), false)
                          }
                        >
                          停用筛选结果
                        </button>
                      </div> : null}
                    </div>
                    <div style={styles.toolList}>
                      {group.tools.map((tool) => {
                        const itemKey = `${stage.name}:${tool.name}`;
                        const busy = savingKey === itemKey;
                        return (
                          <div key={itemKey} style={{ ...styles.toolItem, ...(!matchesTool(tool) ? { display: "none" } : {}) }}>
                            <div style={styles.toolMeta}>
                              <div style={styles.toolName}>{tool.label}</div>
                              <details open={showDescriptions || undefined} className="tool-description"><summary>用途说明</summary><p style={styles.toolDesc}>{tool.description}</p></details>
                              {!tool.available ? (
                                <div style={styles.unavailable}>不可用：{tool.unavailableReason || "当前环境不支持"}</div>
                              ) : null}
                            </div>
                            <label className="sensory-toggle">
                            <input
                              className="sensory-checkbox"
                              type="checkbox"
                              aria-label={tool.label}
                              checked={tool.enabled}
                              disabled={!tool.available}
                              aria-busy={busy}
                              onChange={(event) => handleToggle(stage, tool, event.target.checked)}
                            />
                            </label>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </section>
      ) : null}
    </main>
  );
}

function groupByCategory(tools: ModelToolConfigItem[]) {
  const map = new Map<string, { category: string; label: string; tools: ModelToolConfigItem[] }>();
  for (const tool of tools) {
    const key = `${tool.category}:${tool.categoryLabel}`;
    const existing = map.get(key);
    if (existing) {
      existing.tools.push(tool);
      continue;
    }
    map.set(key, {
      category: tool.category,
      label: tool.categoryLabel,
      tools: [tool]
    });
  }
  return Array.from(map.values());
}

function buildStageToolSummary(stage: ModelToolStageConfig): string {
  const stageTools = stage.tools;
  if (!stageTools.length) {
    return "0/0";
  }
  const enabledCount = stageTools.filter((tool) => tool.enabled && tool.available).length;
  return `${enabledCount}/${stageTools.length}`;
}

function buildBatchToggles(
  stage: ModelToolStageConfig,
  tools: ModelToolConfigItem[],
  enabled: boolean
) {
  return tools
    .filter((tool) => tool.available)
    .filter((tool) => tool.enabled !== enabled)
    .map((tool) => ({
      stageName: stage.name,
      toolName: tool.name,
      enabled
    }));
}

function StageBadge({ enabled, reason }: { enabled: boolean; reason: string }) {
  if (enabled) {
    return <span style={styles.stageEnabled}>阶段可用</span>;
  }
  return <span style={styles.stageDisabled}>阶段关闭{reason ? `：${reason}` : ""}</span>;
}

async function handleBatchUpdate(
  input: {
    config: ModelToolConfig;
    configRef: { current: ModelToolConfig | null };
    saveQueueRef: { current: Promise<void> };
    pendingSaveCountRef: { current: number };
    setConfig: (next: ModelToolConfig) => void;
    setSavingKey: (next: string) => void;
    setError: (next: string) => void;
    setSaveMessage: (next: string) => void;
  },
  toggles: Array<{ stageName: string; toolName: string; enabled: boolean }>,
  key: string
) {
  if (!toggles.length) {
    return;
  }
  input.pendingSaveCountRef.current += 1;
  input.setSavingKey(key);
  input.setSaveMessage("");

  const run = async () => {
    const snapshot = input.configRef.current ?? input.config;
    const optimisticConfig = applyToggles(snapshot, toggles);
    input.setError("");
    input.configRef.current = optimisticConfig;
    input.setConfig(optimisticConfig);
    try {
      const nextConfig = await updateModelToolConfig(toggles);
      input.configRef.current = nextConfig;
      input.setConfig(nextConfig);
      input.setSaveMessage("工具配置已保存。");
    } catch (err) {
      // Requests are serialized so this rollback cannot erase a newer
      // optimistic update or a newer server response.
      input.configRef.current = snapshot;
      input.setConfig(snapshot);
      input.setError(String(err));
    } finally {
      input.pendingSaveCountRef.current -= 1;
      if (input.pendingSaveCountRef.current === 0) {
        input.setSavingKey("");
      }
    }
  };

  const queued = input.saveQueueRef.current.then(run, run);
  input.saveQueueRef.current = queued.catch(() => undefined);
  await queued;
}

function applyToggles(
  config: ModelToolConfig,
  toggles: Array<{ stageName: string; toolName: string; enabled: boolean }>
): ModelToolConfig {
  const table = new Map<string, boolean>();
  for (const toggle of toggles) {
    table.set(`${toggle.stageName}:${toggle.toolName}`, toggle.enabled);
  }
  return {
    ...config,
    stages: config.stages.map((stage) => ({
      ...stage,
      tools: stage.tools.map((tool) => {
        const key = `${stage.name}:${tool.name}`;
        const hit = table.get(key);
        if (hit === undefined) {
          return tool;
        }
        return {
          ...tool,
          enabled: hit,
          effectiveEnabled: hit && tool.available
        };
      })
    }))
  };
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1280,
    margin: "0 auto",
    padding: "38px 32px 56px",
    display: "grid",
    gap: 20,
    alignContent: "start"
  },
  header: {
    display: "grid",
    gap: 10
  },
  title: {
    margin: 0,
    fontSize: 28,
    fontWeight: 800,
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
    color: "var(--ink)"
  },
  subtitle: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 14
  },
  loading: {
    border: "1px solid var(--border)",
    padding: "16px",
    background: "var(--panel)",
    color: "var(--muted)"
  },
  error: {
    border: "1px solid color-mix(in srgb, var(--negative) 35%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 8%, white)",
    color: "var(--negative)",
    padding: "10px 12px"
  },
  stageList: {
    display: "grid",
    gap: 14
  },
  stageCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "14px",
    display: "grid",
    gap: 12
  },
  stageHeader: {
    display: "flex",
    alignItems: "start",
    justifyContent: "space-between",
    gap: 12
  },
  stageTitle: {
    margin: 0,
    fontSize: 18,
    color: "var(--ink)"
  },
  stageCount: {
    marginLeft: 8,
    fontSize: 14,
    color: "var(--muted)",
    fontWeight: 500
  },
  stageDesc: {
    margin: "4px 0 0",
    fontSize: 13,
    color: "var(--muted)"
  },
  stageAudit: {
    margin: "4px 0 0",
    fontSize: 11,
    color: "var(--muted)"
  },
  stageEnabled: {
    fontSize: 12,
    color: "var(--positive)",
    border: "1px solid color-mix(in srgb, var(--positive) 35%, var(--border))",
    background: "color-mix(in srgb, var(--positive) 9%, white)",
    padding: "2px 8px"
  },
  stageDisabled: {
    fontSize: 12,
    color: "var(--negative)",
    border: "1px solid color-mix(in srgb, var(--negative) 35%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 8%, white)",
    padding: "2px 8px"
  },
  categoryWrap: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12
  },
  categoryCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "10px",
    display: "grid",
    gap: 8,
    alignContent: "start"
  },
  categoryTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  categoryHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8
  },
  categoryActions: {
    display: "flex",
    gap: 6
  },
  categoryActionBtn: {
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--ink)",
    fontSize: 12,
    minHeight: 44,
    padding: "6px 8px",
    cursor: "pointer"
  },
  toolList: {
    display: "grid",
    gap: 8
  },
  toolItem: {
    background: "var(--bg)",
    border: "1px solid var(--border)",
    padding: "10px",
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    gap: 10,
    alignItems: "start"
  },
  toolMeta: {
    display: "grid",
    gap: 4
  },
  toolName: {
    color: "var(--ink)",
    fontSize: 14,
    fontWeight: 600
  },
  toolDesc: {
    color: "var(--muted)",
    fontSize: 12,
    lineHeight: 1.6
  },
  unavailable: {
    color: "var(--negative)",
    fontSize: 12
  },
  auditRow: {
    color: "var(--muted)",
    fontSize: 11,
    lineHeight: 1.5
  }
};
