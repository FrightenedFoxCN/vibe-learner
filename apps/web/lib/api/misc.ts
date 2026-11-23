import { DiagnosticContext as DiagnosticContext } from "../diagnostics";

import { AI_BASE_URL, request, readJson } from "./_shared";

export async function cancelStreamRun(
  streamId: string,
  context?: DiagnosticContext,
): Promise<void> {
  await readJson<{ stream_id: string }>(
    await request(
      `${AI_BASE_URL()}/stream-runs/${streamId}/cancel`,
      {
        method: "POST",
      },
      context,
    ),
  );
}
