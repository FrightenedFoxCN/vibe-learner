import type { TokenUsageStats } from "@vibe-learner/shared";
import { SETTINGS_RESPONSE_CONTRACTS } from "@vibe-learner/shared/settings-response-contracts";
import {
  modelResponseDecoder,
  responseEnvelope,
  legacyField,
  ModelResponseDecodeError,
} from "./model-response-decode.ts";
const d = modelResponseDecoder("model_usage");

export function decodeModelUsageStats(raw: unknown): TokenUsageStats {
  const p = "model_usage";
  const { value: v, legacy } = responseEnvelope(
    raw,
    p,
    SETTINGS_RESPONSE_CONTRACTS.modelUsage,
    d,
  );
  function counts(value: Record<string, unknown>, path: string) {
    return {
      promptTokens: d.integer(
        d.field(value, "prompt_tokens", path),
        `${path}.prompt_tokens`,
      ),
      completionTokens: d.integer(
        d.field(value, "completion_tokens", path),
        `${path}.completion_tokens`,
      ),
      totalTokens: d.integer(
        d.field(value, "total_tokens", path),
        `${path}.total_tokens`,
      ),
    };
  }
  const buckets = d.array(
    d.field(v, "buckets", p),
    `${p}.buckets`,
    (raw, path) => {
      const b = d.record(raw, path);
      return {
        date: d.string(d.field(b, "date", path), `${path}.date`),
        feature: d.string(d.field(b, "feature", path), `${path}.feature`),
        model: d.string(d.field(b, "model", path), `${path}.model`),
        ...counts(b, path),
      };
    },
  );
  d.unique(
    buckets.map((b) => JSON.stringify([b.date, b.feature, b.model])),
    `${p}.buckets`,
  );
  const records = d.array(
    legacyField(v, "records", p, legacy, [], d),
    `${p}.records`,
    (raw, path) => {
      const r = d.record(raw, path);
      const string = (key: string) =>
        d.string(d.field(r, key, path), `${path}.${key}`);
      const correlation = (key: string) =>
        d.string(
          legacyField(r, key, path, legacy, "", d),
          `${path}.${key}`,
          true,
        );
      return {
        id: string("id"),
        createdAt: string("created_at"),
        feature: string("feature"),
        model: string("model"),
        operationId: correlation("operation_id"),
        workflow: correlation("workflow"),
        stage: correlation("stage"),
        ...counts(r, path),
      };
    },
  );
  d.unique(
    records.map((r) => r.id),
    `${p}.records`,
  );
  const totals = {
    totalPromptTokens: d.integer(
      d.field(v, "total_prompt_tokens", p),
      `${p}.total_prompt_tokens`,
    ),
    totalCompletionTokens: d.integer(
      d.field(v, "total_completion_tokens", p),
      `${p}.total_completion_tokens`,
    ),
    totalTokens: d.integer(d.field(v, "total_tokens", p), `${p}.total_tokens`),
  };
  // The API returns all filtered records; each provider counter is independent.
  // Provider total_tokens need not equal prompt_tokens + completion_tokens.
  for (const [key, total] of [
    ["promptTokens", totals.totalPromptTokens],
    ["completionTokens", totals.totalCompletionTokens],
    ["totalTokens", totals.totalTokens],
  ] as const) {
    if (
      buckets.reduce((sum, bucket) => sum + bucket[key], 0) !== total ||
      ((!legacy || Object.hasOwn(v, "records")) &&
        records.reduce((sum, record) => sum + record[key], 0) !== total)
    ) {
      throw new ModelResponseDecodeError(
        "model_usage",
        `${p}.${key}`,
        "aggregate_mismatch",
      );
    }
  }
  return { buckets, records, ...totals };
}
