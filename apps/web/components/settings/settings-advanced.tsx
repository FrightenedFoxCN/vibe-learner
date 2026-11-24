import type { RuntimeSettings } from "@vibe-learner/shared";
import { Button } from "../ui/button";
import { SettingsField, SettingsPanel, SettingsToggle } from "./settings-ui";
import { SettingsNumericField } from "./settings-numeric-field";
import type { SettingsController } from "./use-settings-controller";

export function AdvancedSettingsCard({
  controller,
  settings,
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <SettingsPanel>
      <div className="flex flex-wrap items-center gap-2.5">
        <h2 className="m-0 text-lg font-semibold text-ink">高级运行参数</h2>
        <Button
          aria-expanded={controller.advancedExpanded}
          onClick={() => controller.setAdvancedExpanded(!controller.advancedExpanded)}
        >
          {controller.advancedExpanded ? "收起高级设置" : "展开高级设置"}
        </Button>
      </div>
      {controller.advancedExpanded ? (
        <div className="grid gap-3">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsNumericField
              controller={controller}
              name="openaiSettingTemperature"
              label="人格设定温度"
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatTemperature"
              label="学习对话温度"
            />
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsNumericField
              controller={controller}
              name="openaiSettingMaxTokens"
              label="人格设定最大输出长度"
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatMaxTokens"
              label="学习对话最大输出长度"
            />
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsNumericField
              controller={controller}
              name="openaiChatHistoryMessages"
              label="保留历史消息数"
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatToolMaxRounds"
              label="工具调用最大轮次"
            />
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsField label="向量检索模型">
              <input
                value={settings.openaiEmbeddingModel}
                onChange={(event) =>
                  controller.setSettingField("openaiEmbeddingModel", event.target.value)
                }
              />
            </SettingsField>
            <SettingsField label="计划失败时的降级模型">
              <input
                value={settings.openaiPlanFallbackModel}
                onChange={(event) =>
                  controller.setSettingField(
                    "openaiPlanFallbackModel",
                    event.target.value,
                  )
                }
                placeholder="留空表示不启用"
              />
            </SettingsField>
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,17.5rem),1fr))] gap-2.5">
            <SettingsToggle>
              <input
                type="checkbox"
                checked={settings.openaiPlanFallbackDisableTools}
                onChange={(event) =>
                  controller.setSettingField(
                    "openaiPlanFallbackDisableTools",
                    event.target.checked,
                  )
                }
              />
              <span>降级模型禁用工具链</span>
            </SettingsToggle>
          </div>
        </div>
      ) : null}
    </SettingsPanel>
  );
}
