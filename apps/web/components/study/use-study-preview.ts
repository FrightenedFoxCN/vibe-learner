import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Citation,
  DocumentRecord,
  StudySessionRecord,
} from "@vibe-learner/shared";
import { getAiBaseUrl } from "../../lib/runtime-config";
import type {
  StudyDialogPageCache,
  StudyDialogPreviewState,
} from "../../lib/learning-workspace-page-cache";
import { resolveStudyPreviewSync, type StudyPreviewInputs } from "./study-preview-sync";

type StudyPreviewOptions = {
  activeDocument: DocumentRecord | null;
  studySession: StudySessionRecord | null;
  studyDialogCache?: StudyDialogPageCache;
  requestedPage: number;
};

export function useStudyPreview({
  activeDocument,
  studySession,
  studyDialogCache,
  requestedPage,
}: StudyPreviewOptions) {
  const [pdfPage, setPdfPage] = useState(() => studyDialogCache?.pdfPage ?? 1);
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(false);
  const [previewState, setPreviewState] = useState<StudyDialogPreviewState | null>(
    () => studyDialogCache?.previewState ?? null,
  );
  const [pendingComposerInsert, setPendingComposerInsert] = useState<{
    id: string;
    text: string;
  } | null>(null);
  const projectedPdf = studySession?.projectedPdf ?? null;

  const handleOpenPdfPage = useCallback(
    (page: number) => {
      setPdfPage(page);
      if (activeDocument) {
        setPreviewState({
          kind: "document",
          sourceId: activeDocument.id,
          title: activeDocument.title,
          page: page,
          pageCount: activeDocument.pageCount,
        });
      }
      setIsPdfPreviewOpen(true);
    },
    [activeDocument],
  );

  const handleOpenCitation = useCallback(
    (citation: Citation) => {
      const targetPage = Math.max(1, citation.pageStart || 1);
      if (citation.sourceKind === "attachment_pdf" && studySession?.id) {
        const attachment = resolvePreviewableAttachmentById(
          studySession,
          citation.sourceId || citation.sectionId,
          "pdf",
        );
        if (attachment) {
          setPreviewState({
            kind: "attachment_pdf",
            sourceId: attachment.attachmentId,
            title: attachment.name,
            page: targetPage,
            pageCount: attachment.pageCount ?? 0,
          });
          setIsPdfPreviewOpen(true);
          return;
        }
      }
      if (citation.sourceKind === "attachment_image" && studySession?.id) {
        const attachment = resolvePreviewableAttachmentById(
          studySession,
          citation.sourceId || citation.sectionId,
          "image",
        );
        if (attachment) {
          setPreviewState({
            kind: "attachment_image",
            sourceId: attachment.attachmentId,
            title: attachment.name,
            page: 1,
            pageCount: 1,
          });
          setIsPdfPreviewOpen(true);
          return;
        }
      }
      if (activeDocument) {
        setPdfPage(targetPage);
        setPreviewState({
          kind: "document",
          sourceId: activeDocument.id,
          title: activeDocument.title,
          page: targetPage,
          pageCount: activeDocument.pageCount,
        });
        setIsPdfPreviewOpen(true);
      }
    },
    [activeDocument, studySession],
  );

  const documentId = activeDocument?.id;
  const documentTitle = activeDocument?.title;
  const documentPageCount = activeDocument?.pageCount;
  const documentFirstPage = activeDocument?.sections[0]?.pageStart;
  const hasProjectedPdf = projectedPdf !== null;
  const previousPreviewInputs = useRef<StudyPreviewInputs | null>(null);

  useEffect(() => {
    const inputs = {
      documentId,
      documentTitle,
      documentPageCount,
      documentFirstPage,
      requestedPage,
      hasProjectedPdf,
    };
    const sync = resolveStudyPreviewSync(previousPreviewInputs.current, inputs);
    previousPreviewInputs.current = inputs;
    if (!sync) return;

    if (sync.kind === "metadata") {
      setPreviewState((current) =>
        current?.kind === "document" && current.sourceId === documentId
          ? {
              ...current,
              title: sync.title ?? current.title,
              pageCount: sync.pageCount ?? current.pageCount,
            }
          : current,
      );
      return;
    }

    setPdfPage(sync.page);
    if (
      documentId !== undefined &&
      documentTitle !== undefined &&
      documentPageCount !== undefined
    ) {
      setPreviewState({
        kind: "document",
        sourceId: documentId,
        title: documentTitle,
        page: sync.page,
        pageCount: documentPageCount,
      });
    }
  }, [
    documentId,
    documentTitle,
    documentPageCount,
    documentFirstPage,
    requestedPage,
    hasProjectedPdf,
  ]);

  const { imageUrl, pageNumber, pageCount, sourceId, sourceKind, title, updatedAt } =
    projectedPdf ?? {};
  // A new projection can restore the preview even when its displayed fields are unchanged.
  useEffect(() => {
    // A revision with unchanged displayed fields must still restore the selection.
    void updatedAt;
    if (
      sourceKind === undefined ||
      sourceId === undefined ||
      title === undefined ||
      pageNumber === undefined ||
      pageCount === undefined
    )
      return;
    if (sourceKind === "attachment_pdf") {
      setPreviewState({
        kind: "attachment_pdf",
        sourceId,
        title,
        page: pageNumber,
        pageCount,
      });
    } else if (sourceKind === "attachment_image") {
      setPreviewState({
        kind: "attachment_image",
        sourceId,
        title,
        page: pageNumber,
        pageCount,
        imageUrl: imageUrl || "",
      });
    } else if (sourceKind === "generated_image") {
      setPreviewState({
        kind: "generated_image",
        sourceId,
        title,
        page: pageNumber,
        pageCount,
        imageUrl: imageUrl || "",
      });
    } else {
      setPreviewState({
        kind: "document",
        sourceId,
        title,
        page: pageNumber,
        pageCount,
      });
    }
  }, [imageUrl, pageNumber, pageCount, sourceId, sourceKind, title, updatedAt]);

  const effectivePreview = previewState;
  const previewPage = effectivePreview?.page ?? pdfPage;
  const previewTitle = effectivePreview?.title ?? activeDocument?.title ?? "";
  const previewFileUrl =
    effectivePreview?.kind === "document"
      ? `${getAiBaseUrl()}/documents/${effectivePreview.sourceId}/file`
      : effectivePreview?.kind === "generated_image"
        ? effectivePreview.imageUrl
        : (effectivePreview?.kind === "attachment_pdf" ||
              effectivePreview?.kind === "attachment_image") &&
            studySession?.id
          ? `${getAiBaseUrl()}/study-sessions/${studySession.id}/attachments/${effectivePreview.sourceId}/file`
          : "";
  const previewPageCount =
    effectivePreview?.pageCount ?? activeDocument?.pageCount ?? 0;
  const previewOverlays =
    (effectivePreview?.kind === "attachment_pdf" ||
      effectivePreview?.kind === "attachment_image" ||
      effectivePreview?.kind === "generated_image") &&
    projectedPdf?.sourceId === effectivePreview.sourceId
      ? projectedPdf.overlays.filter((item) => item.pageNumber === previewPage)
      : [];
  const jumpToPreviewPage = useCallback(() => {
    if (
      !effectivePreview ||
      effectivePreview.kind === "attachment_image" ||
      effectivePreview.kind === "generated_image"
    ) {
      return;
    }
    const raw = window.prompt("跳转到页码", String(previewPage));
    if (!raw) {
      return;
    }
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return;
    }
    const nextPage = previewPageCount > 0 ? Math.min(parsed, previewPageCount) : parsed;
    setPdfPage(nextPage);
    setPreviewState((current) =>
      current
        ? {
            ...current,
            page: nextPage,
          }
        : current,
    );
  }, [effectivePreview, previewPage, previewPageCount]);

  const isImage =
    effectivePreview?.kind === "attachment_image" ||
    effectivePreview?.kind === "generated_image";
  const canGoBack = Boolean(effectivePreview && !isImage && previewPage > 1);
  const canGoForward = Boolean(
    effectivePreview &&
    !isImage &&
    !(previewPageCount > 0 && previewPage >= previewPageCount),
  );

  function goBack() {
    if (!canGoBack || !effectivePreview) return;
    // Step back even when a freshly loaded document reports a smaller page count.
    const nextPage = previewPage - 1;
    setPdfPage(nextPage);
    setPreviewState({ ...effectivePreview, page: nextPage });
  }

  function requestPage(delta: -1 | 1) {
    if (!effectivePreview || isImage) return;
    const nextPage = previewPage + delta;
    if (nextPage < 1 || (previewPageCount > 0 && nextPage > previewPageCount)) return;
    setPdfPage(nextPage);
    setPreviewState((current) => (current ? { ...current, page: nextPage } : current));
  }

  function updatePageCount(pageCount: number) {
    if (!effectivePreview) return;
    setPreviewState((current) => (current ? { ...current, pageCount } : current));
  }

  function insertReference(text: string) {
    const source =
      effectivePreview?.kind === "generated_image"
        ? "generated-image"
        : isImage
          ? "image"
          : previewPage;
    setPendingComposerInsert({
      id: `${Date.now()}:${source}:${text.slice(0, 24)}`,
      text,
    });
  }

  return {
    pdfPage,
    isPdfPreviewOpen,
    previewState,
    pendingComposerInsert,
    setPendingComposerInsert,
    handleOpenPdfPage,
    handleOpenCitation,
    previewPage,
    previewTitle,
    previewPageCount,
    previewFileUrl,
    previewOverlays,
    isImage,
    canGoBack,
    canGoForward,
    goBack,
    requestPage,
    updatePageCount,
    insertReference,
    jumpToPreviewPage,
    setIsPdfPreviewOpen,
  };
}

function resolvePreviewableAttachmentById(
  session: StudySessionRecord | null | undefined,
  attachmentId: string,
  kind?: "pdf" | "image",
) {
  const normalizedId = attachmentId.trim();
  if (!session || !normalizedId) {
    return null;
  }
  for (const turn of session.turns) {
    const match = turn.learnerAttachments?.find(
      (attachment) =>
        attachment.attachmentId === normalizedId &&
        attachment.previewable &&
        (!kind || attachment.kind === kind),
    );
    if (match) {
      return match;
    }
  }
  return null;
}
