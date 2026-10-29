import { StrictResponseDecoder } from "./strict-response-decode.ts";

type Domain =
  | "runtime_settings"
  | "model_tool_config"
  | "runtime_model_probe"
  | "model_usage";

export class ModelResponseDecodeError extends Error {
  readonly code: string;
  readonly domain: Domain;
  readonly path: string;
  readonly reason: string;
  constructor(domain: Domain, path: string, reason: string) {
    super(`${domain}: ${reason} at ${path}`);
    this.domain = domain;
    this.path = path;
    this.reason = reason;
    this.name = "ModelResponseDecodeError";
    this.code = `${domain}_response_decode_error`;
  }
}

export function modelResponseDecoder(domain: Domain) {
  return new StrictResponseDecoder((path, reason) => {
    // Enum failures must not echo a credential or provider-controlled value.
    const safeReason = reason.startsWith("unexpected_enum_")
      ? "unexpected_enum"
      : reason.startsWith("identity_mismatch_")
        ? "identity_mismatch"
        : reason;
    throw new ModelResponseDecodeError(domain, path, safeReason);
  });
}

export function responseEnvelope(
  raw: unknown,
  path: string,
  contract: string,
  d: StrictResponseDecoder,
) {
  const value = d.record(raw, path);
  const legacy = !Object.hasOwn(value, "contract_version");
  if (!legacy)
    d.equal(value.contract_version, contract, `${path}.contract_version`);
  return { value, legacy };
}

/** Defaults apply only to absent fields in an unversioned historical response. */
export function legacyField(
  value: Record<string, unknown>,
  key: string,
  path: string,
  legacy: boolean,
  fallback: unknown,
  d: StrictResponseDecoder,
): unknown {
  return legacy && !Object.hasOwn(value, key)
    ? fallback
    : d.field(value, key, path);
}
