// Shared within the WebView, so an old settings page cannot race a new page's vault action.
export function createVaultQueue() {
  let tail: Promise<unknown> = Promise.resolve();
  return function enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const result = tail.then(operation);
    tail = result.catch(() => undefined);
    return result;
  };
}

export const enqueueVaultOperation = createVaultQueue();

interface VaultSave<T, Secrets> {
  read: () => Promise<Secrets>;
  store: (value: Secrets) => Promise<unknown>;
  apply: (value: Secrets) => Promise<unknown>;
  commit: () => Promise<T>;
}

export async function saveWithVault<T, Secrets>(
  port: VaultSave<T, Secrets>,
  value: Secrets,
) {
  const previous = await port.read();
  let sessionAttempted = false;
  try {
    await port.store(value);
    sessionAttempted = true;
    await port.apply(value);
    return await port.commit();
  } catch (error) {
    // An error can be reported after a partial mutation or after losing the response.
    const failures: string[] = [];
    if (sessionAttempted) {
      try {
        await port.apply(previous);
      } catch {
        failures.push("运行时密钥");
      }
    }
    try {
      await port.store(previous);
    } catch {
      failures.push("保险库");
    }
    if (failures.length) {
      throw new Error(
        `设置保存失败；无法确认${failures.join("、")}已恢复。请锁定保险库并重新检查。`,
        { cause: error },
      );
    }
    throw new Error("设置保存未获确认，密钥已恢复。请重试或刷新设置。", {
      cause: error,
    });
  }
}
