export function logWorkspaceInfo(stage: string, payload: Record<string, unknown>) {
  console.info(`[gal-learner] ${stage}`, payload);
}

export function logWorkspaceError(stage: string, error: unknown) {
  console.error(`[gal-learner] ${stage}`, error);
}
