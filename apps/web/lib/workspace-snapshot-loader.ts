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
    completion: Promise<void>;
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

  // Focus signals do not require a new snapshot while an owned read is already
  // underway. Explicit refresh still calls load() and fences older projections.
  loadOnFocus(observer: WorkspaceSnapshotObserver): Promise<void> {
    if (!this.active) return Promise.resolve();
    return this.pending?.completion ?? this.load(false, observer);
  }

  load(includePersonas: boolean, observer: WorkspaceSnapshotObserver): Promise<void> {
    if (!this.active) return Promise.resolve();
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
    this.pending = { revision, includesPersonas: needsPersonas, completion };
    return completion;
  }

  private async read(
    revision: number,
    needsPersonas: boolean,
    personaVersion: number,
    observer: WorkspaceSnapshotObserver,
  ): Promise<void> {
    const current = () => this.active && revision === this.revision;
    try {
      const [documents, plans, personas] = await Promise.all([
        this.sources.listDocuments(),
        this.sources.listLearningPlans(),
        needsPersonas ? this.sources.listPersonas() : Promise.resolve(undefined),
      ]);
      if (!current()) return;
      observer.loaded({
        documents,
        plans,
        ...(personas === undefined || personaVersion !== this.personaVersion
          ? {}
          : { personas }),
      });
      if (needsPersonas) this.personasLoaded = true;
    } catch (error) {
      if (current()) observer.failed(error);
    } finally {
      if (current()) observer.finished();
    }
  }
}
