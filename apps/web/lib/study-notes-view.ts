import type { StudyNote, StudyNoteInput } from "@vibe-learner/shared";
import { AsyncResultFence, type AsyncResultTicket } from "./async-result-fence.ts";

export type NotesOperation = "list" | "detail" | "write" | "export";

export interface NotesTicket {
  operation: NotesOperation;
  ticket: AsyncResultTicket;
  signal: AbortSignal;
}

/** A keyed Session view owns these channels. Closing a view never cancels a write on the server. */
export class StudyNotesView {
  private readonly channels = new Map<
    NotesOperation,
    {
      fence: AsyncResultFence;
      controller?: AbortController;
    }
  >();

  private readonly sessionId: string;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  begin(operation: NotesOperation, target: string): NotesTicket {
    this.cancel(operation);
    const channel = this.channels.get(operation) ?? { fence: new AsyncResultFence() };
    const controller = new AbortController();
    channel.controller = controller;
    this.channels.set(operation, channel);
    return {
      operation,
      signal: controller.signal,
      ticket: channel.fence.begin({
        subjectId: this.sessionId,
        draftRevision: 0,
        fieldTarget: target,
      }),
    };
  }

  current(token: NotesTicket): boolean {
    const channel = this.channels.get(token.operation);
    return (
      channel?.controller?.signal === token.signal &&
      !token.signal.aborted &&
      channel.fence.decide(token.ticket, {
        subjectId: this.sessionId,
        draftRevision: 0,
        fieldTarget: token.ticket.fieldTarget,
      }) === "apply"
    );
  }

  finish(token: NotesTicket): void {
    if (this.current(token)) {
      const channel = this.channels.get(token.operation);
      channel?.fence.settle(token.ticket);
      if (channel) channel.controller = undefined;
    }
  }

  busy(operation: NotesOperation): boolean {
    return Boolean(this.channels.get(operation)?.fence.currentOperationId());
  }

  cancel(operation: NotesOperation): void {
    const channel = this.channels.get(operation);
    channel?.controller?.abort();
    channel?.fence.invalidate();
  }

  close(): void {
    for (const operation of this.channels.keys()) this.cancel(operation);
  }
}

export interface StudyNoteDraft {
  original: StudyNote | null;
  fields: StudyNoteInput;
  unconfirmed: boolean;
}

export type StudyNoteSaveFailure = {
  kind: "rejected" | "unknown";
  error: string;
  conflictRevision?: number;
};

export type StudyNoteSaveOutcome =
  { kind: "saved"; note: StudyNote } | StudyNoteSaveFailure;

interface StudyNoteSaveReceipt {
  outcome: StudyNoteSaveOutcome;
  nextDraft: StudyNoteDraft;
  refreshList: boolean;
}

type ReadDraft = (sessionId: string) => StudyNoteDraft | null;
type StoreDraft = (sessionId: string, draft: StudyNoteDraft | null) => void;

/** Save receipts outlive a keyed editor, but not its page's draft store. */
class StudyNoteSaveReceipts {
  private readonly saves = new WeakMap<
    StudyNoteDraft,
    { sessionId: string; receipt: StudyNoteSaveReceipt | null }
  >();
  private readonly listeners = new Map<
    string,
    Set<(pending: StudyNoteDraft, receipt: StudyNoteSaveReceipt) => void>
  >();

  private readonly readDraft: ReadDraft;

  constructor(readDraft: ReadDraft) {
    this.readDraft = readDraft;
  }

  pending(draft: StudyNoteDraft | null): boolean {
    return draft !== null && this.saves.get(draft)?.receipt === null;
  }

  begin(sessionId: string, pending: StudyNoteDraft): void {
    this.saves.set(pending, { sessionId, receipt: null });
  }

  settle(
    pending: StudyNoteDraft,
    original: StudyNoteDraft,
    outcome: StudyNoteSaveOutcome,
    storeDraft: StoreDraft,
  ): void {
    const save = this.saves.get(pending);
    if (!save || save.receipt) return;
    const nextDraft =
      outcome.kind === "saved"
        ? draftFromNote(outcome.note)
        : outcome.kind === "rejected"
          ? original
          : pending;
    const receipt = { outcome, nextDraft, refreshList: outcome.kind !== "rejected" };
    save.receipt = receipt;
    if (outcome.kind !== "unknown" && this.readDraft(save.sessionId) === pending) {
      storeDraft(save.sessionId, outcome.kind === "saved" ? null : original);
    }
    for (const listener of this.listeners.get(save.sessionId) ?? []) {
      listener(pending, receipt);
    }
  }

  subscribe(
    sessionId: string,
    readEditor: () => StudyNoteDraft | null,
    receive: (receipt: StudyNoteSaveReceipt, matchesEditor: boolean) => void,
  ): () => void {
    const listeners = this.listeners.get(sessionId) ?? new Set();
    this.listeners.set(sessionId, listeners);
    const listener = (pending: StudyNoteDraft, receipt: StudyNoteSaveReceipt) => {
      receive(receipt, readEditor() === pending);
    };
    listeners.add(listener);
    // The render may have restored the pending draft before the receipt landed,
    // and only committed this subscription after it landed.
    const draft = readEditor();
    const save = draft && this.saves.get(draft);
    if (save?.sessionId === sessionId && save.receipt) receive(save.receipt, true);
    return () => {
      listeners.delete(listener);
      if (!listeners.size) this.listeners.delete(sessionId);
    };
  }
}

const saveReceiptsByStore = new WeakMap<ReadDraft, StudyNoteSaveReceipts>();

export function getStudyNoteSaveReceipts(readDraft: ReadDraft): StudyNoteSaveReceipts {
  let receipts = saveReceiptsByStore.get(readDraft);
  if (!receipts) {
    receipts = new StudyNoteSaveReceipts(readDraft);
    saveReceiptsByStore.set(readDraft, receipts);
  }
  return receipts;
}

export function draftFromNote(note: StudyNote | null): StudyNoteDraft {
  return {
    original: note,
    fields: { title: note?.title ?? "", content: note?.content ?? "" },
    unconfirmed: false,
  };
}

export function isStudyNoteDraftDirty(draft: StudyNoteDraft): boolean {
  return (
    draft.fields.title !== (draft.original?.title ?? "") ||
    draft.fields.content !== (draft.original?.content ?? "")
  );
}

export function rebaseStudyNoteDraft(
  draft: StudyNoteDraft,
  latest: StudyNote,
): StudyNoteDraft {
  if (
    draft.original?.id !== latest.id ||
    draft.original.session_id !== latest.session_id ||
    latest.revision < draft.original.revision
  ) {
    throw new Error("study_note_draft_revision_mismatch");
  }
  return { original: latest, fields: draft.fields, unconfirmed: false };
}
