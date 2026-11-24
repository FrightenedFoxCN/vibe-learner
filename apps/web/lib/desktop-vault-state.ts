import type { DesktopVaultState } from "@vibe-learner/shared";

type VaultSession = {
  stronghold: { save(): Promise<void>; unload(): Promise<void> };
};

// Native config describes the file at page load, not the WebView's open handle.
export function createDesktopVaultSession<T extends VaultSession>(
  readBootstrap: () => DesktopVaultState | null,
) {
  let session: T | null = null;
  let configuredHere = false;
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((listener) => listener());

  return {
    getSnapshot(): DesktopVaultState | null {
      if (session) return "unlocked";
      if (configuredHere) return "locked";
      const bootstrap = readBootstrap();
      // Only a live Stronghold handle can mean unlocked.
      return bootstrap === "unlocked" ? "locked" : bootstrap;
    },
    getSession: () => session,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async activate(next: T, mode: "initialize" | "unlock") {
      if (mode === "initialize") {
        try {
          await next.stronghold.save();
        } catch (error) {
          await next.stronghold.unload().catch(() => undefined);
          throw error;
        }
      }
      configuredHere = true;
      session = next;
      notify();
    },
    async lock() {
      const previous = session;
      if (!previous) return;
      session = null;
      notify();
      await previous.stronghold.unload();
    },
  };
}
