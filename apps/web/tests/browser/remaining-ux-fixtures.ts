import { test as base, expect, type Request } from "@playwright/test";
import responses from "../../../../packages/shared/fixtures/settings/responses-v1.json" with { type: "json" };

export { expect };
export const apiOrigin = "http://127.0.0.1:18999";
export const timestamp = "2026-10-30T00:00:00Z";
type Reply = { status?: number; json: unknown };
type Handler = (request: Request) => Reply | Promise<Reply>;
type ApiRequest = { method: string; path: string; body: unknown };
type Wire = {
  requests: ApiRequest[];
  on: (method: string, path: string, handler: Handler) => void;
};

export const test = base.extend<{ wire: Wire }>({
  wire: async ({ page, baseURL }, provide, info) => {
    const requests: ApiRequest[] = [];
    const unexpected: string[] = [];
    const handlers = new Map<string, Handler>();
    await page.addInitScript((aiBaseUrl) => {
      window.__VIBE_LEARNER_DESKTOP_CONFIG__ = {
        aiBaseUrl,
        isDesktop: false,
        platform: "unknown",
        secretStorageMode: "plain_text",
        vaultState: "unconfigured",
        vaultPath: "",
        storageRoot: "",
        startupError: "",
      };
    }, apiOrigin);
    // Fail closed: every API request is synthetic, and no other origin can run a provider.
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin === new URL(baseURL!).origin) return route.continue();
      if (url.origin !== apiOrigin) {
        unexpected.push(`${request.method()} ${url.origin}${url.pathname}`);
        return route.abort("blockedbyclient");
      }
      const key = `${request.method()} ${url.pathname}`;
      requests.push({
        method: request.method(),
        path: url.pathname,
        body: request.postData() ? request.postDataJSON() : null,
      });
      const handler = handlers.get(key);
      if (handler) return route.fulfill(await handler(request));
      if (key === "POST /diagnostics/events")
        return route.fulfill({
          json: { accepted: request.postDataJSON().events.length, dropped: 0 },
        });
      if (key === "GET /runtime-settings")
        return route.fulfill({
          json: { ...responses.runtime_settings, show_debug_info: false },
        });
      if (key === "GET /personas")
        return route.fulfill({ json: { items: [persona()] } });
      if (
        [
          "GET /persona-cards",
          "GET /scene-library",
          "GET /reusable-scene-nodes",
        ].includes(key)
      )
        return route.fulfill({ json: { items: [] } });
      unexpected.push(key);
      return route.fulfill({
        status: 501,
        json: { detail: `Unconfigured synthetic request: ${key}` },
      });
    });
    await provide({
      requests,
      on: (method, path, handler) => handlers.set(`${method} ${path}`, handler),
    });
    await info.attach("synthetic-api-log.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            boundary: "Chromium + synthetic API only",
            requests: requests.slice(0, 200),
            unexpected,
          },
          null,
          2,
        ),
      ),
      contentType: "application/json",
    });
    expect(unexpected, "No API or provider escapes the synthetic fixtures").toEqual([]);
    expect(requests.length, "Bounded API log").toBeLessThanOrEqual(200);
  },
});

export function deferred() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

export function persona(overrides: Record<string, unknown> = {}) {
  return {
    id: "ux-persona",
    revision: 1,
    name: "UX Mentor",
    source: "user",
    summary: "原摘要",
    relationship: "原关系",
    learner_address: "原称呼",
    system_prompt: "原约束",
    reference_hints: ["保留来源", "移除来源"],
    slots: [
      {
        kind: "custom",
        label: "原插槽",
        content: "原内容",
        weight: 1,
        locked: false,
        sort_order: 0,
      },
    ],
    available_emotions: ["calm"],
    available_actions: ["point"],
    default_speech_style: "clear",
    ...overrides,
  };
}

export function card(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `ux-card-${index}`,
    title: `候选卡 ${index}`,
    kind: "custom",
    label: `候选插槽 ${index}`,
    content: `候选内容 ${index}`,
    tags: ["压力测试"],
    search_keywords: "审查",
    source: "generated_keywords",
    source_note: index === 1 ? "保留来源" : `新增来源 ${index}`,
    created_at: timestamp,
    updated_at: timestamp,
    ...overrides,
  };
}

export function personaCandidate() {
  return {
    mode: "keywords",
    used_model: "synthetic-only",
    used_web_search: false,
    summary: "候选摘要",
    relationship: "候选关系",
    learner_address: "候选称呼",
    items: [card(1), card(2), card(3)],
    model_recoveries: [],
    harness_trace: wireHarnessTrace("persona", "persona_generation"),
  };
}

type Layer = {
  id: string;
  title: string;
  scope_label: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  tags: string;
  reuse_id: string;
  reuse_hint: string;
  objects: ReturnType<typeof sceneObject>[];
  children: Layer[];
};

export function sceneLayer(id: string, title: string): Layer {
  return {
    id,
    title,
    scope_label: "范围",
    summary: `${title}摘要`,
    atmosphere: "安静",
    rules: "访客禁止离开",
    entrance: "正门",
    tags: "实验",
    reuse_id: `reuse-${id}`,
    reuse_hint: "审查复用",
    objects: [] as ReturnType<typeof sceneObject>[],
    children: [] as ReturnType<typeof sceneLayer>[],
  };
}

export function sceneObject(id: string, name: string) {
  return {
    id,
    name,
    description: `${name}说明`,
    interaction: "观察",
    tags: "实验",
    reuse_id: `reuse-${id}`,
    reuse_hint: "物体复用",
  };
}

export function sceneCandidate(layers = [sceneLayer("root", "实验室")]) {
  return {
    contract_version: "scene-tree-generate-response-v1",
    mode: "keywords",
    used_model: "synthetic-only",
    used_web_search: false,
    scene_name: "候选场景",
    scene_summary: "候选场景摘要",
    selected_layer_id: layers[0].id,
    scene_layers: layers,
    model_recoveries: [],
    harness_trace: wireHarnessTrace("scene", "scene_generation"),
  };
}

export type SceneSave = {
  scene_name: string;
  scene_summary: string;
  scene_layers: Layer[];
  selected_layer_id: string;
  collapsed_layer_ids: string[];
};

export function sceneRecord(body: SceneSave, sceneId: string, revision: number) {
  const find = (
    layers: Layer[],
    parents: string[] = [],
  ): { layer: Layer; path: string[] } | undefined => {
    for (const layer of layers) {
      const path = [...parents, layer.title];
      if (layer.id === body.selected_layer_id) return { layer, path };
      const child = find(layer.children, path);
      if (child) return child;
    }
  };
  const selected = find(body.scene_layers)!;
  return {
    ...body,
    config_id: sceneId,
    scene_id: sceneId,
    revision,
    created_at: timestamp,
    updated_at: timestamp,
    scene_profile: {
      scene_name: body.scene_name,
      summary: body.scene_summary,
      scene_id: body.selected_layer_id,
      title: selected.layer.title,
      tags: [
        ...new Set(
          selected.layer.tags
            .split(/[,，]/)
            .map((s) => s.trim())
            .filter(Boolean),
        ),
      ],
      selected_path: selected.path,
      focus_object_names: selected.layer.objects.slice(0, 4).map((o) => o.name),
      scene_tree: body.scene_layers,
    },
  };
}

export async function noHorizontalOverflow(page: import("@playwright/test").Page) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
  ).toBeLessThanOrEqual(0);
}

// Standalone synthetic v3 DTO, based on the decoder contract fixture; no production evidence claim.
function wireHarnessTrace(
  workflow: "persona" | "scene",
  stage: "persona_generation" | "scene_generation",
  overrides: Record<string, unknown> = {},
) {
  const operationId = "harness-operation-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const artifactType = workflow === "persona" ? "persona_snapshot" : "scene_snapshot";
  const inputContract =
    workflow === "persona"
      ? {
          name: "PersonaGenerationInputManifest",
          version: "persona-generation-input-manifest-v1",
        }
      : {
          name: "SceneGenerationInputManifest",
          version: "scene-generation-input-manifest-v1",
        };
  const artifactContract =
    workflow === "persona"
      ? {
          name: "PersonaGenerationProtectedInput",
          version: "persona-generation-protected-input-v1",
        }
      : {
          name: "SceneGenerationProtectedInput",
          version: "scene-generation-protected-input-v1",
        };
  const promptContract =
    workflow === "persona"
      ? { name: "PersonaGenerationPrompt", version: "persona-generation-prompt-v1" }
      : { name: "SceneGenerationPrompt", version: "scene-generation-prompt-v1" };
  const policyContract =
    workflow === "persona"
      ? {
          name: "PersonaGenerationHarnessPolicy",
          version: "persona-generation-harness-v1",
        }
      : {
          name: "SceneGenerationHarnessPolicy",
          version: "scene-generation-harness-v1",
        };
  const traceContract =
    workflow === "persona"
      ? { name: "PersonaGenerationProposal", version: "persona-generation-proposal-v1" }
      : { name: "SceneTreeProposal", version: "scene-tree-proposal-v1" };
  const componentContract =
    workflow === "persona"
      ? { name: "persona_compiler", version: "persona-compiler-v1" }
      : { name: "scene_compiler", version: "scene-compiler-v1" };
  const outputDigest = "a".repeat(64);
  return {
    trace_schema_version: "harness-trace-v3",
    trace_id: "harness-trace-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    operation_id: operationId,
    parent_trace_id: null,
    workflow,
    stage,
    status: "passed",
    contract: traceContract,
    context: {
      context_contract: {
        name: "HarnessContextEnvelopeV3",
        version: "harness-context-v3",
      },
      workflow,
      stage,
      operation_id: operationId,
      input_contract: inputContract,
      subject_refs: [
        {
          resource_type: "frontend_request",
          resource_id: `${workflow}-request-1`,
          revision: null,
        },
      ],
      component_versions: [componentContract],
      snapshot_refs: [
        {
          artifact_type: artifactType,
          artifact_id: `${workflow}-snapshot-1`,
          contract: artifactContract,
          digest_algorithm: "sha256",
          payload_digest: "b".repeat(64),
        },
      ],
      digest_algorithm: "sha256",
      digest_contract: {
        name: "HarnessContextManifestDigest",
        version: "harness-context-manifest-digest-v1",
      },
      input_digest: "c".repeat(64),
      context_digest: "d".repeat(64),
      policy_contract: policyContract,
      prompt_contract: promptContract,
    },
    output_digest: outputDigest,
    checks: [
      {
        name: "proposal_schema_and_invariants",
        status: "passed",
        code: "proposal_valid",
        message: "Proposal is valid.",
      },
    ],
    attempt_records: [
      {
        attempt_id: "harness-attempt-cccccccccccccccccccccccccccccccc",
        attempt_index: 1,
        phase: "generate",
        status: "passed",
        output_digest: outputDigest,
        error_code: "",
        duration_ms: 1,
      },
      {
        attempt_id: "harness-attempt-dddddddddddddddddddddddddddddddd",
        attempt_index: 2,
        phase: "decode",
        status: "passed",
        output_digest: outputDigest,
        error_code: "",
        duration_ms: 1,
      },
      {
        attempt_id: "harness-attempt-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        attempt_index: 3,
        phase: "validate",
        status: "passed",
        output_digest: outputDigest,
        error_code: "",
        duration_ms: 1,
      },
    ],
    recovery_strategy: "none",
    error_code: "",
    duration_ms: 1,
    commit_evidence: {
      status: "not_applicable",
      effect_batch_id: null,
      payload_contract: null,
      digest_algorithm: null,
      digest_scope: null,
      attempted_resource_refs: [],
      committed_resources: [],
      payload_digest: null,
      committed_at: null,
      rollback_reason_code: "",
      rolled_back_at: null,
    },
    started_at: "2026-08-24T00:00:00Z",
    completed_at: "2026-08-24T00:00:01Z",
    ...overrides,
  };
}
