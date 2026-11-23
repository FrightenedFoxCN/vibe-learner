type FollowUpSnapshot = {
  id: string;
  revision: number;
  pendingFollowUps?: readonly { id: string; status: string }[];
};

export async function readBackFollowUpCancellation<T extends FollowUpSnapshot>(
  before: T,
  targetIds: ReadonlySet<string>,
  read: () => Promise<T>,
): Promise<{ state: "stopped" | "pending"; session: T } | { state: "unknown" }> {
  try {
    const session = await read();
    if (session.id !== before.id || session.revision < before.revision) {
      return { state: "unknown" };
    }
    const stillPending = session.pendingFollowUps?.some(
      (item) => targetIds.has(item.id) && item.status === "pending",
    );
    return { state: stillPending ? "pending" : "stopped", session };
  } catch {
    return { state: "unknown" };
  }
}
