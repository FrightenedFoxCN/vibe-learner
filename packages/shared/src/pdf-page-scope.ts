/** Physical offsets and printed labels are distinct; labels never define bounds. */
export interface PrintedPageLabel {
  label: string;
  source: "pdf_metadata";
}
export interface DocumentPageCoordinate {
  physicalPdfPage: number;
  printedPage: PrintedPageLabel | null;
}
export interface DocumentPageNumbering {
  contractVersion: "document-page-numbering-v1";
  coordinateSystem: "pdf_physical_1_based";
  documentId: string;
  documentRevision: number;
  physicalPageCount: number;
  pages: DocumentPageCoordinate[];
}
