// The root layout tracks completion only, never an editor draft (which can
// contain unreconciled Vault secrets). A returning editor waits for outgoing
// writes before taking the latest confirmed runtime settings as its baseline.
const READY = { pending: false } as const;

export class SettingsWriteHandoff {
  private pending = 0;
  private snapshot: { readonly pending: boolean } = READY;
  private listeners = new Set<() => void>();

  isPending = () => this.pending !== 0;
  getSnapshot = () => this.snapshot;
  getServerSnapshot = () => READY;

  readBaseline<T>(readConfirmed: () => T): T | null {
    return this.isPending() ? null : readConfirmed();
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  track(completion: Promise<unknown>) {
    this.pending++;
    if (this.pending === 1) this.notify();
    const settle = () => {
      this.pending--;
      if (this.pending === 0) this.notify();
    };
    void completion.then(settle, settle);
  }

  private notify() {
    // Each edge has its own identity. React can batch both edges without
    // rendering the busy state; the returning editor still needs to retry admission.
    this.snapshot = { pending: this.isPending() };
    for (const listener of this.listeners) listener();
  }
}
