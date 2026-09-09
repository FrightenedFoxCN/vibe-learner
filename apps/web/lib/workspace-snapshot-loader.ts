import type { DocumentRecord, LearningPlan, PersonaProfile } from "@vibe-learner/shared";
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
  }

  async load(includePersonas: boolean, observer: WorkspaceSnapshotObserver): Promise<void> {
    if (!this.active) return;
    const revision = ++this.revision;
    const current = () => this.active && revision === this.revision;
    const needsPersonas = includePersonas || !this.personasLoaded;
    observer.started();
    try {
      const [documents, plans, personas] = await Promise.all([
        this.sources.listDocuments(),
        this.sources.listLearningPlans(),
        needsPersonas ? this.sources.listPersonas() : Promise.resolve(undefined),
      ]);
      if (!current()) return;
      observer.loaded({ documents, plans, ...(personas === undefined ? {} : { personas }) });
      if (needsPersonas) this.personasLoaded = true;
    } catch (error) {
      if (current()) observer.failed(error);
    } finally {
      if (current()) observer.finished();
    }
  }
}
