import { test, expect, type Page } from "@playwright/test";
import { observeRequests } from "./api-fixture";
const api = "http://127.0.0.1:18999";
const timestamp = "2026-08-12T00:00:00Z";
async function tavernFixture(page: Page, status: "partial" | "failed", archived = false) {
  const requests = await observeRequests(page);
  const names = ["Completed Actor", "Failed Actor", "Blocked Actor"];
  const participants = names.map((name, i) => ({ room_id: "copy-room", persona_id: `copy-persona-${i}`, display_order: i, display_name: name,
    persona_snapshot: { id: `copy-persona-${i}`, revision: 0, name, source: "user", summary: "Fixture", relationship: "peer", learner_address: "Learner", system_prompt: "Reply", reference_hints: [], slots: [], available_emotions: ["calm"], available_actions: ["nod"], default_speech_style: "clear" }, prompt_hash: `digest-${i}`, joined_at: timestamp }));
  const room = { id: "copy-room", creation_key: "", creation_input_digest: "", title: "Independent Copy Room", scene_profile: null,
    harness_policy: { version: "tavern-harness-v1", max_character_messages: 4, max_reply_characters: 1200, context_message_limit: 18, prevent_speaker_impersonation: true },
    status: archived ? "archived" : "active", revision: 0, last_sequence: 0, created_at: timestamp, updated_at: timestamp };
  let run: any = null;
  let messages: any[] = [];
  const message = (id: string, seq: number, author: string) => ({ id, room_id: room.id, sequence: seq, run_id: "copy-run", author_kind: author,
    persona_id: author === "persona" ? participants[0].persona_id : "", persona_name: author === "persona" ? names[0] : "",
    content: author === "persona" ? "Committed actor reply" : "Independent round", emotion: "calm", action: "", speech_style: "", addressed_participant_ids: [], reply_to_message_id: author === "persona" ? "input-message" : "", client_request_id: "", created_at: timestamp, harness_trace: null });
  await page.route(`${api}/tavern/rooms?*`, route => route.fulfill({ json: { contract_version: "tavern-room-list-v1", next_cursor: null, items: [{ id: room.id, title: room.title, participant_persona_ids: participants.map(p => p.persona_id), participant_names: names, message_count: messages.length, revision: room.revision, status: room.status, created_at: timestamp, updated_at: timestamp }] } }));
  await page.route(`${api}/tavern/rooms/${room.id}?*`, route => route.fulfill({ json: { room, participants, messages, message_count: messages.length, next_after_sequence: null, next_before_sequence: null } }));
  await page.route(`${api}/tavern/rooms/${room.id}/runs?*`, route => route.fulfill({ json: { items: run ? [run] : [] } }));
  await page.route(`${api}/tavern/rooms/${room.id}/run-recovery?*`, route => route.fulfill({ json: { items: run ? [{ root_run_id: run.id, run_ids: [run.id], root_status: run.status, leaf_run: run, chain_status: "recoverable", recovery_action: "retry_leaf", completed_participant_ids: status === "partial" ? [participants[0].persona_id] : [], unfinished_participant_ids: participants.filter((_,i) => status === "failed" || i > 0).map(p => p.persona_id) }] : [] } }));
  await page.route(`${api}/tavern/rooms/${room.id}/turns`, async route => {
    const input = route.request().postDataJSON();
    messages = [message("input-message", 1, "user"), ...(status === "partial" ? [message("actor-message", 2, "persona")] : [])];
    room.revision = 1; room.last_sequence = messages.length;
    run = { id: "copy-run", room_id: room.id, idempotency_key: input.idempotency_key, request_digest: "request", context_digest: "context", mode: "facilitated", trigger_kind: "user_message", parent_run_id: "", root_run_id: "copy-run", input_message_id: "input-message", anchor_message_id: "", scheduled_participant_ids: participants.map(p => p.persona_id),
      speaker_steps: participants.map((p,i) => ({ run_id: "copy-run", step_index: i, persona_id: p.persona_id, participant_prompt_hash: p.prompt_hash,
        status: status === "partial" && i === 0 ? "completed" : i === (status === "partial" ? 1 : 0) ? "failed" : "blocked",
        message_id: status === "partial" && i === 0 ? "actor-message" : "", reply_to_message_id: "input-message", error_code: i === 2 ? "INDEPENDENT_BLOCKED_RAW_CODE" : "INDEPENDENT_FAILURE_RAW_CODE", harness_trace: null, claim_count: i === 2 ? 0 : 1, started_at: timestamp, completed_at: timestamp })), guidance: "", status, expected_room_revision: 0, generated_message_ids: status === "partial" ? ["actor-message"] : [], harness_trace: [], error_code: "INDEPENDENT_RUN_RAW_CODE", terminal_sequence: messages.length, created_at: timestamp, completed_at: timestamp };
    await route.fulfill({ json: { run, input_message: messages[0], generated_messages: messages.slice(1), room_state: { id: room.id, status: room.status, revision: room.revision, last_sequence: room.last_sequence, updated_at: timestamp } } });
  });
  await page.goto("/tavern");
  await expect(page.getByText("Independent Copy Room", { exact: true }).first()).toBeVisible();
  return { requests, room, participants, getRun: () => run };
}

for (const status of ["partial", "failed"] as const) {
  test(`independent Tavern copy: ${status} has readable primary feedback and blocked is unexecuted`, async ({ page }, info) => {
    const h = await tavernFixture(page, status);
    const roster = page.getByRole("region", { name: "角色与目标", exact: true });
    for (const checkbox of await roster.getByRole("checkbox").all()) await checkbox.check();
    await page.getByRole("textbox", { name: "你的消息", exact: true }).fill("Independent round");
    await page.getByRole("button", { name: "发送并回应", exact: false }).click();
    await expect.poll(() => h.getRun()?.status).toBe(status);
    const details = page.locator("details.reliability-details");
    await expect(details).not.toHaveAttribute("open", "");
    const blocked = roster.locator("label").filter({ hasText: "Blocked Actor" });
    await expect(blocked).toContainText("上一轮尚未执行");
    await expect(blocked).not.toContainText(/回应失败|角色失败/);
    await expect(page.getByText(status === "partial" ? "部分角色回应未完成；已保存的回应不会重复生成，可在下方仅恢复未完成角色。" : "本轮角色回应未完成；可从恢复入口继续尚未完成的角色。", { exact: true })).toBeVisible();
    const visibleText = await page.locator("body").innerText();
    expect(visibleText).not.toMatch(/INDEPENDENT_.*RAW_CODE|tavern_[a-z_]+/);
    await details.locator("summary").click();
    await expect(details).toContainText(/因前序回应未完成而暂未执行/);
    await expect(details.getByRole("button", { name: "仅重试未完成角色", exact: true })).toBeEnabled();
    if (status === "partial") await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    await info.attach("visible-copy.json", { body: JSON.stringify({ status, visibleText, details: await details.innerText() }), contentType: "application/json" });
  });
}

test("independent Tavern copy: archived room explicitly stays read-only", async ({ page }) => {
  await tavernFixture(page, "failed", true);
  await expect(page.getByRole("textbox", { name: "你的消息", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "你的消息", exact: true })).toHaveAttribute("placeholder", "归档房间为只读状态。");
  await expect(page.getByText(/已打开归档房间（只读）/)).toBeVisible();
});

for (const [code, expectedCopy] of [
  ["tavern_retry_context_changed", "房间内容或角色设定已变化，不能继续旧恢复任务。"],
  ["UNKNOWN_INDEPENDENT_PRIVATE_CODE", "重试未完整返回；已重新同步已保存的结果。"],
] as const) {
  test(`independent Tavern copy: retry error ${code} stays readable without raw leakage`, async ({ page }, info) => {
    await tavernFixture(page, "partial");
    const roster = page.getByRole("region", { name: "角色与目标", exact: true });
    for (const checkbox of await roster.getByRole("checkbox").all()) await checkbox.check();
    await page.getByRole("textbox", { name: "你的消息", exact: true }).fill("Independent round");
    await page.getByRole("button", { name: "发送并回应", exact: false }).click();
    await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    let retries = 0;
    await page.route(`${api}/tavern/rooms/copy-room/runs/copy-run/retry`, route => {
      retries++;
      return route.fulfill({ status: 409, json: { detail: { code, run_id: "copy-run", child_run_id: "", current_revision: 1, recovery_action: "reload_room" } } });
    });
    const composer = page.getByRole("region", { name: "发起互动", exact: true });
    await composer.getByRole("button", { name: "仅重试未完成角色", exact: true }).click();
    await expect(page.getByText(expectedCopy, { exact: true })).toBeVisible();
    expect(retries).toBe(1);
    const visibleText = await page.locator("body").innerText();
    expect(visibleText).not.toContain(code);
    expect(visibleText).not.toMatch(/INDEPENDENT_.*RAW_CODE|当前叶节点/);
    await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    await info.attach("retry-visible-copy.json", { body: JSON.stringify({ code, visibleText }), contentType: "application/json" });
  });
}
