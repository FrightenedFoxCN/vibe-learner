import type { ModelToolConfig } from "@vibe-learner/shared";
import { SETTINGS_RESPONSE_CONTRACTS } from "@vibe-learner/shared/settings-response-contracts";
import {
  modelResponseDecoder,
  responseEnvelope,
  legacyField,
  ModelResponseDecodeError,
} from "./model-response-decode.ts";
const d = modelResponseDecoder("model_tool_config");

export function decodeModelToolConfig(raw: unknown): ModelToolConfig {
  const p = "model_tool_config";
  const { value: v, legacy } = responseEnvelope(
    raw,
    p,
    SETTINGS_RESPONSE_CONTRACTS.modelTools,
    d,
  );
  const stages = d.array(
    d.field(v, "stages", p),
    `${p}.stages`,
    (raw, path) => {
      const value = d.record(raw, path);
      const string = (key: string, empty = false) =>
        d.string(d.field(value, key, path), `${path}.${key}`, empty);
      const stageEnabled = d.boolean(
        d.field(value, "stage_enabled", path),
        `${path}.stage_enabled`,
      );
      const tools = d.array(
        d.field(value, "tools", path),
        `${path}.tools`,
        (raw, tp) => {
          const t = d.record(raw, tp);
          const string = (key: string, empty = false) =>
            d.string(d.field(t, key, tp), `${tp}.${key}`, empty);
          const boolean = (key: string) =>
            d.boolean(d.field(t, key, tp), `${tp}.${key}`);
          const enabled = boolean("enabled"),
            available = boolean("available"),
            effectiveEnabled = boolean("effective_enabled");
          if (
            effectiveEnabled !== (enabled && available && stageEnabled) ||
            (available && !stageEnabled)
          )
            throw new ModelResponseDecodeError(
              "model_tool_config",
              tp,
              "inconsistent_effective_state",
            );
          return {
            name: string("name"),
            label: string("label"),
            description: string("description", true),
            category: string("category"),
            categoryLabel: string("category_label"),
            enabled,
            available,
            effectiveEnabled,
            auditBasis: d.stringArray(
              d.field(t, "audit_basis", tp),
              `${tp}.audit_basis`,
            ),
            unavailableReason: d.string(
              legacyField(t, "unavailable_reason", tp, legacy, "", d),
              `${tp}.unavailable_reason`,
              true,
            ),
          };
        },
      );
      d.unique(
        tools.map((tool) => tool.name),
        `${path}.tools`,
      );
      return {
        name: string("name"),
        label: string("label"),
        description: string("description", true),
        stageEnabled,
        auditBasis: d.stringArray(
          d.field(value, "audit_basis", path),
          `${path}.audit_basis`,
        ),
        stageDisabledReason: d.string(
          legacyField(value, "stage_disabled_reason", path, legacy, "", d),
          `${path}.stage_disabled_reason`,
          true,
        ),
        tools,
      };
    },
  );
  d.unique(
    stages.map((stage) => stage.name),
    `${p}.stages`,
  );
  return {
    updatedAt: d.string(d.field(v, "updated_at", p), `${p}.updated_at`, true),
    stages,
  };
}
