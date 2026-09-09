import assert from "node:assert/strict";
import test from "node:test";
import { JSON_IMPORT_MAX_BYTES, readBoundedJsonImport } from "../lib/bounded-json-import.ts";

test("both editors accept exactly 8 MiB and reject one byte more before reading", async () => {
  for (const kind of ["persona", "scene"] as const) {
    const file = new File(['{}' + ' '.repeat(JSON_IMPORT_MAX_BYTES - 2)], "synthetic.json");
    assert.equal(file.size, JSON_IMPORT_MAX_BYTES);
    assert.deepEqual(await readBoundedJsonImport(file, kind), {});
    let read = false;
    await assert.rejects(readBoundedJsonImport({ size: JSON_IMPORT_MAX_BYTES + 1, text: async () => { read = true; return '{}'; } }, kind), new RegExp(`${kind}_import_file_too_large`));
    assert.equal(read, false);
    await assert.rejects(readBoundedJsonImport(new File(['{'], 'bad.json'), kind), SyntaxError);
    assert.deepEqual(await readBoundedJsonImport(new File(['{}'], 'retry.json'), kind), {});
  }
});

test("file limits use UTF-8 bytes, not JavaScript string length", async () => {
  const file = new File([JSON.stringify({ text: '🦊'.repeat(JSON_IMPORT_MAX_BYTES / 4) })], 'unicode.json');
  assert.ok(file.size > JSON_IMPORT_MAX_BYTES);
  await assert.rejects(readBoundedJsonImport(file, 'scene'), /scene_import_file_too_large/);
});
