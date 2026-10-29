import type { DocumentPageNumbering } from "@vibe-learner/shared";
import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { DocumentDecodeError } from "./document-decode.ts";
const d = new StrictResponseDecoder((path, reason) => {
  throw new DocumentDecodeError(path, reason);
});
export function decodeDocumentPageNumbering(
  raw: unknown,
  documentId: string,
  requestedPages: number[],
): DocumentPageNumbering {
  const p = "document_page_numbering";
  const v = d.record(raw, p);
  d.equal(v.contract_version, "document-page-numbering-v1", `${p}.contract_version`);
  d.equal(v.coordinate_system, "pdf_physical_1_based", `${p}.coordinate_system`);
  d.equal(v.document_id, documentId, `${p}.document_id`);
  const physicalPageCount = d.integer(
    d.field(v, "physical_page_count", p),
    `${p}.physical_page_count`,
    1,
  );
  const pages = d.array(d.field(v, "pages", p), `${p}.pages`, (raw, path, index) => {
    const page = d.record(raw, path);
    const physicalPdfPage = d.integer(
      d.field(page, "physical_pdf_page", path),
      `${path}.physical_pdf_page`,
      1,
      physicalPageCount,
    );
    d.equal(physicalPdfPage, requestedPages[index], `${path}.physical_pdf_page`);
    const printedPage = d.nullable(
      d.field(page, "printed_page", path),
      `${path}.printed_page`,
      (raw, labelPath) => {
        const value = d.record(raw, labelPath);
        d.equal(value.source, "pdf_metadata", `${labelPath}.source`);
        const label = d.string(
          d.field(value, "label", labelPath),
          `${labelPath}.label`,
        );
        if (Array.from(label).length > 128)
          throw new DocumentDecodeError(labelPath, "label_too_long");
        return { label, source: "pdf_metadata" as const };
      },
    );
    return { physicalPdfPage, printedPage };
  });
  d.equal(pages.length, requestedPages.length, `${p}.pages`);
  d.unique(
    pages.map((page) => page.physicalPdfPage),
    `${p}.pages`,
  );
  return {
    contractVersion: "document-page-numbering-v1",
    coordinateSystem: "pdf_physical_1_based",
    documentId,
    documentRevision: d.integer(
      d.field(v, "document_revision", p),
      `${p}.document_revision`,
    ),
    physicalPageCount,
    pages,
  };
}
