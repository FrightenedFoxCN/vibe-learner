export type StudyPreviewInputs = {
  documentId: string | undefined;
  documentTitle: string | undefined;
  documentPageCount: number | undefined;
  documentFirstPage: number | undefined;
  requestedPage: number;
  hasProjectedPdf: boolean;
};

type StudyPreviewSync =
  | { kind: "navigate"; page: number }
  | { kind: "metadata"; title?: string; pageCount?: number };

export function resolveStudyPreviewSync(
  previous: StudyPreviewInputs | null,
  current: StudyPreviewInputs,
): StudyPreviewSync | null {
  if (current.hasProjectedPdf) return null;

  const sourceChanged =
    !previous || previous.hasProjectedPdf || previous.documentId !== current.documentId;
  const { requestedPage } = current;
  if (
    (sourceChanged || previous.requestedPage !== requestedPage) &&
    Number.isFinite(requestedPage) &&
    requestedPage > 0
  ) {
    return { kind: "navigate", page: requestedPage };
  }
  if (sourceChanged) {
    return current.documentId === undefined
      ? null
      : { kind: "navigate", page: current.documentFirstPage || 1 };
  }

  // A focus refresh can replace the document and its anchors without navigating.
  const title =
    current.documentTitle !== previous.documentTitle
      ? current.documentTitle
      : undefined;
  const pageCount =
    current.documentPageCount !== previous.documentPageCount
      ? current.documentPageCount
      : undefined;
  return title === undefined && pageCount === undefined
    ? null
    : { kind: "metadata", title, pageCount };
}
