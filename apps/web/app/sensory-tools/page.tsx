"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { ModelToolConfig, ModelToolConfigItem, ModelToolStageConfig } from "@vibe-learner/shared";

import { TopNav } from "../../components/top-nav";
import { getModelToolConfig, updateModelToolConfig } from "../../lib/api";

export default function SensoryToolsPage() {
  const [config, setConfig] = useState<ModelToolConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const payload = await getModelToolConfig();
        if (!cancelled) {
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
        setConfig,
        setSavingKey,
        setError
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
        setConfig,
        setSavingKey,
        setError
      },
      toggles,
      `batch:${stage.name}:${tools[0]?.category ?? "unknown"}:${enabled ? "on" : "off"}`
    );
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/sensory-tools" />

      <header style={styles.header}>
        <h1 style={styles.title}>感官工具</h1>
        <p style={styles.subtitle}>统一管理模型在不同阶段可调用的工具，并按阶段与类别进行启用控制。</p>
      </header>

      {loading ? <div style={styles.loading}>正在加载工具配置...</div> : null}
      {error ? <div style={styles.error}>配置更新失败：{error}</div> : null}

      {!loading && config ? (
        <section style={styles.stageList}>
          {config.stages.map((stage) => (
            <article key={stage.name} style={styles.stageCard}>
              <div style={styles.stageHeader}>
                <div>
                  <h2 style={styles.stageTitle}>
                    {stage.label}
                    <span style={styles.stageCount}>({buildStageToolSummary(stage)})</span>
                  </h2>
                  <p style={styles.stageDesc}>{stage.description}</p>
                  <p style={styles.stageAudit}>审计：{stage.auditBasis.join(" | ") || "-"}</p>
                </div>
                <StageBadge enabled={stage.stageEnabled} reason={stage.stageDisabledReason} />
              </div>

              <div style={styles.categoryWrap}>
                {groupByCategory(stage.tools).map((group) => (
                  <div key={`${stage.name}:${group.category}`} style={styles.categoryCard}>
                    <div style={styles.categoryHeader}>
                      <div style={styles.categoryTitle}>{group.label}</div>
                      <div style={styles.categoryActions}>
                        <button
                          type="button"
                          style={styles.categoryActionBtn}
                          disabled={Boolean(savingKey)}
                          onClick={() =>
                            handleCategoryToggle(stage, group.tools, true)
                          }
                        >
                          全开
                        </button>
                        <button
                          type="button"
                          style={styles.categoryActionBtn}
                          disabled={Boolean(savingKey)}
                          onClick={() =>
                            handleCategoryToggle(stage, group.tools, false)
                          }
                        >
                          全关
                        </button>
                      </div>
                    </div>
                    <div style={styles.toolList}>
                      {group.tools.map((tool) => {
                        const itemKey = `${stage.name}:${tool.name}`;
                        const busy = savingKey === itemKey;
                        return (
                          <label key={itemKey} style={styles.toolItem}>
                            <div style={styles.toolMeta}>
                              <div style={styles.toolName}>{tool.label}</div>
                              <div style={styles.toolDesc}>{tool.description}</div>
                              {!tool.available ? (
                                <div style={styles.unavailable}>不可用：{tool.unavailableReason || "当前环境不支持"}</div>
                              ) : null}
                              <div style={styles.auditRow}>审计：{tool.auditBasis.join(" | ") || "-"}</div>
                            </div>
                            <input
                              type="checkbox"
                              checked={tool.enabled}
                              disabled={!tool.available || busy}
                              onChange={(event) => handleToggle(stage, tool, event.target.checked)}
                            />
                          </label>
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
    setConfig: (next: ModelToolConfig) => void;
    setSavingKey: (next: string) => void;
    setError: (next: string) => void;
  },
  toggles: Array<{ stageName: string; toolName: string; enabled: boolean }>,
  key: string
) {
  if (!toggles.length) {
    return;
  }
  const snapshot = input.config;
  input.setSavingKey(key);
  input.setError("");
  input.setConfig(applyToggles(snapshot, toggles));
  try {
    const nextConfig = await updateModelToolConfig(toggles);
    input.setConfig(nextConfig);
  } catch (err) {
    input.setConfig(snapshot);
    input.setError(String(err));
  } finally {
    input.setSavingKey("");
  }
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
    fontSize: 32,
    letterSpacing: "-0.02em",
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
    background: "white",
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
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
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
    background: "white",
    color: "var(--ink)",
    fontSize: 12,
    padding: "2px 8px",
    cursor: "pointer"
  },
  toolList: {
    display: "grid",
    gap: 8
  },
  toolItem: {
    background: "white",
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
