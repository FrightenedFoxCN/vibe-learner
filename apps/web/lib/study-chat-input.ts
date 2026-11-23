export function hasStudyLearnerInput(
  message: string,
  attachments: readonly { size: number }[],
): boolean {
  return Boolean(message.trim()) || attachments.some((file) => file.size > 0);
}
