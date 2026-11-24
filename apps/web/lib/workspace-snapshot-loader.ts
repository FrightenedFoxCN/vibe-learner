import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
} from "@vibe-learner/shared";
import type { WorkspaceSnapshot } from "./learning-workspace-state";

export interface WorkspaceSnapshotSources {
  listDocuments: () => Promise<DocumentRecord[]>;
  listLearningPlans: () => Promise<LearningPlan[]>;
  listPersonas: () => Promise<PersonaProfile[]>;
}

export type WorkspaceSnapshotRead =
  | { status: "loaded"; snapshot: WorkspaceSnapshot }
  | { status: "failed" }
  | { status: "superseded" };

export interface WorkspaceSnapshotObserver {
  started: () => void;
  loaded: (snapshot: WorkspaceSnapshot) => void;
  failed: (error: unknown) => void;
  finished: () => void;
}

// Initial load, focus refresh and manual refresh share the same ownership ticket.
// Invalidation fences projections, not server execution: these are query calls.
export class WorkspaceSnapshotLoader {
  private revision = 0;
  private active = true;
  private personasLoaded = false;
  private personaVersion = 0;
  private pending: {
    revision: number;
    includesPersonas: boolean;
    observer: WorkspaceSnapshotObserver;
    completion: Promise<WorkspaceSnapshotRead>;
  } | null = null;

  private readonly sources: WorkspaceSnapshotSources;

  constructor(sources: WorkspaceSnapshotSources) {
    this.sources = sources;
  }

  activate() {
    this.active = true;
  }

  deactivate() {
    this.active = false;
    this.revision += 1;
    this.pending = null;
  }

  isLoadingPersonas(): boolean {
    return this.active && Boolean(this.pending?.includesPersonas);
  }

  acceptPersonas(): void {
    // A separate library update has already published a newer Persona list.
    // A mixed snapshot begun earlier may still contribute Documents/Plans.
    this.personaVersion += 1;
    this.personasLoaded = true;
  }

  acceptWorkspaceWrite(): void {
    // A read started before this write may contain an older revision or retain
    // a deleted row. Replace the whole pending read rather than merging lists.
    const pending = this.pending;
    if (this.active && pending)
      void this.load(pending.includesPersonas, pending.observer);
  }

  // Focus signals do not require a new snapshot while an owned read is already
  // underway. Explicit refresh still calls load() and fences older projections.
  loadOnFocus(observer: WorkspaceSnapshotObserver): Promise<WorkspaceSnapshotRead> {
    if (!this.active) return Promise.resolve({ status: "superseded" });
    return this.pending?.completion ?? this.load(false, observer);
  }

  load(
    includePersonas: boolean,
    observer: WorkspaceSnapshotObserver,
  ): Promise<WorkspaceSnapshotRead> {
    if (!this.active) return Promise.resolve({ status: "superseded" });
    const revision = ++this.revision;
    const needsPersonas = includePersonas || !this.personasLoaded;
    const personaVersion = this.personaVersion;
    observer.started();
    const completion = this.read(
      revision,
      needsPersonas,
      personaVersion,
      observer,
    ).finally(() => {
      if (this.pending?.revision === revision) this.pending = null;
    });
    this.pending = { revision, includesPersonas: needsPersonas, observer, completion };
    return completion;
  }

  private async read(
    revision: number,
    needsPersonas: boolean,
    personaVersion: number,
    observer: WorkspaceSnapshotObserver,
  ): Promise<WorkspaceSnapshotRead> {
    const current = () => this.active && revision === this.revision;
    try {
      const [documents, plans, personas] = await Promise.all([
        this.sources.listDocuments(),
        this.sources.listLearningPlans(),
        needsPersonas ? this.sources.listPersonas() : Promise.resolve(undefined),
      ]);
      if (!current()) return { status: "superseded" };
      const snapshot = {
        documents,
        plans,
        ...(personas === undefined || personaVersion !== this.personaVersion
          ? {}
          : { personas }),
      };
      observer.loaded(snapshot);
      if (needsPersonas) this.personasLoaded = true;
      return { status: "loaded", snapshot };
    } catch (error) {
      if (!current()) return { status: "superseded" };
      observer.failed(error);
      return { status: "failed" };
    } finally {
      if (current()) observer.finished();
    }
  }
}
