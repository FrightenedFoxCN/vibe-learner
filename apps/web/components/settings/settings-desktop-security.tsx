import { useState } from "react";
import { Alert } from "../ui/alert";
import { Button } from "../ui/button";
import { SettingsField, SettingsPanel, StatusBadge } from "./settings-ui";
import type { SettingsController } from "./use-settings-controller";

export function StartupRequirementCard({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="grid min-w-0 gap-3 border border-solid border-negative/35 bg-negative/5 p-4.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <StatusBadge label="启动提示" tone="negative" />
        <span className="text-xs text-muted wrap-anywhere">
          当前桌面会话还没有完成必需的安全配置。
        </span>
      </div>
      <div className="grid min-w-0 content-start gap-2.5 border border-solid border-border bg-bg p-3.5">
        <h2 className="m-0 text-lg font-semibold text-ink">{title}</h2>
        <p className="m-0 text-sm text-muted wrap-anywhere">{description}</p>
      </div>
    </section>
  );
}

export function DesktopSecurityCard({
  controller,
}: {
  controller: SettingsController;
}) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  if (!controller.desktopSecurity.enabled) {
    return null;
  }

  const isUnconfigured = controller.desktopSecurity.vaultState === "unconfigured";
  const isUnlocked = controller.desktopSecurity.vaultState === "unlocked";
  const isBusy = controller.desktopSecurity.busy;

  return (
    <SettingsPanel>
      <h2 className="m-0 text-lg font-semibold text-ink">桌面密钥库</h2>
      <div className="grid min-w-0 content-start gap-2.5 border border-solid border-border bg-bg p-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <StatusBadge
            label={`Vault：${isUnconfigured ? "未初始化" : isUnlocked ? "已解锁" : "已锁定"}`}
            tone={isUnlocked ? "positive" : "muted"}
          />
          <span className="text-xs text-muted wrap-anywhere">
            {controller.desktopSecurity.vaultPath || "未发现 vault 路径"}
          </span>
        </div>

        {controller.desktopSecurity.error ? (
          <Alert variant="negative">操作失败：{controller.desktopSecurity.error}</Alert>
        ) : null}

        {controller.desktopSecurity.startupError ? (
          <Alert variant="negative">
            桌面后端启动失败：{controller.desktopSecurity.startupError}
          </Alert>
        ) : null}

        {!isUnlocked ? (
          <>
            <SettingsField label="主密码">
              <input
                type="password"
                autoComplete="off"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少使用一个你能记住的高强度密码"
              />
            </SettingsField>

            {isUnconfigured ? (
              <SettingsField label="确认密码">
                <input
                  type="password"
                  autoComplete="off"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="再次输入主密码"
                />
              </SettingsField>
            ) : null}

            <div className="flex flex-wrap items-center gap-2.5">
              <Button
                disabled={
                  isBusy ||
                  !password.trim() ||
                  (isUnconfigured && password !== confirmPassword)
                }
                onClick={() =>
                  void (isUnconfigured
                    ? controller.initializeDesktopVault(password)
                    : controller.unlockDesktopVault(password))
                }
              >
                {isBusy ? "处理中…" : isUnconfigured ? "创建并解锁" : "解锁"}
              </Button>
              {isUnconfigured &&
              password &&
              confirmPassword &&
              password !== confirmPassword ? (
                <span className="text-xs text-muted wrap-anywhere">
                  两次输入的密码不一致。
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2.5">
            <Button
              disabled={isBusy}
              onClick={() => void controller.lockDesktopVault()}
            >
              {isBusy ? "处理中…" : "锁定"}
            </Button>
            <Button
              variant="danger"
              disabled={isBusy}
              onClick={() => void controller.clearDesktopSecrets()}
            >
              清空已保存密钥
            </Button>
            <span className="text-xs text-muted wrap-anywhere">
              锁定后会清除本次运行中的密钥。
            </span>
          </div>
        )}
      </div>
    </SettingsPanel>
  );
}
