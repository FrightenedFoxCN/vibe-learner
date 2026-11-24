import { useId, useState } from "react";
import { SettingsField } from "./settings-ui";
import { NUMERIC_SETTING_CONFIGS, type NumericSettingKey } from "./settings-utils";
import type { SettingsController } from "./use-settings-controller";

export function SettingsNumericField({
  controller,
  name,
  label,
  hint,
}: {
  controller: SettingsController;
  name: NumericSettingKey;
  label: string;
  hint?: string;
}) {
  const id = useId();
  const [invalidDraft, setInvalidDraft] = useState<string | null>(null);
  const config = NUMERIC_SETTING_CONFIGS[name];
  const value = controller.numericDrafts[name];
  const invalid = invalidDraft !== null && value === invalidDraft;
  return (
    <SettingsField label={label}>
      <input
        type="text"
        inputMode={config.integer ? "numeric" : "decimal"}
        aria-label={label}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? id + "-hint " + id + "-error" : id + "-hint"}
        value={value}
        onChange={(event) => {
          setInvalidDraft(null);
          controller.setNumericDraft(name, event.target.value);
        }}
        onBlur={(event) => {
          const draft = event.currentTarget.value;
          setInvalidDraft(controller.commitNumericSetting(name) ? null : draft);
        }}
      />
      <span id={id + "-hint"} className="text-xs text-muted">
        范围 {config.min}–{config.max}，默认 {config.default}。{hint}
      </span>
      {invalid && (
        <span id={id + "-error"} role="alert" className="text-xs">
          请输入范围内的{config.integer ? "整数" : "数值"}
          。本次输入未保存，原设置保持不变。
        </span>
      )}
    </SettingsField>
  );
}
