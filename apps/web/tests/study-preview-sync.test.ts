import assert from "node:assert/strict";
import test from "node:test";
import {
  resolveStudyPreviewSync,
  type StudyPreviewInputs,
} from "../components/study/study-preview-sync.ts";

const textbook: StudyPreviewInputs = {
  documentId: "textbook-a",
  documentTitle: "Textbook A",
  documentPageCount: 100,
  documentFirstPage: 5,
  requestedPage: 0,
  hasProjectedPdf: false,
};

const navigate = (page: number) => ({ kind: "navigate", page });

test("refreshing the same textbook does not replay its first page", () => {
  assert.deepEqual(resolveStudyPreviewSync(null, textbook), navigate(5));
  assert.equal(resolveStudyPreviewSync(textbook, { ...textbook }), null);
  assert.equal(
    resolveStudyPreviewSync(textbook, { ...textbook, documentFirstPage: 7 }),
    null,
  );
});

test("only a changed valid page request navigates within the same textbook", () => {
  const deepLink = { ...textbook, requestedPage: 18 };
  assert.deepEqual(resolveStudyPreviewSync(textbook, deepLink), navigate(18));
  assert.equal(resolveStudyPreviewSync(deepLink, { ...deepLink }), null);
  assert.deepEqual(
    resolveStudyPreviewSync(deepLink, { ...deepLink, requestedPage: 31 }),
    navigate(31),
  );
  for (const requestedPage of [0, -3, NaN, Infinity]) {
    assert.equal(
      resolveStudyPreviewSync(deepLink, { ...deepLink, requestedPage }),
      null,
    );
  }
});

test("same-textbook metadata updates do not navigate or resend unchanged page counts", () => {
  assert.deepEqual(
    resolveStudyPreviewSync(textbook, {
      ...textbook,
      documentTitle: "Revised textbook A",
      documentFirstPage: 7,
    }),
    { kind: "metadata", title: "Revised textbook A", pageCount: undefined },
  );
  assert.deepEqual(
    resolveStudyPreviewSync(textbook, { ...textbook, documentPageCount: 102 }),
    { kind: "metadata", title: undefined, pageCount: 102 },
  );
});

test("a new textbook initializes, keeping a deep link across delayed document selection", () => {
  const second = { ...textbook, documentId: "textbook-b", documentFirstPage: 11 };
  assert.deepEqual(resolveStudyPreviewSync(textbook, second), navigate(11));
  assert.deepEqual(
    resolveStudyPreviewSync(textbook, { ...second, documentFirstPage: undefined }),
    navigate(1),
  );
  const loading = {
    ...textbook,
    documentId: undefined,
    documentTitle: undefined,
    documentPageCount: undefined,
    documentFirstPage: undefined,
    requestedPage: 18,
  };
  assert.deepEqual(resolveStudyPreviewSync(null, loading), navigate(18));
  assert.deepEqual(
    resolveStudyPreviewSync(loading, { ...second, requestedPage: 18 }),
    navigate(18),
  );
});

test("a projection suppresses ordinary navigation until it is removed", () => {
  const projected = { ...textbook, hasProjectedPdf: true, requestedPage: 18 };
  assert.equal(resolveStudyPreviewSync(textbook, projected), null);
  const newProjected = { ...projected, documentId: "textbook-b", requestedPage: 31 };
  assert.equal(resolveStudyPreviewSync(projected, newProjected), null);
  const ordinary = { ...newProjected, hasProjectedPdf: false };
  assert.deepEqual(resolveStudyPreviewSync(newProjected, ordinary), navigate(31));
  assert.equal(resolveStudyPreviewSync(ordinary, { ...ordinary }), null);
  assert.deepEqual(
    resolveStudyPreviewSync(projected, { ...textbook, requestedPage: 0 }),
    navigate(5),
  );
});
