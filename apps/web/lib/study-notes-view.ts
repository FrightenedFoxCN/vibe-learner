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
