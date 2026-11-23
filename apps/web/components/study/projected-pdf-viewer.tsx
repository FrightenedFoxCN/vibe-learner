"use client";

import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import { useEffect, useId, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { PdfRect, ProjectedPdfOverlay } from "@vibe-learner/shared";

import { MaterialIcon } from "../ui/material-icon";
import type { StudyOverlayStyle } from "./study-overlay-style";
import "./study-pdf-viewer.css";
import "./projected-pdf-viewer-vendor.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface ProjectedPdfViewerProps {
  fileUrl: string;
  title: string;
  pageNumber: number;
  overlays?: ProjectedPdfOverlay[];
  onInsertReference?: (text: string) => void;
  onPageCountChange?: (pageCount: number) => void;
  onPageRequest?: (delta: -1 | 1) => void;
}

type TextSelectionState = {
  text: string;
  rects: PdfRect[];
};

type PreviewLoadState =
  | { phase: "document_loading" | "page_loading"; message: string }
  | { phase: "ready"; message: "" }
  | { phase: "error"; message: string };

const PREVIEW_TIMEOUT_MS = 12_000;

export function ProjectedPdfViewer({
  fileUrl,
  title,
  pageNumber,
  overlays = [],
  onInsertReference,
  onPageCountChange,
  onPageRequest,
}: ProjectedPdfViewerProps) {
  const viewerId = useId();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pageShellRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
  } | null>(null);
  const draftRegionRef = useRef<PdfRect | null>(null);
  const wheelDeltaRef = useRef(0);
  const wheelNavAtRef = useRef(0);
  const [pageHeight, setPageHeight] = useState(0);
  const [loadState, setLoadState] = useState<PreviewLoadState>({
    phase: "document_loading",
    message: "正在载入 PDF…",
  });
  const [retryToken, setRetryToken] = useState(0);
  const [isRegionMode, setIsRegionMode] = useState(false);
  const [textSelection, setTextSelection] = useState<TextSelectionState | null>(null);
  const [draftRegion, setDraftRegion] = useState<PdfRect | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<PdfRect | null>(null);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) return;
    const measure = () => {
      setPageHeight(Math.max(240, Math.floor(node.clientHeight)));
    };
    measure();
    const observer = new ResizeObserver(() => measure());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setLoadState({ phase: "document_loading", message: "正在载入 PDF…" });
    clearInteractionState();
    wheelDeltaRef.current = 0;
  }, [fileUrl, pageNumber, retryToken]);

  useEffect(() => {
    if (!fileUrl || loadState.phase === "ready" || loadState.phase === "error") return;
    const timer = window.setTimeout(() => {
      setLoadState({
        phase: "error",
        message:
          loadState.phase === "document_loading"
            ? "PDF 加载超时。"
            : "PDF 页面渲染超时。",
      });
    }, PREVIEW_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [fileUrl, loadState.phase, retryToken]);

  const retryPreview = () => {
    setRetryToken((current) => current + 1);
  };

  const clearInteractionState = () => {
    dragStateRef.current = null;
    draftRegionRef.current = null;
    setDraftRegion(null);
    setSelectedRegion(null);
    setTextSelection(null);
    window.getSelection()?.removeAllRanges();
  };

  const handleMouseUp = () => {
    if (isRegionMode) {
      return;
    }
    const selection = window.getSelection();
    const pageNode = pageShellRef.current;
    if (
      !selection ||
      !pageNode ||
      selection.isCollapsed ||
      selection.rangeCount === 0
    ) {
      setTextSelection(null);
      return;
    }
    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if (
      (anchorNode && !pageNode.contains(anchorNode)) ||
      (focusNode && !pageNode.contains(focusNode))
    ) {
      return;
    }
    const text = selection.toString().replace(/\s+/g, " ").trim();
    if (!text) {
      setTextSelection(null);
      return;
    }
    const pageRect = pageNode.getBoundingClientRect();
    const rects = Array.from(selection.getRangeAt(0).getClientRects())
      .filter((rect) => rect.width > 2 && rect.height > 2)
      .map((rect) => normalizeRect(rect, pageRect))
      .filter((rect) => rect.width > 0 && rect.height > 0);
    if (!rects.length) {
      setTextSelection(null);
      return;
    }
    setTextSelection({ text, rects });
    setSelectedRegion(null);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!isRegionMode || !pageShellRef.current) return;
    event.preventDefault();
    const pageRect = pageShellRef.current.getBoundingClientRect();
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: clamp01((event.clientX - pageRect.left) / Math.max(pageRect.width, 1)),
      startY: clamp01((event.clientY - pageRect.top) / Math.max(pageRect.height, 1)),
    };
    draftRegionRef.current = null;
    setDraftRegion(null);
    setSelectedRegion(null);
    setTextSelection(null);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId || !pageShellRef.current)
      return;
    event.preventDefault();
    const pageRect = pageShellRef.current.getBoundingClientRect();
    const nextRegion = buildRect(
      dragState.startX,
      dragState.startY,
      clamp01((event.clientX - pageRect.left) / Math.max(pageRect.width, 1)),
      clamp01((event.clientY - pageRect.top) / Math.max(pageRect.height, 1)),
    );
    draftRegionRef.current = nextRegion;
    setDraftRegion(nextRegion);
  };

  const finishRegionSelection = (event: ReactPointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    dragStateRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const finalRegion = draftRegionRef.current;
    draftRegionRef.current = null;
    setDraftRegion(null);
    if (!finalRegion || finalRegion.width < 0.01 || finalRegion.height < 0.01) {
      return;
    }
    setSelectedRegion(finalRegion);
  };

  const insertTextReference = () => {
    if (!textSelection || !onInsertReference) return;
    onInsertReference(
      `请结合当前投射材料《${title}》第 ${pageNumber} 页这段内容回答：\n> ${textSelection.text}`,
    );
    clearInteractionState();
  };

  const insertRegionReference = () => {
    if (!selectedRegion || !onInsertReference) return;
    onInsertReference(
      `请结合当前投射材料《${title}》第 ${pageNumber} 页这个选区回答：` +
        ` [x=${selectedRegion.x.toFixed(3)}, y=${selectedRegion.y.toFixed(3)}, w=${selectedRegion.width.toFixed(3)}, h=${selectedRegion.height.toFixed(3)}]`,
    );
    clearInteractionState();
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    if (!onPageRequest) {
      return;
    }
    const now = Date.now();
    if (now - wheelNavAtRef.current < 240) {
      return;
    }
    wheelDeltaRef.current += event.deltaY;
    if (Math.abs(wheelDeltaRef.current) < 180) {
      return;
    }
    const direction: -1 | 1 = wheelDeltaRef.current > 0 ? 1 : -1;
    wheelDeltaRef.current = 0;
    wheelNavAtRef.current = now;
    event.preventDefault();
    onPageRequest(direction);
  };

  return (
    <div className="study-pdf-viewer-wrap">
      <div
        className="study-pdf-viewer-viewport"
        ref={viewportRef}
        onWheel={handleWheel}
      >
        <div className="study-pdf-viewer-floating-bar">
          <button
            type="button"
            className={
              !isRegionMode
                ? "study-pdf-viewer-icon-button study-pdf-viewer-icon-button-active"
                : "study-pdf-viewer-icon-button"
            }
            onClick={() => {
              setIsRegionMode(false);
              clearInteractionState();
            }}
            title="文本选择"
            aria-label="文本选择"
          >
            <MaterialIcon name="description" size={15} />
          </button>
          <button
            type="button"
            className={
              isRegionMode
                ? "study-pdf-viewer-icon-button study-pdf-viewer-icon-button-active"
                : "study-pdf-viewer-icon-button"
            }
            onClick={() => {
              setIsRegionMode(true);
              clearInteractionState();
            }}
            title="框选"
            aria-label="框选"
          >
            <MaterialIcon name="crop_free" size={15} />
          </button>

          {textSelection ? (
            <span className="study-pdf-viewer-selection-badge">已选文段</span>
          ) : null}
          {selectedRegion ? (
            <span className="study-pdf-viewer-selection-badge">已框选</span>
          ) : null}

          {textSelection ? (
            <button
              type="button"
              className="study-pdf-viewer-icon-button study-pdf-viewer-icon-action-button"
              onClick={insertTextReference}
              title="插入引用"
              aria-label="插入引用"
            >
              <MaterialIcon name="input" size={15} />
            </button>
          ) : null}
          {selectedRegion ? (
            <button
              type="button"
              className="study-pdf-viewer-icon-button study-pdf-viewer-icon-action-button"
              onClick={insertRegionReference}
              title="插入选区"
              aria-label="插入选区"
            >
              <MaterialIcon name="input" size={15} />
            </button>
          ) : null}
          {textSelection || selectedRegion || draftRegion ? (
            <button
              type="button"
              className="study-pdf-viewer-icon-button"
              onClick={clearInteractionState}
              title="清除"
              aria-label="清除"
            >
              <MaterialIcon name="close" size={15} />
            </button>
          ) : null}
        </div>

        {fileUrl ? (
          <Document
            key={`${fileUrl}:${retryToken}`}
            className="study-pdf-preview-document"
            file={fileUrl}
            loading={null}
            error={null}
            onLoadError={() =>
              setLoadState({ phase: "error", message: "PDF 加载失败。" })
            }
            onLoadSuccess={(payload) => {
              onPageCountChange?.(payload.numPages);
              setLoadState({
                phase: "page_loading",
                message: `正在渲染第 ${pageNumber} 页…`,
              });
            }}
          >
            <div
              ref={pageShellRef}
              data-pdf-viewer-id={viewerId}
              className={
                isRegionMode
                  ? "study-pdf-viewer-page-shell study-pdf-viewer-page-shell-region-mode"
                  : "study-pdf-viewer-page-shell"
              }
              onMouseUp={handleMouseUp}
            >
              <Page
                className={
                  isRegionMode
                    ? "study-pdf-preview-page study-pdf-preview-page--region"
                    : "study-pdf-preview-page"
                }
                pageNumber={pageNumber}
                height={pageHeight || undefined}
                renderTextLayer
                renderAnnotationLayer={false}
                loading={null}
                error={null}
                onRenderSuccess={() => setLoadState({ phase: "ready", message: "" })}
                onRenderError={() =>
                  setLoadState({ phase: "error", message: "当前页渲染失败。" })
                }
              />

              <div className="study-pdf-viewer-overlay-stage">
                {overlays.map((overlay) =>
                  overlay.rects.map((rect, index) => (
                    <div
                      key={`${overlay.id}:${index}`}
                      className="study-pdf-viewer-overlay-box"
                      style={
                        {
                          left: `${rect.x * 100}%`,
                          top: `${rect.y * 100}%`,
                          width: `${rect.width * 100}%`,
                          height: `${rect.height * 100}%`,
                          "--study-overlay-color": overlay.color,
                        } as StudyOverlayStyle
                      }
                      title={overlay.label || overlay.quoteText || overlay.kind}
                    >
                      {index === 0 && (overlay.label || overlay.quoteText) ? (
                        <span className="study-pdf-viewer-overlay-label">
                          {overlay.label || overlay.quoteText}
                        </span>
                      ) : null}
                    </div>
                  )),
                )}

                {textSelection?.rects.map((rect, index) => (
                  <div
                    key={`text-selection:${index}`}
                    className="study-pdf-viewer-selection-box"
                    style={{
                      left: `${rect.x * 100}%`,
                      top: `${rect.y * 100}%`,
                      width: `${rect.width * 100}%`,
                      height: `${rect.height * 100}%`,
                    }}
                  />
                ))}

                {selectedRegion ? (
                  <div
                    className="study-pdf-viewer-region-box"
                    style={{
                      left: `${selectedRegion.x * 100}%`,
                      top: `${selectedRegion.y * 100}%`,
                      width: `${selectedRegion.width * 100}%`,
                      height: `${selectedRegion.height * 100}%`,
                    }}
                  />
                ) : null}

                {isRegionMode ? (
                  <div
                    className="study-pdf-viewer-region-capture-layer"
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={finishRegionSelection}
                    onPointerCancel={finishRegionSelection}
                  >
                    {draftRegion ? (
                      <div
                        className="study-pdf-viewer-region-draft-box"
                        style={{
                          left: `${draftRegion.x * 100}%`,
                          top: `${draftRegion.y * 100}%`,
                          width: `${draftRegion.width * 100}%`,
                          height: `${draftRegion.height * 100}%`,
                        }}
                      />
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </Document>
        ) : (
          <div className="study-pdf-viewer-error-state">当前没有可预览的 PDF。</div>
        )}
        {fileUrl && loadState.phase !== "ready" ? (
          <div
            className="study-pdf-viewer-status-layer"
            role={loadState.phase === "error" ? "alert" : "status"}
            aria-live="polite"
          >
            <span>{loadState.message}</span>
            {loadState.phase === "error" ? (
              <button
                type="button"
                className="study-pdf-viewer-retry-button"
                onClick={retryPreview}
              >
                重新加载
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function normalizeRect(rect: DOMRect | ClientRect, bounds: DOMRect): PdfRect {
  const width = Math.max(bounds.width, 1);
  const height = Math.max(bounds.height, 1);
  const x = clamp01((rect.left - bounds.left) / width);
  const y = clamp01((rect.top - bounds.top) / height);
  return {
    x,
    y,
    width: Math.max(0, Math.min(1 - x, rect.width / width)),
    height: Math.max(0, Math.min(1 - y, rect.height / height)),
  };
}

function buildRect(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
): PdfRect {
  return {
    x: Math.min(startX, endX),
    y: Math.min(startY, endY),
    width: Math.abs(endX - startX),
    height: Math.abs(endY - startY),
  };
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}
