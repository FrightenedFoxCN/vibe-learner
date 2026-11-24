import type { RuntimeSettings } from "@vibe-learner/shared";
import { MODEL_REQUEST_TOKEN_POLICY } from "@vibe-learner/shared/model-runtime-config";
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
              label="人格与场景设定温度"
              hint={"支持温度的模型才会接收该参数。"}
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatTemperature"
              label="学习对话与酒馆温度"
              hint={"常规请求使用此值；语义恢复会降低温度。"}
            />
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsNumericField
              controller={controller}
              name="openaiSettingMaxTokens"
              label="设定辅助常规输出预算（tokens）"
              hint={`人格短辅助使用此值；人格、场景长结构生成至少保留 ${MODEL_REQUEST_TOKEN_POLICY.structuredGenerationTokens} tokens，恢复可能使用不同预算。`}
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatMaxTokens"
              label="学习对话与酒馆常规输出预算（tokens）"
              hint={`语义恢复的输出预算分别不低于 ${MODEL_REQUEST_TOKEN_POLICY.studyRecoveryMinTokens} / ${MODEL_REQUEST_TOKEN_POLICY.tavernRecoveryMinTokens} tokens。`}
            />
          </div>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3">
            <SettingsNumericField
              controller={controller}
              name="openaiChatHistoryMessages"
              label="学习对话初始历史条数"
              hint={"按消息计数，不是对话轮数，也不删除历史。"}
            />
            <SettingsNumericField
              controller={controller}
              name="openaiChatToolMaxRounds"
              label="学习对话非豁免工具轮次上限"
              hint={"不含豁免工具，也不是总模型请求次数。"}
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
            <SettingsField label="学习计划生成备用模型">
              <input
                value={settings.openaiPlanFallbackModel}
                onChange={(event) =>
                  controller.setSettingField(
                    "openaiPlanFallbackModel",
                    event.target.value,
                  )
                }
                placeholder="留空或与主模型相同则不启用"
              />
              <span className="text-xs text-muted">
                只有主模型最终返回空响应或用尽工具轮次，才尝试切换一次；备用模型沿用本次生成的剩余预算。鉴权、限流、预算不足、结果校验失败和计划修订不触发切换。
              </span>
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
              <span>备用模型禁用工具链</span>
            </SettingsToggle>
          </div>
        </div>
      ) : null}
    </SettingsPanel>
  );
}
