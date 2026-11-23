"use client";

import type { RuntimeSettings } from "@vibe-learner/shared";

import { useRuntimeSettings } from "../layout/runtime-settings-provider";

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
    return (
      <ProviderMarker
        label="正在确认模型状态"
        description={`${scopeLabel}的提供器状态正在确认`}
        tone="neutral"
      />
    );
  }
  if (runtime.error || !settings) {
    return (
      <ProviderMarker
        label="模型状态不可用"
        description={`${scopeLabel}的提供器状态不可用`}
        tone="warning"
      />
    );
  }
  if (settings.planProvider === "mock") {
    return (
      <ProviderMarker
        label="本地模拟"
        description={`${scopeLabel}使用本地模拟，不调用真实模型`}
        tone="mock"
      />
    );
  }

  const connection = resolveConnection(settings, scope);
  const configured = Boolean(
    connection.baseUrl && connection.model && connection.keyConfigured,
  );
  return (
    <ProviderMarker
      label={configured ? `网络模型 · ${connection.model}` : "网络模型未配置"}
      description={
        configured
          ? `${scopeLabel}使用网络模型 ${connection.model}；请在统一设置运行代表请求验证。`
          : `${scopeLabel}的网络模型接口配置不完整。`
      }
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
  const appearance = toneStyles[tone];
  return (
    <span
      className={`inline-flex min-h-6 min-w-0 max-w-full shrink-0 items-center gap-1.5 overflow-hidden rounded-full border px-2 py-0.5 text-[13px] leading-[1.3] font-semibold ${appearance.marker}`}
      role="status"
      aria-label={description}
      title={description}
    >
      <span
        className={`size-1.5 shrink-0 rounded-full ${appearance.dot}`}
        aria-hidden="true"
      />
      <span className="min-w-0 truncate">{label}</span>
    </span>
  );
}

function resolveConnection(settings: RuntimeSettings, scope: ProviderScope) {
  if (scope === "plan") {
    return {
      baseUrl: settings.openaiPlanBaseUrl || settings.openaiBaseUrl,
      model: settings.openaiPlanModel,
      keyConfigured:
        settings.openaiPlanApiKeyConfigured ||
        settings.openaiApiKeyConfigured ||
        Boolean(settings.openaiPlanApiKey || settings.openaiApiKey),
    };
  }
  if (scope === "persona" || scope === "scene") {
    return {
      baseUrl: settings.openaiSettingBaseUrl || settings.openaiBaseUrl,
      model: settings.openaiSettingModel,
      keyConfigured:
        settings.openaiSettingApiKeyConfigured ||
        settings.openaiApiKeyConfigured ||
        Boolean(settings.openaiSettingApiKey || settings.openaiApiKey),
    };
  }
  return {
    baseUrl: settings.openaiChatBaseUrl || settings.openaiBaseUrl,
    model: settings.openaiChatModel,
    keyConfigured:
      settings.openaiChatApiKeyConfigured ||
      settings.openaiApiKeyConfigured ||
      Boolean(settings.openaiChatApiKey || settings.openaiApiKey),
  };
}

const toneStyles = {
  neutral: { marker: "border-border bg-panel text-ink-2", dot: "bg-muted" },
  mock: { marker: "border-border-strong bg-panel-strong text-ink-2", dot: "bg-ink-2" },
  real: {
    marker: "border-positive/35 bg-positive/5 text-positive",
    dot: "bg-positive",
  },
  warning: {
    marker: "border-negative/35 bg-negative/5 text-negative",
    dot: "bg-negative",
  },
} as const;
