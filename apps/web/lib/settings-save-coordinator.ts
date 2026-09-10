export type SavePhase = "idle" | "pending" | "saving" | "saved" | "error";

export interface SaveCoordinatorPort<T> {
  serialize: (snapshot: T) => string;
  persist: (snapshot: T) => Promise<T>;
  saved: (snapshot: T, submittedKey: string) => void;
  status: (phase: SavePhase, error: string) => void;
}
export interface SaveScheduler {
  schedule: (callback: () => void, delay: number) => unknown;
  cancel: (handle: unknown) => void;
}
const scheduler: SaveScheduler = {
  schedule: (callback, delay) => setTimeout(callback, delay),
  cancel: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

// Owns one serialized save queue. A navigation flush keeps draining the latest
// edit even after its React owner has unmounted; failed snapshots never retry
// automatically. Persistence/secret handling remains with the domain adapter.
export class SettingsSaveCoordinator<T> {
  private port: SaveCoordinatorPort<T>;
  private scheduler: SaveScheduler;
  private delay: number;
  private savedKey = "";
  private blockedKey = "";
  private pending: { snapshot: T; key: string } | null = null;
  private runningKey: string | null = null;
  private timer: unknown = null;
  private flushing = false;

  constructor(port: SaveCoordinatorPort<T>, delay: number, clock: SaveScheduler = scheduler) {
    this.port = port;
    this.delay = delay;
    this.scheduler = clock;
  }

  acceptSaved(snapshot: T) {
    this.savedKey = this.port.serialize(snapshot);
  }

  edit(snapshot: T) {
    const key = this.port.serialize(snapshot);
    // Unrelated renders must not restart the debounce.
    if (this.pending?.key === key) return;
    this.clearTimer();
    if (key === this.blockedKey) {
      this.pending = null;
      if (this.runningKey === null) this.port.status("error", "");
      return;
    }
    if (this.runningKey === null && key === this.savedKey) {
      this.pending = null;
      this.port.status("saved", "");
      return;
    }
    this.pending = { snapshot, key };
    if (this.runningKey === null) this.schedule();
  }

  retry(snapshot: T) {
    this.blockedKey = "";
    this.pending = { snapshot, key: this.port.serialize(snapshot) };
    this.flush();
  }

  flush() {
    this.clearTimer();
    this.flushing = true;
    if (this.runningKey === null) void this.drain();
  }

  private clearTimer() {
    if (this.timer !== null) this.scheduler.cancel(this.timer);
    this.timer = null;
  }

  private schedule() {
    this.port.status("pending", "");
    this.timer = this.scheduler.schedule(() => {
      this.timer = null;
      void this.drain();
    }, this.delay);
  }

  private async drain() {
    const pending = this.pending;
    if (!pending || this.runningKey !== null) {
      if (this.runningKey === null) this.flushing = false;
      return;
    }
    this.pending = null;
    this.runningKey = pending.key;
    this.port.status("saving", "");
    try {
      const next = await this.port.persist(pending.snapshot);
      this.savedKey = this.port.serialize(next);
      this.blockedKey = "";
      this.port.saved(next, pending.key);
      this.port.status("saved", "");
    } catch (error) {
      this.blockedKey = pending.key;
      this.port.status("error", String(error));
    } finally {
      this.runningKey = null;
      const next = this.pending as { snapshot: T; key: string } | null;
      if (next && (next.key === this.savedKey || next.key === this.blockedKey)) this.pending = null;
      if (this.pending) {
        if (this.flushing) void this.drain();
        else this.schedule();
      } else {
        this.flushing = false;
      }
    }
  }
}
