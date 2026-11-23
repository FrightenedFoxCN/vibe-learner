import type { RuntimeFeatureProbeName, RuntimeSettings } from "@vibe-learner/shared";
import { Button } from "../ui/button";
import { SettingsField, SettingsPanel, StatusBadge } from "./settings-ui";
import { formatProbeHint, uniqueWithCurrent } from "./settings-utils";
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
    description: "用于学习计划生成。",
    apiKeyKey: "openaiPlanApiKey",
    baseUrlKey: "openaiPlanBaseUrl",
    modelKey: "openaiPlanModel",
  },
  {
    scope: "chat",
    title: "学习对话",
    description: "用于章节对话。",
    apiKeyKey: "openaiChatApiKey",
    baseUrlKey: "openaiChatBaseUrl",
    modelKey: "openaiChatModel",
  },
  {
    scope: "setting",
    title: "设定辅助",
    description: "用于人格与场景设定内容生成与润色。",
    apiKeyKey: "openaiSettingApiKey",
    baseUrlKey: "openaiSettingBaseUrl",
    modelKey: "openaiSettingModel",
  },
];

export function ProviderCard({
  controller,
  settings,
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <SettingsPanel>
      <h2 className="m-0 text-lg font-semibold text-ink">运行提供器</h2>
      <SettingsField label="模型接口协议">
        <select
          value={settings.planProvider}
          onChange={(event) =>
            controller.setSettingField(
              "planProvider",
              (event.target.value === "litellm"
                ? "litellm"
                : "mock") as RuntimeSettings["planProvider"],
            )
          }
        >
          <option value="mock">本地模拟</option>
          <option value="litellm">LiteLLM SDK</option>
        </select>
      </SettingsField>
    </SettingsPanel>
  );
}

export function ConnectionModelsCard({
  controller,
  settings,
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  const desktopManagedSecrets =
    controller.desktopSecurity.enabled &&
    controller.desktopSecurity.vaultState !== "unlocked";

  return (
    <SettingsPanel>
      <h2 className="m-0 text-lg font-semibold text-ink">连接与模型分配</h2>
      <div className="grid min-w-0 content-start gap-2.5 border border-solid border-border bg-bg p-3.5">
        <div className="grid gap-1">
          <h3 className="m-0 text-sm font-semibold text-ink-2">默认连接</h3>
          <p className="m-0 text-xs text-muted">未单独设置时会继承这里的配置。</p>
        </div>

        <SettingsField label="默认访问密钥">
          <input
            type="password"
            autoComplete="off"
            value={settings.openaiApiKey}
            onChange={(event) =>
              controller.setSettingField("openaiApiKey", event.target.value)
            }
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
            <span className="text-xs text-muted wrap-anywhere">
              {settings.openaiApiKeyConfigured
                ? "默认密钥已存入桌面密钥库。"
                : "解锁后才能编辑密钥。"}
            </span>
          ) : null}
        </SettingsField>
        <SettingsField label="默认服务地址">
          <input
            value={settings.openaiBaseUrl}
            onChange={(event) =>
              controller.setSettingField("openaiBaseUrl", event.target.value)
            }
            placeholder="http://127.0.0.1:4000"
          />
        </SettingsField>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            data-probe-scope="global"
            data-probe-action="models"
            disabled={controller.probeState.global.loading || desktopManagedSecrets}
            onClick={() => void controller.probeScope("global")}
          >
            {controller.probeState.global.loading ? "拉取中…" : "拉取默认模型"}
          </Button>
          <span role="status" className="text-xs text-muted wrap-anywhere">
            {formatProbeHint(controller.probeState.global)}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
        {MODEL_SCOPE_CONFIGS.map((config) => (
          <ScopeModelCard
            key={config.scope}
            config={config}
            controller={controller}
            settings={settings}
          />
        ))}
      </div>

      <SettingsField label="请求超时时间（秒）">
        <input
          type="text"
          inputMode="numeric"
          value={controller.numericDrafts.openaiTimeoutSeconds}
          onChange={(event) =>
            controller.setNumericDraft("openaiTimeoutSeconds", event.target.value)
          }
          onBlur={() => controller.commitNumericSetting("openaiTimeoutSeconds")}
        />
      </SettingsField>
    </SettingsPanel>
  );
}

function ScopeModelCard({
  config,
  controller,
  settings,
}: {
  config: ScopeModelConfig;
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  const probe = controller.probeState[config.scope];
  const currentModel = String(settings[config.modelKey] || "");
  const models = uniqueWithCurrent(probe.models, currentModel);
  const featureLabels: Array<[RuntimeFeatureProbeName, string]> =
    config.scope === "plan"
      ? [["plan", "计划工具请求"]]
      : config.scope === "setting"
        ? [
            ["persona", "人格生成"],
            ["scene", "场景生成"],
          ]
        : [
            ["study", "学习对话"],
            ["tavern", "酒馆严格输出"],
          ];
  const modelListed = probe.models.includes(currentModel);
  const currentFeatureReadiness = featureLabels
    .map(([feature]) => probe.featureReadiness[feature])
    .filter((readiness) => readiness?.model === currentModel);
  const authenticationPassed =
    probe.available ||
    currentFeatureReadiness.some((readiness) => readiness?.status === "ready");
  const desktopManagedSecrets =
    controller.desktopSecurity.enabled &&
    controller.desktopSecurity.vaultState !== "unlocked";
  const configured =
    config.apiKeyKey === "openaiPlanApiKey"
      ? settings.openaiPlanApiKeyConfigured
      : config.apiKeyKey === "openaiSettingApiKey"
        ? settings.openaiSettingApiKeyConfigured
        : settings.openaiChatApiKeyConfigured;

  return (
    <section
      className="grid min-w-0 content-start gap-2.5 border border-solid border-border bg-bg p-3.5"
      data-model-scope={config.scope}
    >
      <div className="grid gap-1">
        <h3 className="m-0 text-sm font-semibold text-ink-2">{config.title}</h3>
        <p className="m-0 text-xs text-muted">{config.description}</p>
      </div>

      <SettingsField label="访问密钥" compact>
        <input
          type="password"
          autoComplete="off"
          value={String(settings[config.apiKeyKey] || "")}
          disabled={desktopManagedSecrets}
          onChange={(event) =>
            controller.setSettingField(
              config.apiKeyKey,
              event.target.value as RuntimeSettings[typeof config.apiKeyKey],
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
          <span className="text-xs text-muted wrap-anywhere">
            {configured ? "该场景已有密钥，解锁后可编辑。" : "该场景还没有密钥。"}
          </span>
        ) : null}
      </SettingsField>
      <SettingsField label="服务地址" compact>
        <input
          value={String(settings[config.baseUrlKey] || "")}
          onChange={(event) =>
            controller.setSettingField(
              config.baseUrlKey,
              event.target.value as RuntimeSettings[typeof config.baseUrlKey],
            )
          }
          placeholder="留空则继承默认服务地址"
        />
      </SettingsField>
      <div className="flex flex-wrap items-center gap-2.5">
        <Button
          data-probe-scope={config.scope}
          data-probe-action="models"
          disabled={probe.loading || desktopManagedSecrets}
          onClick={() => void controller.probeScope(config.scope)}
        >
          {probe.loading ? "验证中…" : "验证模型与当前功能"}
        </Button>
        <span role="status" className="text-xs text-muted wrap-anywhere">
          {formatProbeHint(probe)}
        </span>
      </div>
      <SettingsField label="模型选择">
        <select
          value={String(settings[config.modelKey] || "")}
          onChange={(event) =>
            controller.setSettingField(
              config.modelKey,
              event.target.value as RuntimeSettings[typeof config.modelKey],
            )
          }
        >
          {models.map((modelName) => (
            <option key={modelName} value={modelName}>
              {modelName}
            </option>
          ))}
        </select>
      </SettingsField>
      <div className="grid min-w-0 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            label={
              !probe.lastCheckedAt
                ? "模型列表：未验证"
                : probe.available && modelListed
                  ? "模型列表：已列出"
                  : probe.available
                    ? "模型列表：未列出"
                    : "模型列表：拉取失败"
            }
            tone={
              probe.available && modelListed
                ? "positive"
                : probe.lastCheckedAt
                  ? "negative"
                  : "muted"
            }
          />
          <StatusBadge
            label={
              !probe.lastCheckedAt
                ? "鉴权：未验证"
                : authenticationPassed
                  ? "鉴权：已通过"
                  : "鉴权：未确认"
            }
            tone={
              authenticationPassed
                ? "positive"
                : probe.lastCheckedAt
                  ? "negative"
                  : "muted"
            }
          />
        </div>
        <p className="m-0 text-xs text-muted">
          代表请求只检查连接与请求兼容性，不验证工具实际执行或完整工作流输出。
        </p>
        {featureLabels.map(([feature, label]) => {
          const readiness = probe.featureReadiness[feature];
          const current = readiness?.model === currentModel ? readiness : undefined;
          return (
            <div key={feature} className="grid min-w-0 gap-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  label={`${label}：${
                    current?.status === "ready"
                      ? "代表请求已返回"
                      : current?.status === "unsupported"
                        ? "参数不兼容"
                        : current?.status === "failed"
                          ? "调用失败"
                          : "未验证"
                  }`}
                  tone={
                    current?.status === "ready"
                      ? "positive"
                      : current
                        ? "negative"
                        : "muted"
                  }
                />
              </div>
              {current?.note ? (
                <p className="m-0 text-xs text-muted wrap-anywhere">{current.note}</p>
              ) : null}
              {current?.parameterAdjustments.length ? (
                <p className="m-0 text-xs text-ink-2 wrap-anywhere">
                  显式参数适配：{current.parameterAdjustments.join("、")}
                </p>
              ) : null}
              {current?.code ? (
                <p className="m-0 text-xs text-ink-2 wrap-anywhere">
                  原因代码：{current.code}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
