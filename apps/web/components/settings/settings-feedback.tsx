import type { RuntimeSettings } from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import { Button } from "../ui/button";
import { SettingsPanel, SettingsToggle, StatusBadge } from "./settings-ui";
import type { SettingsController } from "./use-settings-controller";

export function DebugVisibilityCard({
  controller,
  settings,
}: {
  controller: SettingsController;
  settings: RuntimeSettings;
}) {
  return (
    <SettingsPanel>
      <h2 className="m-0 text-lg font-semibold text-ink">调试信息显示</h2>
      <SettingsToggle>
        <input
          type="checkbox"
          checked={settings.showDebugInfo}
          onChange={(event) =>
            controller.setSettingField("showDebugInfo", event.target.checked)
          }
        />
        <span>显示调试悬浮窗</span>
      </SettingsToggle>
    </SettingsPanel>
  );
}

export function AutoSaveStatusBar({ controller }: { controller: SettingsController }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 border border-solid border-border bg-panel px-3.5 py-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2.5">
        <StatusBadge {...savePhaseBadge(controller.savePhase)} />
        <span role="status" className="text-sm text-ink wrap-anywhere">
          {savePhaseText(controller.savePhase, controller.saveError)}
        </span>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2.5">
        <span className="text-xs text-muted tabular-nums">
          最近保存：
          {controller.lastSavedAt
            ? formatTimestamp(controller.lastSavedAt, { style: "full" })
            : "-"}
        </span>
        {controller.savePhase === "error" ? (
          <Button onClick={controller.retrySave}>重试保存</Button>
        ) : null}
      </div>
    </div>
  );
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
    return "正在保存修改。";
  }
  if (phase === "pending") {
    return "等待保存。";
  }
  if (phase === "error") {
    return `自动保存失败：${error || "未知错误"}`;
  }
  if (phase === "saved") {
    return "已保存。";
  }
  return "";
}
