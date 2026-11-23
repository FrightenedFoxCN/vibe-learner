import type { RuntimeSettings } from "@vibe-learner/shared";
import { Button } from "../ui/button";
import { SettingsPanel, SettingsToggle, StatusBadge } from "./settings-ui";
import {
  CAPABILITY_AUDIT_CONFIGS,
  capabilitySignalToBoolean,
  formatCapabilityDecisionNote,
  formatCapabilitySource,
  formatCapabilityStatus,
  resolveCapabilitySignal,
} from "./settings-utils";
import type { SettingsController } from "./use-settings-controller";

export function CapabilityAuditCard({
  controller,
  settings,
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <SettingsPanel>
      <h2 className="m-0 text-lg font-semibold text-ink">能力对照与回填</h2>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15.625rem),1fr))] gap-3">
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
          const showModalities =
            capability?.inputModalities?.length || capability?.outputModalities?.length;

          return (
            <section
              key={config.scope}
              className="grid min-w-0 content-start gap-2.5 border border-solid border-border bg-bg p-3.5"
            >
              <div className="grid gap-1">
                <h3 className="m-0 text-sm font-semibold text-ink">{config.title}</h3>
                <p className="m-0 text-xs text-muted">{config.description}</p>
              </div>

              <div className="text-sm text-ink-2 wrap-anywhere">
                当前模型：<strong>{modelName || "未设置"}</strong>
              </div>

              <SettingsToggle>
                <input
                  type="checkbox"
                  checked={manualValue}
                  onChange={(event) =>
                    controller.setSettingField(
                      config.manualKey,
                      event.target.checked as RuntimeSettings[typeof config.manualKey],
                    )
                  }
                />
                <span>{config.manualLabel}</span>
              </SettingsToggle>

              <div className="grid min-w-0 gap-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    label={`检测结果：${formatCapabilityStatus(signal)}`}
                    tone={toneForStatus(signal.status)}
                  />
                  <StatusBadge
                    label={sourceText}
                    tone={signal.source === "metadata" ? "positive" : "muted"}
                  />
                  {mismatch ? (
                    <StatusBadge label="开关与检测不一致" tone="negative" />
                  ) : null}
                </div>
                {formatCapabilityDecisionNote(signal) ? (
                  <p className="m-0 text-xs text-muted wrap-anywhere">
                    {formatCapabilityDecisionNote(signal)}
                  </p>
                ) : null}
                {showModalities ? (
                  <div className="m-0 text-xs text-ink-2 wrap-anywhere">
                    输入模态：{capability?.inputModalities?.join(", ") || "-"}
                    {" · "}
                    输出模态：{capability?.outputModalities?.join(", ") || "-"}
                  </div>
                ) : null}
                {showToolTypes ? (
                  <div className="m-0 text-xs text-ink-2 wrap-anywhere">
                    工具类型：{capability?.toolTypes.join(", ")}
                  </div>
                ) : null}
                {!probe.lastCheckedAt ? (
                  <div className="m-0 text-xs text-ink-2 wrap-anywhere">
                    还没有拉取能力信息。
                  </div>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                <Button
                  disabled={probe.loading}
                  onClick={() => void controller.probeScope(config.scope)}
                >
                  {probe.loading ? "拉取中…" : "刷新能力"}
                </Button>
                <Button
                  disabled={detectedValue === null}
                  onClick={() => controller.syncCapabilitySetting(config.scope)}
                >
                  {signal.source === "model_name" ? "按推断回填" : "按检测回填"}
                </Button>
              </div>
            </section>
          );
        })}
      </div>
    </SettingsPanel>
  );
}

function toneForStatus(
  status: "supported" | "unsupported" | "unknown",
): "positive" | "negative" | "muted" {
  if (status === "supported") {
    return "positive";
  }
  if (status === "unsupported") {
    return "negative";
  }
  return "muted";
}
