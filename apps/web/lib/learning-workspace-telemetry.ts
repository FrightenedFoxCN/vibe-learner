export function logWorkspaceInfo(stage: string, payload: Record<string, unknown>) {
  console.info(`[vibe-learner] ${stage}`, payload);
}

export function logWorkspaceError(stage: string, error: unknown) {
  console.error(`[vibe-learner] ${stage}`, error);
}
