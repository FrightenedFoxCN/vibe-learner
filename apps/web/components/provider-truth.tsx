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
  const scopeLabel = SCOPE_LABELS[scope];

  if (runtime.loading) {
    return <ProviderMarker label="正在确认模型状态" description={`${scopeLabel}的提供器状态正在确认`} tone="neutral" />;
  }
  if (runtime.error || !settings) {
    return <ProviderMarker label="模型状态不可用" description={`${scopeLabel}的提供器状态不可用`} tone="warning" />;
  }
  if (settings.planProvider === "mock") {
    return <ProviderMarker label="本地模拟" description={`${scopeLabel}使用本地模拟，不调用真实模型`} tone="mock" />;
  }

  const connection = resolveConnection(settings, scope);
  const configured = Boolean(connection.baseUrl && connection.model && connection.keyConfigured);
  return (
    <ProviderMarker
      label={configured ? `网络模型 · ${connection.model}` : "网络模型未配置"}
      description={configured
        ? `${scopeLabel}使用网络模型 ${connection.model}；请在统一设置运行代表请求验证。`
        : `${scopeLabel}的网络模型接口配置不完整。`}
      tone={configured ? "real" : "warning"}
    />
  );
}

function ProviderMarker({
  label,
  description,
  tone,
}: {
  label: string;
  description: string;
  tone: keyof typeof toneStyles;
}) {
  const toneStyle = toneStyles[tone];
  return (
    <span
      style={{ ...styles.marker, ...toneStyle.marker }}
      role="status"
      aria-label={description}
      title={description}
    >
      <span style={{ ...styles.dot, ...toneStyle.dot }} aria-hidden="true" />
      <span style={styles.label}>{label}</span>
    </span>
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
  marker: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    minHeight: 24,
    minWidth: 0,
    maxWidth: "100%",
    padding: "2px 8px",
    border: "1px solid var(--border)",
    borderRadius: 999,
    color: "var(--ink-2)",
    background: "var(--panel)",
    fontSize: 13,
    fontWeight: 600,
    lineHeight: 1.3,
    flexShrink: 0,
    overflow: "hidden",
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    flex: "0 0 auto",
  },
  label: {
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
};

const toneStyles = {
  neutral: {
    marker: {},
    dot: { background: "var(--muted)" },
  },
  mock: {
    marker: {
      borderColor: "#d8b763",
      background: "#fff8e1",
      color: "#725b16",
    },
    dot: { background: "#a16d00" },
  },
  real: {
    marker: {
      borderColor: "color-mix(in srgb, var(--positive) 35%, var(--border))",
      background: "color-mix(in srgb, var(--positive) 7%, var(--panel))",
      color: "var(--positive)",
    },
    dot: { background: "var(--positive)" },
  },
  warning: {
    marker: {
      borderColor: "color-mix(in srgb, var(--negative) 35%, var(--border))",
      background: "color-mix(in srgb, var(--negative) 6%, var(--panel))",
      color: "var(--negative)",
    },
    dot: { background: "var(--negative)" },
  },
} as const;
