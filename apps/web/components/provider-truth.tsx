"use client";

import type { RuntimeSettings } from "@vibe-learner/shared";

import { useRuntimeSettings } from "./runtime-settings-provider";

type ProviderScope = "plan" | "study" | "persona" | "scene" | "tavern";

const SCOPE_LABELS: Record<ProviderScope, string> = {
  plan: "计划生成",
  study: "学习对话",
  persona: "人格生成",
  scene: "场景生成",
  tavern: "酒馆互动",
};

export function ProviderTruth({ scope }: { scope: ProviderScope }) {
  const runtime = useRuntimeSettings();
  const settings = runtime.settings;
  if (runtime.loading) {
    return <div style={styles.banner}>正在确认 {SCOPE_LABELS[scope]} 的提供器状态…</div>;
  }
  if (runtime.error || !settings) {
    return (
      <div style={{ ...styles.banner, ...styles.warning }} role="status">
        无法读取提供器状态；当前页面不会把服务连通误报为模型可调用。
      </div>
    );
  }
  if (settings.planProvider === "mock") {
    return (
      <div style={{ ...styles.banner, ...styles.mock }} role="status">
        <strong>本地模拟，不调用真实模型</strong>
        <span>{SCOPE_LABELS[scope]} 将使用确定性模板结果，仅用于本地流程验证。</span>
      </div>
    );
  }

  const connection = resolveConnection(settings, scope);
  const configured = Boolean(connection.baseUrl && connection.model && connection.keyConfigured);
  return (
    <div style={{ ...styles.banner, ...(configured ? styles.real : styles.warning) }} role="status">
      <strong>
        {configured
          ? `真实模型接口已配置 · ${connection.model}`
          : "真实模型接口配置不完整"}
      </strong>
      <span>
        {configured
          ? "已配置或模型可列出不代表当前功能可调用；请在统一设置运行代表请求验证。"
          : "请在统一设置补齐 endpoint、模型与会话密钥。"}
      </span>
      {configured ? (
        <details style={styles.details}>
          <summary style={styles.summary}>了解可靠性边界</summary>
          <span style={styles.detailText}>
            功能可调用也不代表内容或事实正确；结构与提交证据只说明可靠性边界。
          </span>
        </details>
      ) : null}
    </div>
  );
}

function resolveConnection(
  settings: RuntimeSettings,
  scope: ProviderScope
) {
  if (scope === "plan") {
    return {
      baseUrl: settings.openaiPlanBaseUrl || settings.openaiBaseUrl,
      model: settings.openaiPlanModel,
      keyConfigured: settings.openaiPlanApiKeyConfigured || settings.openaiApiKeyConfigured || Boolean(settings.openaiPlanApiKey || settings.openaiApiKey),
    };
  }
  if (scope === "persona" || scope === "scene") {
    return {
      baseUrl: settings.openaiSettingBaseUrl || settings.openaiBaseUrl,
      model: settings.openaiSettingModel,
      keyConfigured: settings.openaiSettingApiKeyConfigured || settings.openaiApiKeyConfigured || Boolean(settings.openaiSettingApiKey || settings.openaiApiKey),
    };
  }
  return {
    baseUrl: settings.openaiChatBaseUrl || settings.openaiBaseUrl,
    model: settings.openaiChatModel,
    keyConfigured: settings.openaiChatApiKeyConfigured || settings.openaiApiKeyConfigured || Boolean(settings.openaiChatApiKey || settings.openaiApiKey),
  };
}

const styles = {
  banner: {
    display: "flex",
    flexWrap: "wrap" as const,
    alignItems: "baseline",
    gap: "6px 12px",
    margin: "0 0 14px",
    padding: "10px 12px",
    border: "1px solid var(--border)",
    borderRadius: 12,
    color: "var(--muted-foreground)",
    background: "var(--panel)",
    fontSize: 13,
  },
  mock: {
    borderColor: "color-mix(in srgb, var(--warning) 38%, var(--border))",
    background: "color-mix(in srgb, var(--warning) 8%, var(--panel))",
  },
  real: {
    borderColor: "color-mix(in srgb, var(--positive) 35%, var(--border))",
    background: "color-mix(in srgb, var(--positive) 7%, var(--panel))",
  },
  warning: {
    borderColor: "color-mix(in srgb, var(--negative) 35%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 6%, var(--panel))",
  },
  details: {
    flexBasis: "100%",
  },
  summary: {
    width: "fit-content",
    minHeight: 44,
    display: "flex",
    alignItems: "center",
    cursor: "pointer",
    color: "var(--muted-foreground)",
  },
  detailText: {
    display: "block",
    paddingTop: 4,
  },
};
