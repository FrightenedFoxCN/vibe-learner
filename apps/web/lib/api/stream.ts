import { consumeVersionedStream, StreamDecodeError } from "../stream-decode";
import { withDecodeDiagnostics } from "./_shared";

export async function consumeDiagnosticStream(
  response: Response,
  isProjectionDecodeError: (error: unknown) => boolean,
  ...args: Parameters<typeof consumeVersionedStream>
) {
  return withDecodeDiagnostics(
    response,
    () => consumeVersionedStream(...args),
    (error) => error instanceof StreamDecodeError || isProjectionDecodeError(error),
  );
}

export function formatStreamErrorPayload(
  payload: Record<string, unknown> | undefined,
  fallbackCode: string,
): string {
  const detail = String(payload?.detail ?? payload?.error ?? fallbackCode);
  const internal = payload?.internal_error_code;
  const statusCode = payload?.status_code;
  const retryAttempts = payload?.retry_attempts;
  const suffixParts: string[] = [];
  if (internal) {
    suffixParts.push(`internal=${String(internal)}`);
  }
  if (statusCode) {
    suffixParts.push(`status=${String(statusCode)}`);
  }
  if (typeof retryAttempts === "number" && retryAttempts > 1) {
    suffixParts.push(`retries=${String(retryAttempts - 1)}`);
  }
  if (!suffixParts.length) {
    return detail;
  }
  return `${detail} (${suffixParts.join(", ")})`;
}
