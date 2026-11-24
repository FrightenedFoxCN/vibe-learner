type RecoveryStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type SharedStorage = RecoveryStorage & Pick<Storage, "length" | "key">;

function validId(id: string | null): id is string {
  return id !== null && /^[A-Za-z0-9._:-]{1,80}$/.test(id);
}

export function planRevisionRecovery(
  planId: string,
  shared: SharedStorage,
  tab: RecoveryStorage,
) {
  const legacyKey = `vibe-learner:plan-revision:v1:${planId}`;
  const tabKey = `vibe-learner:plan-revision:v2:current:${encodeURIComponent(planId)}`;
  const prefix = `vibe-learner:plan-revision:v2:request:${encodeURIComponent(planId)}:`;
  const key = (id: string) => prefix + id;
  const dismissedKey = (id: string) => `${prefix}dismissed/${id}`;

  // The old plan-wide slot has no owner. Import it on explicit selection, but
  // never write or delete the shared slot: an older tab could still replace it.
  function available(id: string) {
    if (shared.getItem(dismissedKey(id)) !== null) return false;
    const value = shared.getItem(key(id));
    return value === "saved" || value === "legacy" || shared.getItem(legacyKey) === id;
  }

  return {
    current() {
      const id = tab.getItem(tabKey);
      // A selection belongs to this tab, even if another tab dismissed its
      // own selection of the same ID (for example after duplicating a tab).
      return validId(id) ? id : "";
    },
    list() {
      const ids = new Set<string>();
      const legacy = shared.getItem(legacyKey);
      if (validId(legacy) && available(legacy)) ids.add(legacy);
      for (let i = 0; i < shared.length; i++) {
        const storedKey = shared.key(i);
        if (!storedKey?.startsWith(prefix)) continue;
        const id = storedKey.slice(prefix.length);
        if (validId(id) && available(id)) ids.add(id);
      }
      return [...ids].sort();
    },
    select(id: string) {
      if (!validId(id) || !available(id)) return false;
      if (shared.getItem(key(id)) === null) {
        shared.setItem(key(id), "legacy");
        if (!available(id)) return false;
      }
      tab.setItem(tabKey, id);
      return true;
    },
    remember(id: string) {
      if (!validId(id) || available(id) || shared.getItem(dismissedKey(id)) !== null) {
        throw new Error("Invalid or already saved plan revision request ID");
      }
      shared.setItem(key(id), "saved");
      try {
        tab.setItem(tabKey, id);
      } catch (error) {
        shared.removeItem(key(id));
        throw error;
      }
    },
    clear(id: string) {
      if (!validId(id)) return;
      if (shared.getItem(legacyKey) === id || shared.getItem(key(id)) === "legacy") {
        // A separate, scoped dismissal also wins over a concurrent legacy import.
        shared.setItem(dismissedKey(id), "1");
      }
      shared.removeItem(key(id));
      if (tab.getItem(tabKey) === id) tab.removeItem(tabKey);
    },
  };
}
