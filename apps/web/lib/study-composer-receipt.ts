/** Clear only a mounted, unchanged draft, and consume the callback only once. */
export function whenStudyDraftCommitted(
  version: { current: object | null },
  clear: () => void,
): () => void {
  const submitted = version.current;
  return () => {
    if (!submitted || version.current !== submitted) return;
    version.current = null;
    clear();
  };
}

export function isExactStudyCommit(
  receipt: {
    sessionId: string;
    clientRequestId: string;
    status: string;
    result?: unknown;
  },
  draft: { sessionId: string; clientRequestId: string },
): boolean {
  return (
    receipt.status === "committed" &&
    Boolean(receipt.result) &&
    receipt.sessionId === draft.sessionId &&
    receipt.clientRequestId === draft.clientRequestId
  );
}
