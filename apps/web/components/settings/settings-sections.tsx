import { useState, type CSSProperties } from "react";

import type { RuntimeSettings } from "@vibe-learner/shared";
import { settingsStyles as styles } from "./settings-styles";
import {
  CAPABILITY_AUDIT_CONFIGS,
  capabilitySignalToBoolean,
  formatCapabilitySource,
  formatCapabilityStatus,
  formatProbeHint,
  resolveCapabilitySignal,
  uniqueWithCurrent
} from "./settings-utils";
import type { SettingsController } from "./use-settings-controller";

interface ScopeModelConfig {
  scope: "plan" | "setting" | "chat";
  title: string;
  description: string;
  apiKeyKey: "openaiPlanApiKey" | "openaiSettingApiKey" | "openaiChatApiKey";
  baseUrlKey: "openaiPlanBaseUrl" | "openaiSettingBaseUrl" | "openaiChatBaseUrl";
  modelKey: "openaiPlanModel" | "openaiSettingModel" | "openaiChatModel";
}

const MODEL_SCOPE_CONFIGS: ScopeModelConfig[] = [
  {
    scope: "plan",
    title: "计划生成",
    description: "专门负责学习计划编排，可覆盖默认连接与模型。",
    apiKeyKey: "openaiPlanApiKey",
    baseUrlKey: "openaiPlanBaseUrl",
    modelKey: "openaiPlanModel"
  },
  {
    scope: "setting",
    title: "人格设定辅助",
    description: "用于人格卡、设定词和系统提示词的润色与扩展。",
    apiKeyKey: "openaiSettingApiKey",
    baseUrlKey: "openaiSettingBaseUrl",
    modelKey: "openaiSettingModel"
  },
  {
    scope: "chat",
    title: "学习对话",
    description: "负责章节聊天、追问与后续工具调用。",
    apiKeyKey: "openaiChatApiKey",
    baseUrlKey: "openaiChatBaseUrl",
    modelKey: "openaiChatModel"
  }
];

export function SettingsHeader() {
  return (
    <header style={styles.header}>
      <h1 style={styles.title}>统一设置</h1>
      <p style={styles.subtitle}>
        统一管理 LiteLLM 接入、分场景模型和运行开关。页面会自动保存，模型能力可以单独拉取并回填，减少多模态和联网配置与事实不一致的情况。
      </p>
    </header>
  );
}

export function DesktopSecurityCard({ controller }: { controller: SettingsController }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  if (!controller.desktopSecurity.enabled) {
    return null;
  }

  const isUnconfigured = controller.desktopSecurity.vaultState === "unconfigured";
  const isUnlocked = controller.desktopSecurity.vaultState === "unlocked";
  const isBusy = controller.desktopSecurity.busy;

  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>桌面密钥库</h2>
      <p style={styles.cardDescription}>
        API key 不再写入后端数据库。桌面版会把密钥保存在本地加密 vault 中，解锁后仅同步到本次运行的 sidecar 内存。
      </p>

      <div style={styles.subCard}>
        <div style={styles.probeRow}>
          <StatusBadge
            label={`Vault：${isUnconfigured ? "未初始化" : isUnlocked ? "已解锁" : "已锁定"}`}
            tone={isUnlocked ? "positive" : "muted"}
          />
          <span style={styles.probeHint}>{controller.desktopSecurity.vaultPath || "未发现 vault 路径"}</span>
        </div>

        {controller.desktopSecurity.error ? (
          <div style={styles.error}>操作失败：{controller.desktopSecurity.error}</div>
        ) : null}

        {!isUnlocked ? (
          <>
            <label style={styles.field}>
              <span style={styles.label}>主密码</span>
              <input
                type="password"
                autoComplete="off"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少使用一个你能记住的高强度密码"
              />
            </label>

            {isUnconfigured ? (
              <label style={styles.field}>
                <span style={styles.label}>确认密码</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="再次输入主密码"
                />
              </label>
            ) : null}

            <div style={styles.probeRow}>
              <button
                type="button"
                style={styles.secondaryBtn}
                disabled={isBusy || !password.trim() || (isUnconfigured && password !== confirmPassword)}
                onClick={() =>
                  void (isUnconfigured
                    ? controller.initializeDesktopVault(password)
                    : controller.unlockDesktopVault(password))
                }
              >
                {isBusy ? "处理中..." : isUnconfigured ? "创建并解锁 vault" : "解锁 vault"}
              </button>
              {isUnconfigured && password && confirmPassword && password !== confirmPassword ? (
                <span style={styles.probeHint}>两次输入的密码不一致。</span>
              ) : null}
            </div>
          </>
        ) : (
          <div style={styles.probeRow}>
            <button type="button" style={styles.secondaryBtn} disabled={isBusy} onClick={() => void controller.lockDesktopVault()}>
              {isBusy ? "处理中..." : "锁定 vault"}
            </button>
            <button type="button" style={styles.ghostBtn} disabled={isBusy} onClick={() => void controller.clearDesktopSecrets()}>
              清空已保存密钥
            </button>
            <span style={styles.probeHint}>锁定后，后端本次运行中的 session secrets 会一起清除。</span>
          </div>
        )}
      </div>
    </section>
  );
}

export function ProviderCard({
  controller,
  settings
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>运行提供器</h2>
      <p style={styles.cardDescription}>“本地模拟”适合稳定调试，“LiteLLM SDK”则直接走 LiteLLM Python SDK，可直连带 provider 前缀的模型，也可接入 LiteLLM Proxy 等 OpenAI 兼容网关。</p>
      <label style={styles.field}>
        <span style={styles.label}>模型接口协议</span>
        <select
          value={settings.planProvider}
          onChange={(event) =>
            controller.setSettingField(
              "planProvider",
              (event.target.value === "litellm" ? "litellm" : "mock") as RuntimeSettings["planProvider"]
            )
          }
        >
          <option value="mock">本地模拟</option>
          <option value="litellm">LiteLLM SDK</option>
        </select>
      </label>
    </section>
  );
}

export function ConnectionModelsCard({
  controller,
  settings
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  const desktopManagedSecrets =
    controller.desktopSecurity.enabled && controller.desktopSecurity.vaultState !== "unlocked";

  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>连接与模型分配</h2>
      <p style={styles.cardDescription}>
        默认连接会作为各个场景的回退来源。这里既可以填 LiteLLM Proxy，也可以填 LiteLLM SDK 可访问的上游地址；但“拉取模型/能力”当前仍优先依赖 `/models` 兼容响应，若上游不提供该接口，可直接手填模型名。
      </p>

      <div style={styles.subCard}>
        <div style={styles.subCardHeader}>
          <h3 style={styles.subTitle}>默认连接</h3>
          <p style={styles.tip}>当下方场景未单独填写密钥或地址时，会自动继承这里的配置。</p>
        </div>

        <label style={styles.field}>
          <span style={styles.label}>默认访问密钥</span>
          <input
            type="password"
            autoComplete="off"
            value={settings.openaiApiKey}
            onChange={(event) => controller.setSettingField("openaiApiKey", event.target.value)}
            disabled={desktopManagedSecrets}
            placeholder={
              desktopManagedSecrets
                ? settings.openaiApiKeyConfigured
                  ? "已保存在桌面 vault，解锁后可编辑"
                  : "先在上方创建或解锁桌面 vault"
                : "sk-..."
            }
          />
          {desktopManagedSecrets ? (
            <span style={styles.fieldHint}>
              {settings.openaiApiKeyConfigured
                ? "当前默认密钥已存入桌面密钥库，后端不会持久化明文。"
                : "桌面模式下，密钥只能在 vault 解锁后编辑。"}
            </span>
          ) : null}
        </label>
        <label style={styles.field}>
          <span style={styles.label}>默认服务地址</span>
          <input
            value={settings.openaiBaseUrl}
            onChange={(event) => controller.setSettingField("openaiBaseUrl", event.target.value)}
            placeholder="http://127.0.0.1:4000"
          />
        </label>
        <div style={styles.probeRow}>
          <button
            type="button"
            style={styles.secondaryBtn}
            disabled={controller.probeState.global.loading || desktopManagedSecrets}
            onClick={() => void controller.probeScope("global")}
          >
            {controller.probeState.global.loading ? "拉取中..." : "拉取默认连接模型"}
          </button>
          <span style={styles.probeHint}>{formatProbeHint(controller.probeState.global)}</span>
        </div>
      </div>

      <div style={styles.grid2}>
        {MODEL_SCOPE_CONFIGS.map((config) => (
          <ScopeModelCard
            key={config.scope}
            config={config}
            controller={controller}
            settings={settings}
          />
        ))}
      </div>

      <label style={styles.field}>
        <span style={styles.label}>请求超时时间（秒）</span>
        <input
          type="text"
          inputMode="numeric"
          value={controller.numericDrafts.openaiTimeoutSeconds}
          onChange={(event) => controller.setNumericDraft("openaiTimeoutSeconds", event.target.value)}
          onBlur={() => controller.commitNumericSetting("openaiTimeoutSeconds")}
        />
        <span style={styles.fieldHint}>所有模型连接都会复用这个超时值，建议保持在 15 到 60 秒之间。</span>
      </label>
    </section>
  );
}

export function CapabilityAuditCard({
  controller,
  settings
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>能力对照与回填</h2>
      <p style={styles.cardDescription}>
        这里把“手工开关”和“刚刚拉取到的模型能力”放在一起看。检测值有明确结论时，可以一键回填，避免把联网或多模态能力开错。
      </p>

      <div style={styles.auditGrid}>
        {CAPABILITY_AUDIT_CONFIGS.map((config) => {
          const modelName = String(settings[config.modelKey] || "");
          const probe = controller.probeState[config.scope];
          const capability = probe.capabilities[modelName];
          const signal = resolveCapabilitySignal(capability, config.capabilityKey);
          const detectedValue = capabilitySignalToBoolean(signal);
          const manualValue = Boolean(settings[config.manualKey]);
          const mismatch = detectedValue !== null && detectedValue !== manualValue;
          const sourceText = formatCapabilitySource(signal);
          const showToolTypes = capability?.toolTypes?.length;
          const showModalities = capability?.inputModalities?.length || capability?.outputModalities?.length;

          return (
            <section key={config.scope} style={styles.auditCard}>
              <div style={styles.auditHeader}>
                <h3 style={styles.auditTitle}>{config.title}</h3>
                <p style={styles.auditDescription}>{config.description}</p>
              </div>

              <div style={styles.auditModel}>
                当前模型：<strong>{modelName || "未设置"}</strong>
              </div>

              <label style={styles.switchField}>
                <input
                  type="checkbox"
                  checked={manualValue}
                  onChange={(event) =>
                    controller.setSettingField(
                      config.manualKey,
                      event.target.checked as RuntimeSettings[typeof config.manualKey]
                    )
                  }
                />
                <span>{config.manualLabel}</span>
              </label>

              <div style={styles.capabilityStack}>
                <div style={styles.capabilityRow}>
                  <StatusBadge label={`检测结果：${formatCapabilityStatus(signal)}`} tone={toneForStatus(signal.status)} />
                  <StatusBadge
                    label={sourceText}
                    tone={signal.source === "metadata" ? "positive" : signal.source === "model_name" ? "muted" : "muted"}
                  />
                  {mismatch ? <StatusBadge label="当前开关与检测结果不一致" tone="negative" /> : null}
                </div>
                <p style={styles.capabilityNote}>{signal.note}</p>
                {showModalities ? (
                  <div style={styles.ruleText}>
                    输入模态：{capability?.inputModalities?.join(", ") || "-"}
                    {" · "}
                    输出模态：{capability?.outputModalities?.join(", ") || "-"}
                  </div>
                ) : null}
                {showToolTypes ? (
                  <div style={styles.ruleText}>工具类型：{capability?.toolTypes.join(", ")}</div>
                ) : null}
                {!probe.lastCheckedAt ? (
                  <div style={styles.ruleText}>还没有拉取这个连接的模型能力，请先回到上方连接区执行拉取。</div>
                ) : null}
              </div>

              <div style={styles.probeRow}>
                <button
                  type="button"
                  style={styles.secondaryBtn}
                  disabled={probe.loading}
                  onClick={() => void controller.probeScope(config.scope)}
                >
                  {probe.loading ? "拉取中..." : "刷新能力信息"}
                </button>
                <button
                  type="button"
                  style={styles.ghostBtn}
                  disabled={detectedValue === null}
                  onClick={() => controller.syncCapabilitySetting(config.scope)}
                >
                  {signal.source === "model_name" ? "按推断结果回填" : "按检测结果回填"}
                </button>
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

export function AdvancedSettingsCard({
  controller,
  settings
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <section style={styles.card}>
      <div style={styles.probeRow}>
        <h2 style={styles.cardTitle}>高级运行参数</h2>
        <button
          type="button"
          style={styles.secondaryBtn}
          onClick={() => controller.setAdvancedExpanded(!controller.advancedExpanded)}
        >
          {controller.advancedExpanded ? "收起高级设置" : "展开高级设置"}
        </button>
      </div>
      <p style={styles.cardDescription}>
        这些参数主要影响人格设定辅助、学习对话和工具链回退逻辑。默认值已经偏稳妥，只有在你明确知道要调什么时再改。
      </p>

      {controller.advancedExpanded ? (
        <div style={styles.advancedContent}>
          <div style={styles.grid2}>
            <label style={styles.field}>
              <span style={styles.label}>人格设定温度</span>
              <input
                type="text"
                inputMode="decimal"
                value={controller.numericDrafts.openaiSettingTemperature}
                onChange={(event) => controller.setNumericDraft("openaiSettingTemperature", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiSettingTemperature")}
              />
            </label>
            <label style={styles.field}>
              <span style={styles.label}>学习对话温度</span>
              <input
                type="text"
                inputMode="decimal"
                value={controller.numericDrafts.openaiChatTemperature}
                onChange={(event) => controller.setNumericDraft("openaiChatTemperature", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiChatTemperature")}
              />
            </label>
          </div>

          <div style={styles.grid2}>
            <label style={styles.field}>
              <span style={styles.label}>人格设定最大输出长度</span>
              <input
                type="text"
                inputMode="numeric"
                value={controller.numericDrafts.openaiSettingMaxTokens}
                onChange={(event) => controller.setNumericDraft("openaiSettingMaxTokens", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiSettingMaxTokens")}
              />
            </label>
            <label style={styles.field}>
              <span style={styles.label}>学习对话最大输出长度</span>
              <input
                type="text"
                inputMode="numeric"
                value={controller.numericDrafts.openaiChatMaxTokens}
                onChange={(event) => controller.setNumericDraft("openaiChatMaxTokens", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiChatMaxTokens")}
              />
            </label>
          </div>

          <div style={styles.grid2}>
            <label style={styles.field}>
              <span style={styles.label}>保留历史消息数</span>
              <input
                type="text"
                inputMode="numeric"
                value={controller.numericDrafts.openaiChatHistoryMessages}
                onChange={(event) => controller.setNumericDraft("openaiChatHistoryMessages", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiChatHistoryMessages")}
              />
            </label>
            <label style={styles.field}>
              <span style={styles.label}>工具调用最大轮次</span>
              <input
                type="text"
                inputMode="numeric"
                value={controller.numericDrafts.openaiChatToolMaxRounds}
                onChange={(event) => controller.setNumericDraft("openaiChatToolMaxRounds", event.target.value)}
                onBlur={() => controller.commitNumericSetting("openaiChatToolMaxRounds")}
              />
            </label>
          </div>

          <div style={styles.grid2}>
            <label style={styles.field}>
              <span style={styles.label}>向量检索模型</span>
              <input
                value={settings.openaiEmbeddingModel}
                onChange={(event) => controller.setSettingField("openaiEmbeddingModel", event.target.value)}
              />
            </label>
            <label style={styles.field}>
              <span style={styles.label}>计划失败时的降级模型</span>
              <input
                value={settings.openaiPlanFallbackModel}
                onChange={(event) => controller.setSettingField("openaiPlanFallbackModel", event.target.value)}
                placeholder="留空表示不启用"
              />
            </label>
          </div>

          <div style={styles.toggleGrid}>
            <label style={styles.switchField}>
              <input
                type="checkbox"
                checked={settings.openaiPlanFallbackDisableTools}
                onChange={(event) =>
                  controller.setSettingField("openaiPlanFallbackDisableTools", event.target.checked)
                }
              />
              <span>降级模型禁用工具链</span>
            </label>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function DebugVisibilityCard({
  controller,
  settings
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <section style={styles.card}>
      <h2 style={styles.cardTitle}>调试信息显示</h2>
      <p style={styles.cardDescription}>控制计划页和学习对话页里的调试悬浮信息是否可见，这个开关和模型提供器无关。</p>
      <label style={styles.switchField}>
        <input
          type="checkbox"
          checked={settings.showDebugInfo}
          onChange={(event) => controller.setSettingField("showDebugInfo", event.target.checked)}
        />
        <span>显示调试悬浮窗</span>
      </label>
    </section>
  );
}

export function AutoSaveStatusBar({ controller }: { controller: SettingsController }) {
  return (
    <div style={styles.statusBar}>
      <div style={styles.statusMain}>
        <StatusBadge {...savePhaseBadge(controller.savePhase)} />
        <span style={styles.statusText}>{savePhaseText(controller.savePhase, controller.saveError)}</span>
      </div>
      <div style={styles.statusMain}>
        <span style={styles.updatedAt}>最近保存：{controller.lastSavedAt || "-"}</span>
        {controller.savePhase === "error" ? (
          <button type="button" style={styles.secondaryBtn} onClick={controller.retrySave}>
            重试保存
          </button>
        ) : null}
      </div>
    </div>
  );
}

function ScopeModelCard({
  config,
  controller,
  settings
}: {
  config: ScopeModelConfig;
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  const probe = controller.probeState[config.scope];
  const models = uniqueWithCurrent(probe.models, String(settings[config.modelKey] || ""));
  const desktopManagedSecrets =
    controller.desktopSecurity.enabled && controller.desktopSecurity.vaultState !== "unlocked";
  const configured =
    config.apiKeyKey === "openaiPlanApiKey"
      ? settings.openaiPlanApiKeyConfigured
      : config.apiKeyKey === "openaiSettingApiKey"
        ? settings.openaiSettingApiKeyConfigured
        : settings.openaiChatApiKeyConfigured;

  return (
    <section style={styles.subCard}>
      <div style={styles.subCardHeader}>
        <h3 style={styles.subTitle}>{config.title}</h3>
        <p style={styles.tip}>{config.description}</p>
      </div>

      <label style={styles.field}>
        <span style={styles.label}>访问密钥</span>
        <input
          type="password"
          autoComplete="off"
          value={String(settings[config.apiKeyKey] || "")}
          disabled={desktopManagedSecrets}
          onChange={(event) =>
            controller.setSettingField(
              config.apiKeyKey,
              event.target.value as RuntimeSettings[typeof config.apiKeyKey]
            )
          }
          placeholder={
            desktopManagedSecrets
              ? configured
                ? "已保存在桌面 vault，解锁后可编辑"
                : "先解锁桌面 vault"
              : "留空则继承默认访问密钥"
          }
        />
        {desktopManagedSecrets ? (
          <span style={styles.fieldHint}>
            {configured ? "当前场景已有可用密钥，解锁后会显示明文输入框。" : "未检测到该场景的可用密钥。"}
          </span>
        ) : null}
      </label>
      <label style={styles.field}>
        <span style={styles.label}>服务地址</span>
        <input
          value={String(settings[config.baseUrlKey] || "")}
          onChange={(event) =>
            controller.setSettingField(
              config.baseUrlKey,
              event.target.value as RuntimeSettings[typeof config.baseUrlKey]
            )
          }
          placeholder="留空则继承默认服务地址"
        />
      </label>
      <div style={styles.probeRow}>
        <button
          type="button"
          style={styles.secondaryBtn}
          disabled={probe.loading || desktopManagedSecrets}
          onClick={() => void controller.probeScope(config.scope)}
        >
          {probe.loading ? "拉取中..." : "拉取模型与能力"}
        </button>
        <span style={styles.probeHint}>{formatProbeHint(probe)}</span>
      </div>
      <label style={styles.field}>
        <span style={styles.label}>模型选择</span>
        <select
          value={String(settings[config.modelKey] || "")}
          onChange={(event) =>
            controller.setSettingField(
              config.modelKey,
              event.target.value as RuntimeSettings[typeof config.modelKey]
            )
          }
        >
          {models.map((modelName) => (
            <option key={modelName} value={modelName}>
              {modelName}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function StatusBadge({
  label,
  tone
}: {
  label: string;
  tone: "positive" | "negative" | "muted";
}) {
  return (
    <span style={{ ...styles.badge, ...badgeToneStyle(tone) } as CSSProperties}>
      {label}
    </span>
  );
}

function badgeToneStyle(tone: "positive" | "negative" | "muted"): CSSProperties {
  if (tone === "positive") {
    return styles.badgePositive;
  }
  if (tone === "negative") {
    return styles.badgeNegative;
  }
  return styles.badgeMuted;
}

function toneForStatus(status: "supported" | "unsupported" | "unknown"): "positive" | "negative" | "muted" {
  if (status === "supported") {
    return "positive";
  }
  if (status === "unsupported") {
    return "negative";
  }
  return "muted";
}

function savePhaseBadge(phase: SettingsController["savePhase"]): {
  label: string;
  tone: "positive" | "negative" | "muted";
} {
  if (phase === "saving") {
    return { label: "自动保存中", tone: "muted" };
  }
  if (phase === "pending") {
    return { label: "等待保存", tone: "muted" };
  }
  if (phase === "error") {
    return { label: "保存失败", tone: "negative" };
  }
  if (phase === "saved") {
    return { label: "已保存", tone: "positive" };
  }
  return { label: "未开始", tone: "muted" };
}

function savePhaseText(phase: SettingsController["savePhase"], error: string): string {
  if (phase === "saving") {
    return "正在把最新修改同步到后端。";
  }
  if (phase === "pending") {
    return "检测到更改，稍后会自动保存。";
  }
  if (phase === "error") {
    return `自动保存失败：${error || "未知错误"}`;
  }
  if (phase === "saved") {
    return "最近一次修改已经自动保存。";
  }
  return "设置加载后会进入自动保存模式。";
}
