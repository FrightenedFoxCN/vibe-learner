import {
  diagnosticFetch,
  recordDecodeFailure,
  type DiagnosticContext,
} from "../diagnostics";
import { getAiBaseUrl, getDesktopRuntimeConfig } from "../runtime-config";
import { ApiHttpError, extractApiErrorCode } from "../http-error";

function extractErrorMessage(payload: unknown, fallbackMessage: string) {
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    return trimmed || fallbackMessage;
  }
  if (!payload || typeof payload !== "object") {
    return fallbackMessage;
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail ?? record.error ?? record.message;
  if (typeof detail === "string") {
    const trimmed = detail.trim();
    return trimmed || fallbackMessage;
  }
  if (detail && typeof detail === "object") {
    return extractErrorMessage(detail, fallbackMessage);
  }
  if (detail !== undefined && detail !== null) {
    const text = String(detail).trim();
    if (text) {
      return text;
    }
  }
  return fallbackMessage;
}

export const AI_BASE_URL = () => getAiBaseUrl();

export async function request(
  input: string,
  init?: RequestInit,
  context?: DiagnosticContext,
): Promise<Response> {
  try {
    return await diagnosticFetch(input, init, context);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    const startupError = getDesktopRuntimeConfig()?.startupError.trim();
    const detail = startupError ? ` (${startupError})` : "";
    throw new Error(`Cannot reach AI service at ${AI_BASE_URL()}${detail}`);
  }
}

export async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    const fallbackMessage = text.trim() || `HTTP ${response.status}`;
    let message = fallbackMessage;
    let payload: unknown = text;
    try {
      payload = JSON.parse(text) as unknown;
      message = extractErrorMessage(payload, fallbackMessage);
    } catch {
      // Keep the raw body when it is not JSON.
    }
    throw new ApiHttpError({
      status: response.status,
      code: extractApiErrorCode(payload),
      message,
      payload,
    });
  }
  const started = performance.now();
  try {
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof SyntaxError)
      recordDecodeFailure(response, performance.now() - started);
    throw error;
  }
}

export async function withDecodeDiagnostics<T>(
  response: Response,
  decode: () => Promise<T>,
  isDecodeError: (error: unknown) => boolean,
): Promise<T> {
  const started = performance.now();
  try {
    return await decode();
  } catch (error) {
    if (isDecodeError(error))
      recordDecodeFailure(response, performance.now() - started);
    throw error;
  }
}
