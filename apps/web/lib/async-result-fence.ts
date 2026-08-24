export interface AsyncResultScope {
  subjectId: string;
  draftRevision: number;
  fieldTarget: string;
}

export interface AsyncResultTicket extends AsyncResultScope {
  operationId: string;
  attemptSequence: number;
}

interface ActiveAsyncResultIdentity {
  operationId: string;
  attemptSequence: number;
}

export type AsyncResultDecision =
  | "apply"
  | "operation_mismatch"
  | "operation_superseded"
  | "subject_changed"
  | "draft_changed"
  | "field_target_changed";

function requireScope(scope: AsyncResultScope): void {
  if (!scope.subjectId.trim()) {
    throw new Error("async_result_subject_required");
  }
  if (!Number.isSafeInteger(scope.draftRevision) || scope.draftRevision < 0) {
    throw new Error("async_result_draft_revision_invalid");
  }
  if (!scope.fieldTarget.trim()) {
    throw new Error("async_result_field_target_required");
  }
}

export function decideAsyncResult(
  ticket: AsyncResultTicket,
  current: AsyncResultScope,
  activeIdentity: ActiveAsyncResultIdentity | null,
  resultOperationId = ticket.operationId,
): AsyncResultDecision {
  requireScope(ticket);
  requireScope(current);
  if (resultOperationId !== ticket.operationId) return "operation_mismatch";
  if (
    activeIdentity?.operationId !== ticket.operationId ||
    activeIdentity.attemptSequence !== ticket.attemptSequence
  ) {
    return "operation_superseded";
  }
  if (current.subjectId !== ticket.subjectId) return "subject_changed";
  if (current.draftRevision !== ticket.draftRevision) return "draft_changed";
  if (current.fieldTarget !== ticket.fieldTarget) return "field_target_changed";
  return "apply";
}

export class AsyncResultFence {
  private sequence = 0;
  private activeIdentity: ActiveAsyncResultIdentity | null = null;

  begin(scope: AsyncResultScope, operationId?: string): AsyncResultTicket {
    requireScope(scope);
    const attemptSequence = ++this.sequence;
    const nextOperationId = operationId === undefined
      ? `frontend-async-${attemptSequence}`
      : operationId.trim();
    if (!nextOperationId) {
      throw new Error("async_result_operation_required");
    }
    this.activeIdentity = {
      operationId: nextOperationId,
      attemptSequence,
    };
    return {
      ...scope,
      operationId: nextOperationId,
      attemptSequence,
    };
  }

  decide(
    ticket: AsyncResultTicket,
    current: AsyncResultScope,
    resultOperationId = ticket.operationId,
  ): AsyncResultDecision {
    return decideAsyncResult(
      ticket,
      current,
      this.activeIdentity,
      resultOperationId,
    );
  }

  settle(ticket: AsyncResultTicket): boolean {
    if (
      this.activeIdentity?.operationId !== ticket.operationId ||
      this.activeIdentity.attemptSequence !== ticket.attemptSequence
    ) {
      return false;
    }
    this.activeIdentity = null;
    return true;
  }

  invalidate(): void {
    this.activeIdentity = null;
  }

  currentOperationId(): string | null {
    return this.activeIdentity?.operationId ?? null;
  }
}

export function applyAsyncResult<T>(input: {
  fence: AsyncResultFence;
  ticket: AsyncResultTicket;
  currentScope: AsyncResultScope;
  value: T;
  apply: (value: T) => void;
  resultOperationId?: string;
}): AsyncResultDecision {
  const decision = input.fence.decide(
    input.ticket,
    input.currentScope,
    input.resultOperationId,
  );
  if (decision === "apply") {
    input.apply(input.value);
  }
  return decision;
}

export interface StudyViewSessionProjection {
  id: string;
  studyUnitId: string;
}

export class StudyAsyncViewFence<Session extends StudyViewSessionProjection> {
  session: Session | null;
  viewRevision = 0;
  private fieldTarget: string;
  private readonly resultFence = new AsyncResultFence();

  constructor(input: { initialPlanId?: string; session?: Session | null } = {}) {
    this.session = input.session ?? null;
    this.fieldTarget = this.session
      ? this.sessionTarget(this.session)
      : this.planTarget(input.initialPlanId ?? "");
  }

  private planTarget(planId: string): string {
    return `study-plan:${planId.trim() || "none"}`;
  }

  private sessionTarget(session: Session): string {
    return `study-session:${session.id}:unit:${session.studyUnitId}`;
  }

  transition(fieldTarget: string, clearSession = false): void {
    this.viewRevision += 1;
    this.fieldTarget = fieldTarget;
    this.resultFence.invalidate();
    if (clearSession) {
      this.session = null;
    }
  }

  activateSession(session: Session): boolean {
    const identityChanged =
      this.session?.id !== session.id ||
      this.session?.studyUnitId !== session.studyUnitId;
    if (identityChanged) {
      this.transition(this.sessionTarget(session));
    } else {
      this.fieldTarget = this.sessionTarget(session);
    }
    this.session = session;
    return identityChanged;
  }

  currentScope(selectedPlanId: string): AsyncResultScope {
    return {
      subjectId: this.session?.id || this.planTarget(selectedPlanId),
      draftRevision: this.viewRevision,
      fieldTarget: this.fieldTarget,
    };
  }

  begin(
    sessionId: string,
    operationId: string,
  ): AsyncResultTicket {
    return this.resultFence.begin(
      {
        subjectId: sessionId,
        draftRevision: this.viewRevision,
        fieldTarget: this.fieldTarget,
      },
      operationId,
    );
  }

  decide(
    ticket: AsyncResultTicket,
    selectedPlanId: string,
    resultOperationId = ticket.operationId,
  ): AsyncResultDecision {
    return this.resultFence.decide(
      ticket,
      this.currentScope(selectedPlanId),
      resultOperationId,
    );
  }

  settle(ticket: AsyncResultTicket): boolean {
    return this.resultFence.settle(ticket);
  }
}
