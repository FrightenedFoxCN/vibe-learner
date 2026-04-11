"use client";

import { useEffect, useState, type CSSProperties, type FormEvent } from "react";

import type { RuntimeSettings } from "@vibe-learner/shared";
import { TopNav } from "../../components/top-nav";
import { useRuntimeSettings } from "../../components/runtime-settings-provider";
import { probeRuntimeOpenAIModels, updateRuntimeSettings } from "../../lib/api";

type ProbeScope = "global" | "plan" | "setting" | "chat";

type NumericSettingKey =
  | "openaiTimeoutSeconds"
  | "openaiSettingTemperature"
  | "openaiChatTemperature"
  | "openaiSettingMaxTokens"
  | "openaiChatMaxTokens"
  | "openaiChatHistoryMessages"
  | "openaiChatToolMaxRounds";

interface NumericSettingConfig {
  min: number;
  max: number;
  fallback: number;
  integer: boolean;
}

type NumericDraftState = Record<NumericSettingKey, string>;

interface ScopeProbeState {
  loading: boolean;
  available: boolean;
  models: string[];
  error: string;
}

const EMPTY_PROBE_STATE: ScopeProbeState = {
  loading: false,
  available: false,
  models: [],
  error: ""
};

const NUMERIC_SETTING_CONFIGS: Record<NumericSettingKey, NumericSettingConfig> = {
  openaiTimeoutSeconds: { min: 5, max: 300, fallback: 30, integer: true },
  openaiSettingTemperature: { min: 0, max: 2, fallback: 0.4, integer: false },
  openaiChatTemperature: { min: 0, max: 2, fallback: 0.35, integer: false },
  openaiSettingMaxTokens: { min: 64, max: 16384, fallback: 900, integer: true },
  openaiChatMaxTokens: { min: 64, max: 16384, fallback: 800, integer: true },
  openaiChatHistoryMessages: { min: 1, max: 40, fallback: 8, integer: true },
  openaiChatToolMaxRounds: { min: 1, max: 12, fallback: 4, integer: true }
};

export default function SettingsPage() {
  const runtimeSettings = useRuntimeSettings();
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [error, setError] = useState("");
  const [numericDrafts, setNumericDrafts] = useState<NumericDraftState>({
    openaiTimeoutSeconds: "",
    openaiSettingTemperature: "",
    openaiChatTemperature: "",
    openaiSettingMaxTokens: "",
    openaiChatMaxTokens: "",
    openaiChatHistoryMessages: "",
    openaiChatToolMaxRounds: ""
  });
  const [probeState, setProbeState] = useState<Record<ProbeScope, ScopeProbeState>>({
    global: { ...EMPTY_PROBE_STATE },
    plan: { ...EMPTY_PROBE_STATE },
    setting: { ...EMPTY_PROBE_STATE },
    chat: { ...EMPTY_PROBE_STATE }
  });

  useEffect(() => {
    if (runtimeSettings.settings) {
      setSettings(runtimeSettings.settings);
      setNumericDrafts(buildNumericDrafts(runtimeSettings.settings));
    }
  }, [runtimeSettings.settings]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      const normalized = normalizeNumericSettings(settings, numericDrafts);
      const next = await updateRuntimeSettings({
        planProvider: normalized.planProvider,
        openaiApiKey: normalized.openaiApiKey,
        openaiBaseUrl: normalized.openaiBaseUrl,
        openaiPlanApiKey: normalized.openaiPlanApiKey,
        openaiPlanBaseUrl: normalized.openaiPlanBaseUrl,
        openaiPlanModel: normalized.openaiPlanModel,
        openaiSettingApiKey: normalized.openaiSettingApiKey,
        openaiSettingBaseUrl: normalized.openaiSettingBaseUrl,
        openaiSettingModel: normalized.openaiSettingModel,
        openaiSettingWebSearchEnabled: normalized.openaiSettingWebSearchEnabled,
        openaiChatApiKey: normalized.openaiChatApiKey,
        openaiChatBaseUrl: normalized.openaiChatBaseUrl,
        openaiChatModel: normalized.openaiChatModel,
        openaiChatTemperature: normalized.openaiChatTemperature,
        openaiSettingTemperature: normalized.openaiSettingTemperature,
        openaiSettingMaxTokens: normalized.openaiSettingMaxTokens,
        openaiChatMaxTokens: normalized.openaiChatMaxTokens,
        openaiChatHistoryMessages: normalized.openaiChatHistoryMessages,
        openaiChatToolMaxRounds: normalized.openaiChatToolMaxRounds,
        openaiChatToolsEnabled: normalized.openaiChatToolsEnabled,
        openaiChatMemoryToolEnabled: normalized.openaiChatMemoryToolEnabled,
        openaiEmbeddingModel: normalized.openaiEmbeddingModel,
        openaiChatModelMultimodal: normalized.openaiChatModelMultimodal,
        openaiTimeoutSeconds: normalized.openaiTimeoutSeconds,
        openaiPlanModelMultimodal: normalized.openaiPlanModelMultimodal,
        openaiPlanToolsEnabled: normalized.openaiPlanToolsEnabled,
        openaiPlanFallbackModel: normalized.openaiPlanFallbackModel,
        openaiPlanFallbackDisableTools: normalized.openaiPlanFallbackDisableTools,
        showDebugInfo: normalized.showDebugInfo
      });
      runtimeSettings.replaceSettings(next);
      setSettings(next);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleProbe(scope: ProbeScope) {
    if (!settings) {
      return;
    }
    const endpoint = resolveScopeEndpoint(settings, scope);
    if (!endpoint.apiKey || !endpoint.baseUrl) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          error: "请先填写可用的访问密钥和服务地址"
        }
      }));
      return;
    }
    setProbeState((prev) => ({
      ...prev,
      [scope]: {
        ...prev[scope],
        loading: true,
        error: ""
      }
    }));
    try {
      const result = await probeRuntimeOpenAIModels(endpoint);
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          loading: false,
          available: result.available,
          models: result.models,
          error: result.error
        }
      }));
    } catch (err) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          error: String(err)
        }
      }));
    }
  }

  function commitNumericSetting(key: NumericSettingKey) {
    if (!settings) {
      return;
    }
    const nextValue = parseNumericSetting(numericDrafts[key], NUMERIC_SETTING_CONFIGS[key]);
    setSettings((prev) => (prev ? ({ ...prev, [key]: nextValue } as RuntimeSettings) : prev));
    setNumericDrafts((prev) => ({ ...prev, [key]: String(nextValue) }));
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/settings" />

      <header style={styles.header}>
        <h1 style={styles.title}>统一设置</h1>
        <p style={styles.subtitle}>通过可视化方式管理模型连接与运行参数，保存后立即生效。</p>
      </header>

      {runtimeSettings.loading ? <div style={styles.loading}>正在加载设置...</div> : null}
      {runtimeSettings.error ? <div style={styles.error}>设置加载失败：{runtimeSettings.error}</div> : null}
      {error ? <div style={styles.error}>设置操作失败：{error}</div> : null}

      {!runtimeSettings.loading && settings ? (
        <form className="settings-form" style={styles.form} onSubmit={handleSubmit}>
          <section style={styles.card}>
            <h2 style={styles.cardTitle}>模型提供商</h2>
            <label style={styles.field}>
              <span style={styles.label}>模型接口协议</span>
              <select
                value={settings.planProvider}
                onChange={(event) =>
                  setSettings((prev) =>
                    prev
                      ? {
                          ...prev,
                          planProvider: (event.target.value === "openai" ? "openai" : "mock") as
                            | "mock"
                            | "openai"
                        }
                      : prev
                  )
                }
              >
                <option value="mock">本地模拟</option>
                <option value="openai">OpenAI</option>
              </select>
            </label>
            <p style={styles.tip}>仅当选择 OpenAI 时显示连接、模型与高级参数。</p>
          </section>

          {settings.planProvider === "openai" ? (
            <>
              <section style={styles.card}>
                <h2 style={styles.cardTitle}>连接与模型</h2>
                <p style={styles.tip}>先配置默认连接，再按功能覆盖；子功能服务地址留空即继承默认服务地址。</p>

                <label style={styles.field}>
                  <span style={styles.label}>默认访问密钥</span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={settings.openaiApiKey}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, openaiApiKey: event.target.value } : prev))
                    }
                    placeholder="sk-..."
                  />
                </label>
                <label style={styles.field}>
                  <span style={styles.label}>默认服务地址</span>
                  <input
                    value={settings.openaiBaseUrl}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, openaiBaseUrl: event.target.value } : prev))
                    }
                    placeholder="https://api.openai.com/v1"
                  />
                </label>
                <div style={styles.probeRow}>
                  <button
                    type="button"
                    style={styles.secondaryBtn}
                    disabled={probeState.global.loading}
                    onClick={() => handleProbe("global")}
                  >
                    {probeState.global.loading ? "检测中..." : "检测默认连接并拉取模型"}
                  </button>
                  <span style={styles.probeHint}>{formatProbeHint(probeState.global)}</span>
                </div>

                <div style={styles.subCard}>
                  <h3 style={styles.subTitle}>计划生成</h3>
                  <div style={styles.grid2}>
                    <label style={styles.field}>
                      <span style={styles.label}>访问密钥</span>
                      <input
                        type="password"
                        autoComplete="off"
                        value={settings.openaiPlanApiKey}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiPlanApiKey: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认访问密钥"
                      />
                    </label>
                    <label style={styles.field}>
                      <span style={styles.label}>服务地址</span>
                      <input
                        value={settings.openaiPlanBaseUrl}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiPlanBaseUrl: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认服务地址"
                      />
                    </label>
                  </div>
                  <div style={styles.probeRow}>
                    <button
                      type="button"
                      style={styles.secondaryBtn}
                      disabled={probeState.plan.loading}
                      onClick={() => handleProbe("plan")}
                    >
                      {probeState.plan.loading ? "检测中..." : "检测计划连接并拉取模型"}
                    </button>
                    <span style={styles.probeHint}>{formatProbeHint(probeState.plan)}</span>
                  </div>
                  <label style={styles.field}>
                    <span style={styles.label}>模型选择</span>
                    <select
                      value={settings.openaiPlanModel}
                      onChange={(event) =>
                        setSettings((prev) => (prev ? { ...prev, openaiPlanModel: event.target.value } : prev))
                      }
                    >
                      {uniqueWithCurrent(probeState.plan.models, settings.openaiPlanModel).map((modelName) => (
                        <option key={modelName} value={modelName}>
                          {modelName}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div style={styles.subCard}>
                  <h3 style={styles.subTitle}>人格设置辅助</h3>
                  <div style={styles.grid2}>
                    <label style={styles.field}>
                      <span style={styles.label}>访问密钥</span>
                      <input
                        type="password"
                        autoComplete="off"
                        value={settings.openaiSettingApiKey}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiSettingApiKey: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认访问密钥"
                      />
                    </label>
                    <label style={styles.field}>
                      <span style={styles.label}>服务地址</span>
                      <input
                        value={settings.openaiSettingBaseUrl}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiSettingBaseUrl: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认服务地址"
                      />
                    </label>
                  </div>
                  <div style={styles.probeRow}>
                    <button
                      type="button"
                      style={styles.secondaryBtn}
                      disabled={probeState.setting.loading}
                      onClick={() => handleProbe("setting")}
                    >
                      {probeState.setting.loading ? "检测中..." : "检测人格设置连接并拉取模型"}
                    </button>
                    <span style={styles.probeHint}>{formatProbeHint(probeState.setting)}</span>
                  </div>
                  <label style={styles.field}>
                    <span style={styles.label}>模型选择</span>
                    <select
                      value={settings.openaiSettingModel}
                      onChange={(event) =>
                        setSettings((prev) =>
                          prev ? { ...prev, openaiSettingModel: event.target.value } : prev
                        )
                      }
                    >
                      {uniqueWithCurrent(probeState.setting.models, settings.openaiSettingModel).map((modelName) => (
                        <option key={modelName} value={modelName}>
                          {modelName}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label style={styles.checkboxField}>
                    <input
                      type="checkbox"
                      checked={settings.openaiSettingWebSearchEnabled}
                      onChange={(event) =>
                        setSettings((prev) =>
                          prev
                            ? { ...prev, openaiSettingWebSearchEnabled: event.target.checked }
                            : prev
                        )
                      }
                    />
                    <span style={styles.checkboxLabel}>允许人格设置模型访问网络资源</span>
                  </label>
                  <p style={styles.tip}>
                    关闭后，关键词生成人格卡片仍会调用设定模型，但不再使用联网搜索，而是仅根据关键词自行生成。
                  </p>
                </div>

                <div style={styles.subCard}>
                  <h3 style={styles.subTitle}>章节对话</h3>
                  <div style={styles.grid2}>
                    <label style={styles.field}>
                      <span style={styles.label}>访问密钥</span>
                      <input
                        type="password"
                        autoComplete="off"
                        value={settings.openaiChatApiKey}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiChatApiKey: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认访问密钥"
                      />
                    </label>
                    <label style={styles.field}>
                      <span style={styles.label}>服务地址</span>
                      <input
                        value={settings.openaiChatBaseUrl}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiChatBaseUrl: event.target.value } : prev
                          )
                        }
                        placeholder="留空则继承默认服务地址"
                      />
                    </label>
                  </div>
                  <div style={styles.probeRow}>
                    <button
                      type="button"
                      style={styles.secondaryBtn}
                      disabled={probeState.chat.loading}
                      onClick={() => handleProbe("chat")}
                    >
                      {probeState.chat.loading ? "检测中..." : "检测对话连接并拉取模型"}
                    </button>
                    <span style={styles.probeHint}>{formatProbeHint(probeState.chat)}</span>
                  </div>
                  <label style={styles.field}>
                    <span style={styles.label}>模型选择</span>
                    <select
                      value={settings.openaiChatModel}
                      onChange={(event) =>
                        setSettings((prev) => (prev ? { ...prev, openaiChatModel: event.target.value } : prev))
                      }
                    >
                      {uniqueWithCurrent(probeState.chat.models, settings.openaiChatModel).map((modelName) => (
                        <option key={modelName} value={modelName}>
                          {modelName}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label style={styles.field}>
                  <span style={styles.label}>请求超时时间（秒）</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={numericDrafts.openaiTimeoutSeconds}
                    onChange={(event) =>
                      setNumericDrafts((prev) => ({ ...prev, openaiTimeoutSeconds: event.target.value }))
                    }
                    onBlur={() => commitNumericSetting("openaiTimeoutSeconds")}
                  />
                </label>
              </section>

              <section style={styles.card}>
                <h2 style={styles.cardTitle}>多模态能力</h2>
                <p style={styles.tip}>将图像输入能力单独放在这里，避免和高级参数混在一起。</p>
                <div style={styles.toggleGrid}>
                  <label style={styles.switchField}>
                    <input
                      type="checkbox"
                      checked={settings.openaiChatModelMultimodal}
                      onChange={(event) =>
                        setSettings((prev) =>
                          prev ? { ...prev, openaiChatModelMultimodal: event.target.checked } : prev
                        )
                      }
                    />
                    <span>对话支持图像输入</span>
                  </label>
                  <label style={styles.switchField}>
                    <input
                      type="checkbox"
                      checked={settings.openaiPlanModelMultimodal}
                      onChange={(event) =>
                        setSettings((prev) =>
                          prev ? { ...prev, openaiPlanModelMultimodal: event.target.checked } : prev
                        )
                      }
                    />
                    <span>计划支持图像输入</span>
                  </label>
                </div>
              </section>

              <section style={styles.card}>
                <button
                  type="button"
                  style={styles.secondaryBtn}
                  onClick={() => setAdvancedExpanded((prev) => !prev)}
                >
                  {advancedExpanded ? "收起高级设置" : "展开高级设置"}
                </button>
                {!advancedExpanded ? (
                  <p style={styles.tip}>高级设置包括温度、输出长度、工具开关、降级策略和向量检索模型。</p>
                ) : (
                  <div style={styles.advancedContent}>
                    <div style={styles.grid2}>
                      <label style={styles.field}>
                        <span style={styles.label}>人格设置温度</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={numericDrafts.openaiSettingTemperature}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiSettingTemperature: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiSettingTemperature")}
                        />
                      </label>
                      <label style={styles.field}>
                        <span style={styles.label}>章节对话温度</span>
                        <input
                          type="text"
                          inputMode="decimal"
                          value={numericDrafts.openaiChatTemperature}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiChatTemperature: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiChatTemperature")}
                        />
                      </label>
                    </div>

                    <div style={styles.grid2}>
                      <label style={styles.field}>
                        <span style={styles.label}>人格设置最大输出长度</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={numericDrafts.openaiSettingMaxTokens}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiSettingMaxTokens: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiSettingMaxTokens")}
                        />
                      </label>
                      <label style={styles.field}>
                        <span style={styles.label}>章节对话最大输出长度</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={numericDrafts.openaiChatMaxTokens}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiChatMaxTokens: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiChatMaxTokens")}
                        />
                      </label>
                    </div>

                    <div style={styles.grid2}>
                      <label style={styles.field}>
                        <span style={styles.label}>保留历史消息数</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={numericDrafts.openaiChatHistoryMessages}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiChatHistoryMessages: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiChatHistoryMessages")}
                        />
                      </label>
                      <label style={styles.field}>
                        <span style={styles.label}>工具调用最大轮次</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={numericDrafts.openaiChatToolMaxRounds}
                          onChange={(event) =>
                            setNumericDrafts((prev) => ({ ...prev, openaiChatToolMaxRounds: event.target.value }))
                          }
                          onBlur={() => commitNumericSetting("openaiChatToolMaxRounds")}
                        />
                      </label>
                    </div>

                    <label style={styles.field}>
                      <span style={styles.label}>向量检索模型</span>
                      <input
                        value={settings.openaiEmbeddingModel}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiEmbeddingModel: event.target.value } : prev
                          )
                        }
                      />
                    </label>

                    <label style={styles.field}>
                      <span style={styles.label}>计划失败时的降级模型</span>
                      <input
                        value={settings.openaiPlanFallbackModel}
                        onChange={(event) =>
                          setSettings((prev) =>
                            prev ? { ...prev, openaiPlanFallbackModel: event.target.value } : prev
                          )
                        }
                        placeholder="留空表示不启用"
                      />
                    </label>

                    <div style={styles.toggleGrid}>
                      <label style={styles.switchField}>
                        <input
                          type="checkbox"
                          checked={settings.openaiChatToolsEnabled}
                          onChange={(event) =>
                            setSettings((prev) =>
                              prev ? { ...prev, openaiChatToolsEnabled: event.target.checked } : prev
                            )
                          }
                        />
                        <span>启用章节对话工具</span>
                      </label>
                      <label style={styles.switchField}>
                        <input
                          type="checkbox"
                          checked={settings.openaiChatMemoryToolEnabled}
                          onChange={(event) =>
                            setSettings((prev) =>
                              prev ? { ...prev, openaiChatMemoryToolEnabled: event.target.checked } : prev
                            )
                          }
                        />
                        <span>启用跨会话记忆检索</span>
                      </label>
                      <label style={styles.switchField}>
                        <input
                          type="checkbox"
                          checked={settings.openaiPlanToolsEnabled}
                          onChange={(event) =>
                            setSettings((prev) =>
                              prev ? { ...prev, openaiPlanToolsEnabled: event.target.checked } : prev
                            )
                          }
                        />
                        <span>启用计划工具链</span>
                      </label>
                      <label style={styles.switchField}>
                        <input
                          type="checkbox"
                          checked={settings.openaiPlanFallbackDisableTools}
                          onChange={(event) =>
                            setSettings((prev) =>
                              prev ? { ...prev, openaiPlanFallbackDisableTools: event.target.checked } : prev
                            )
                          }
                        />
                        <span>降级模型禁用工具链</span>
                      </label>
                    </div>
                  </div>
                )}
              </section>

              <section style={styles.card}>
                <h2 style={styles.cardTitle}>调试信息显示</h2>
                <label style={styles.switchField}>
                  <input
                    type="checkbox"
                    checked={settings.showDebugInfo}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, showDebugInfo: event.target.checked } : prev))
                    }
                  />
                  <span>显示调试悬浮窗（计划页与章节对话页会按此开关显示）</span>
                </label>
              </section>
            </>
          ) : (
            <section style={styles.card}>
              <p style={styles.tip}>当前使用本地模拟引擎，已隐藏 OpenAI 相关配置。</p>
            </section>
          )}

          <div style={styles.actions}>
            <button type="submit" disabled={saving} style={styles.primaryBtn}>
              {saving ? "保存中..." : "保存设置"}
            </button>
            <span style={styles.updatedAt}>最近更新：{settings.updatedAt || "-"}</span>
          </div>
        </form>
      ) : null}
    </main>
  );
}

function resolveScopeEndpoint(settings: RuntimeSettings, scope: ProbeScope): {
  apiKey: string;
  baseUrl: string;
} {
  if (scope === "global") {
    return {
      apiKey: settings.openaiApiKey.trim(),
      baseUrl: settings.openaiBaseUrl.trim()
    };
  }
  if (scope === "plan") {
    return {
      apiKey: (settings.openaiPlanApiKey || settings.openaiApiKey).trim(),
      baseUrl: (settings.openaiPlanBaseUrl || settings.openaiBaseUrl).trim()
    };
  }
  if (scope === "setting") {
    return {
      apiKey: (settings.openaiSettingApiKey || settings.openaiApiKey).trim(),
      baseUrl: (settings.openaiSettingBaseUrl || settings.openaiBaseUrl).trim()
    };
  }
  return {
    apiKey: (settings.openaiChatApiKey || settings.openaiApiKey).trim(),
    baseUrl: (settings.openaiChatBaseUrl || settings.openaiBaseUrl).trim()
  };
}

function formatProbeHint(state: ScopeProbeState): string {
  if (state.loading) {
    return "正在检测连接与模型列表...";
  }
  if (state.error) {
    return `失败：${state.error}`;
  }
  if (state.available) {
    return `可用，已发现 ${state.models.length} 个模型`;
  }
  return "未检测";
}

function uniqueWithCurrent(models: string[], current: string): string[] {
  const set = new Set<string>();
  const list: string[] = [];
  for (const modelName of [current, ...models]) {
    const name = String(modelName || "").trim();
    if (!name || set.has(name)) {
      continue;
    }
    set.add(name);
    list.push(name);
  }
  return list;
}

function buildNumericDrafts(settings: RuntimeSettings): NumericDraftState {
  return {
    openaiTimeoutSeconds: String(settings.openaiTimeoutSeconds),
    openaiSettingTemperature: String(settings.openaiSettingTemperature),
    openaiChatTemperature: String(settings.openaiChatTemperature),
    openaiSettingMaxTokens: String(settings.openaiSettingMaxTokens),
    openaiChatMaxTokens: String(settings.openaiChatMaxTokens),
    openaiChatHistoryMessages: String(settings.openaiChatHistoryMessages),
    openaiChatToolMaxRounds: String(settings.openaiChatToolMaxRounds)
  };
}

function parseNumericSetting(value: string, config: NumericSettingConfig): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return config.fallback;
  }
  const normalized = config.integer ? Math.round(parsed) : parsed;
  return Math.min(config.max, Math.max(config.min, normalized));
}

function normalizeNumericSettings(settings: RuntimeSettings, drafts: NumericDraftState): RuntimeSettings {
  return {
    ...settings,
    openaiTimeoutSeconds: parseNumericSetting(
      drafts.openaiTimeoutSeconds,
      NUMERIC_SETTING_CONFIGS.openaiTimeoutSeconds
    ),
    openaiSettingTemperature: parseNumericSetting(
      drafts.openaiSettingTemperature,
      NUMERIC_SETTING_CONFIGS.openaiSettingTemperature
    ),
    openaiChatTemperature: parseNumericSetting(
      drafts.openaiChatTemperature,
      NUMERIC_SETTING_CONFIGS.openaiChatTemperature
    ),
    openaiSettingMaxTokens: parseNumericSetting(
      drafts.openaiSettingMaxTokens,
      NUMERIC_SETTING_CONFIGS.openaiSettingMaxTokens
    ),
    openaiChatMaxTokens: parseNumericSetting(drafts.openaiChatMaxTokens, NUMERIC_SETTING_CONFIGS.openaiChatMaxTokens),
    openaiChatHistoryMessages: parseNumericSetting(
      drafts.openaiChatHistoryMessages,
      NUMERIC_SETTING_CONFIGS.openaiChatHistoryMessages
    ),
    openaiChatToolMaxRounds: parseNumericSetting(
      drafts.openaiChatToolMaxRounds,
      NUMERIC_SETTING_CONFIGS.openaiChatToolMaxRounds
    )
  };
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1100,
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
    fontSize: 14,
    color: "var(--muted)",
    lineHeight: 1.7
  },
  loading: {
    fontSize: 14,
    color: "var(--muted)"
  },
  error: {
    background: "#fff0f0",
    border: "1px solid #ffd9d9",
    color: "#9a1c1c",
    padding: "10px 12px",
    fontSize: 13
  },
  form: {
    display: "grid",
    gap: 16
  },
  card: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "16px 18px",
    display: "grid",
    gap: 12
  },
  cardTitle: {
    margin: 0,
    fontSize: 18,
    color: "var(--ink)"
  },
  subCard: {
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "12px",
    display: "grid",
    gap: 10
  },
  subTitle: {
    margin: 0,
    fontSize: 14,
    color: "var(--ink-2)"
  },
  tip: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)"
  },
  field: {
    display: "grid",
    gap: 6,
    fontSize: 13
  },
  label: {
    color: "var(--ink-2)",
    fontWeight: 600
  },
  probeRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap"
  },
  probeHint: {
    fontSize: 12,
    color: "var(--muted)"
  },
  advancedContent: {
    display: "grid",
    gap: 12
  },
  toggleGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))"
  },
  switchField: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
    color: "var(--ink)"
  },
  checkboxField: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13,
    color: "var(--ink)",
  },
  checkboxLabel: {
    color: "var(--ink)",
    fontSize: 13,
  },
  grid2: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))"
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: 12
  },
  primaryBtn: {
    border: "none",
    background: "var(--accent)",
    color: "#fff",
    height: 36,
    padding: "0 18px",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 600
  },
  secondaryBtn: {
    height: 30,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "0 10px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 500
  },
  updatedAt: {
    fontSize: 12,
    color: "var(--muted)"
  }
};
