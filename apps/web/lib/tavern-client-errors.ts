import { decodeTavernHttpError } from "./api";
import { tavernFailureNotice } from "./tavern-copy";

export function recordError(
  error: unknown,
  fallback: string,
  setVisible: (value: string) => void,
  setRaw: (value: string) => void,
) {
  const raw = error instanceof Error ? error.message : String(error);
  setRaw(raw);
  setVisible(friendlyTavernError(error, fallback));
}

export function friendlyTavernError(error: unknown, fallback: string): string {
  const detail = decodeTavernHttpError(error);
  const code = detail?.code ?? "";
  const raw = error instanceof Error ? error.message : String(error);
  const kind =
    raw.includes("tavern_response_decode_error") || / at tavern\./.test(raw)
      ? "decode"
      : raw.includes("Cannot reach AI service")
        ? "network"
        : "other";
  return tavernFailureNotice(code, kind, fallback);
}
