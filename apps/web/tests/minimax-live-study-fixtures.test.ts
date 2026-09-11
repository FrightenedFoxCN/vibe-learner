import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { decodeStudyChatOperationReceipt } from "../lib/study-chat-operation-decode.ts";
import { decodeStudyChatExchange } from "../lib/study-session-decode.ts";

const rows = readFileSync(new URL("../../../docs/quality/evidence/minimax-study-baseline-v1.jsonl", import.meta.url), "utf8")
  .trim().split("\n").map(line => JSON.parse(line));

test("strict frontend decoders accept twelve frozen real M3 Study receipts", () => {
  assert.equal(rows.length, 12);
  for (const row of rows) {
    const raw = row.receipt;
    const receipt = decodeStudyChatOperationReceipt(raw, {
      expectedSessionId: raw.session_id,
      expectedClientRequestId: raw.client_request_id,
      decodeResult: (value, path, evidence) => decodeStudyChatExchange(value, {
        path, expectedSessionId: raw.session_id, evidence,
      }),
    });
    assert.equal(receipt.status, "committed", `${row.case_id}/${row.repetition}`);
    assert.ok(receipt.result);
  }
});

test("M3 code examples remain real multiline rich blocks", () => {
  const examples = rows.filter(row => row.case_id === "code_and_math");
  assert.equal(examples.length, 3);
  for (const row of examples) {
    const blocks = row.receipt.result.rich_blocks.filter((block: { kind: string }) => block.kind === "code");
    assert.equal(blocks.length, 1);
    assert.ok(blocks[0].content.includes("\n"));
    assert.ok(blocks[0].content.includes("assert "));
  }
});
