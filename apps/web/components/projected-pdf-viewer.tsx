"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useId, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { PdfRect, ProjectedPdfOverlay } from "@vibe-learner/shared";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

interface ProjectedPdfViewerProps {
  fileUrl: string;
  title: string;
  pageNumber: number;
  overlays?: ProjectedPdfOverlay[];
  onInsertReference?: (text: string) => void;
  onPageCountChange?: (pageCount: number) => void;
}

type TextSelectionState = {
  text: string;
  rects: PdfRect[];
};

export function ProjectedPdfViewer({
  fileUrl,
  title,
  pageNumber,
  overlays = [],
  onInsertReference,
  onPageCountChange,
}: ProjectedPdfViewerProps) {
  const viewerId = useId();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pageShellRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null);
  const draftRegionRef = useRef<PdfRect | null>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [isRegionMode, setIsRegionMode] = useState(false);
  const [textSelection, setTextSelection] = useState<TextSelectionState | null>(null);
  const [draftRegion, setDraftRegion] = useState<PdfRect | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<PdfRect | null>(null);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) return;
    const measure = () => {
      setPageWidth(Math.max(240, Math.floor(node.clientWidth)));
    };
    measure();
    const observer = new ResizeObserver(() => measure());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setLoadError("");
    clearInteractionState();
  }, [fileUrl, pageNumber]);

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
    if (!selection || !pageNode || selection.isCollapsed || selection.rangeCount === 0) {
      setTextSelection(null);
      return;
    }
    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if ((anchorNode && !pageNode.contains(anchorNode)) || (focusNode && !pageNode.contains(focusNode))) {
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
    if (!dragState || dragState.pointerId !== event.pointerId || !pageShellRef.current) return;
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
      `请结合当前投射材料《${title}》第 ${pageNumber} 页这段内容回答：\n> ${textSelection.text}`
    );
    clearInteractionState();
  };

  const insertRegionReference = () => {
    if (!selectedRegion || !onInsertReference) return;
    onInsertReference(
      `请结合当前投射材料《${title}》第 ${pageNumber} 页这个选区回答：` +
      ` [x=${selectedRegion.x.toFixed(3)}, y=${selectedRegion.y.toFixed(3)}, w=${selectedRegion.width.toFixed(3)}, h=${selectedRegion.height.toFixed(3)}]`
    );
    clearInteractionState();
  };

  return (
    <div style={styles.wrap}>
      <div style={styles.viewport} ref={viewportRef}>
        <div style={styles.floatingBar}>
          <button
            type="button"
            style={{
              ...styles.modeButton,
              ...(isRegionMode ? styles.modeButtonActive : {}),
            }}
            onClick={() => {
              setIsRegionMode((current) => !current);
              clearInteractionState();
            }}
          >
            {isRegionMode ? "框选中" : "文本引用"}
          </button>

          {textSelection ? <span style={styles.selectionBadge}>已选文段</span> : null}
          {selectedRegion ? <span style={styles.selectionBadge}>已框选</span> : null}

          {textSelection ? (
            <button type="button" style={styles.actionButton} onClick={insertTextReference}>
              插入引用
            </button>
          ) : null}
          {selectedRegion ? (
            <button type="button" style={styles.actionButton} onClick={insertRegionReference}>
              插入选区
            </button>
          ) : null}
          {(textSelection || selectedRegion || draftRegion) ? (
            <button type="button" style={styles.clearButton} onClick={clearInteractionState}>
              清除
            </button>
          ) : null}
        </div>

        {fileUrl ? (
          <Document
            className="pdf-preview-document"
            file={fileUrl}
            loading={<div style={styles.loadingState}>PDF 加载中…</div>}
            error={<div style={styles.errorState}>{loadError || "PDF 加载失败。"}</div>}
            onLoadError={(error) => setLoadError(String(error))}
            onLoadSuccess={(payload) => onPageCountChange?.(payload.numPages)}
          >
            <div
              ref={pageShellRef}
              data-pdf-viewer-id={viewerId}
              style={{
                ...styles.pageShell,
                ...(isRegionMode ? styles.pageShellRegionMode : {}),
              }}
              onMouseUp={handleMouseUp}
            >
              <Page
                className="pdf-preview-page"
                pageNumber={pageNumber}
                width={pageWidth || undefined}
                renderTextLayer
                renderAnnotationLayer={false}
                loading={<div style={styles.loadingState}>PDF 页面加载中…</div>}
                error={<div style={styles.errorState}>当前页加载失败。</div>}
              />

              <div style={styles.overlayStage}>
                {overlays.map((overlay) =>
                  overlay.rects.map((rect, index) => (
                    <div
                      key={`${overlay.id}:${index}`}
                      style={{
                        ...styles.overlayBox,
                        left: `${rect.x * 100}%`,
                        top: `${rect.y * 100}%`,
                        width: `${rect.width * 100}%`,
                        height: `${rect.height * 100}%`,
                        borderColor: overlay.color ?? "#FACC15",
                        background: `${overlay.color ?? "#FACC15"}20`,
                      }}
                      title={overlay.label || overlay.quoteText || overlay.kind}
                    >
                      {index === 0 && (overlay.label || overlay.quoteText) ? (
                        <span
                          style={{
                            ...styles.overlayLabel,
                            background: overlay.color ?? "#FACC15",
                          }}
                        >
                          {overlay.label || overlay.quoteText}
                        </span>
                      ) : null}
                    </div>
                  ))
                )}

                {textSelection?.rects.map((rect, index) => (
                  <div
                    key={`text-selection:${index}`}
                    style={{
                      ...styles.selectionBox,
                      left: `${rect.x * 100}%`,
                      top: `${rect.y * 100}%`,
                      width: `${rect.width * 100}%`,
                      height: `${rect.height * 100}%`,
                    }}
                  />
                ))}

                {selectedRegion ? (
                  <div
                    style={{
                      ...styles.regionBox,
                      left: `${selectedRegion.x * 100}%`,
                      top: `${selectedRegion.y * 100}%`,
                      width: `${selectedRegion.width * 100}%`,
                      height: `${selectedRegion.height * 100}%`,
                    }}
                  />
                ) : null}

                {isRegionMode ? (
                  <div
                    style={styles.regionCaptureLayer}
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={finishRegionSelection}
                    onPointerCancel={finishRegionSelection}
                  >
                    {draftRegion ? (
                      <div
                        style={{
                          ...styles.regionDraftBox,
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
          <div style={styles.errorState}>当前没有可预览的 PDF。</div>
        )}
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

function buildRect(startX: number, startY: number, endX: number, endY: number): PdfRect {
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

const styles: Record<string, CSSProperties> = {
  wrap: {
    minHeight: "100%",
  },
  viewport: {
    position: "relative",
    minHeight: 0,
    overflow: "auto",
    paddingTop: 42,
  },
  floatingBar: {
    position: "absolute",
    top: 10,
    right: 10,
    zIndex: 4,
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "flex-end",
    padding: "6px 8px",
    borderRadius: 14,
    background: "rgba(255, 255, 255, 0.92)",
    border: "1px solid rgba(148, 163, 184, 0.24)",
    boxShadow: "0 10px 24px rgba(15, 23, 42, 0.10)",
    backdropFilter: "blur(10px)",
  },
  modeButton: {
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "rgba(148, 163, 184, 0.32)",
    background: "rgba(248, 250, 252, 0.96)",
    color: "var(--ink)",
    height: 28,
    padding: "0 10px",
    fontSize: 12,
    fontWeight: 700,
    borderRadius: 999,
    cursor: "pointer",
  },
  modeButtonActive: {
    borderColor: "rgba(14, 165, 233, 0.36)",
    background: "rgba(14, 165, 233, 0.12)",
    color: "#0369a1",
  },
  selectionBadge: {
    height: 28,
    display: "inline-flex",
    alignItems: "center",
    padding: "0 10px",
    borderRadius: 999,
    background: "rgba(15, 23, 42, 0.05)",
    color: "var(--ink-2)",
    fontSize: 12,
    fontWeight: 600,
  },
  actionButton: {
    border: "1px solid var(--accent)",
    background: "var(--accent)",
    color: "white",
    height: 28,
    padding: "0 11px",
    fontSize: 12,
    fontWeight: 700,
    borderRadius: 999,
    cursor: "pointer",
  },
  clearButton: {
    border: "1px solid rgba(148, 163, 184, 0.32)",
    background: "white",
    color: "var(--ink-2)",
    height: 28,
    padding: "0 10px",
    fontSize: 12,
    fontWeight: 600,
    borderRadius: 999,
    cursor: "pointer",
  },
  pageShell: {
    position: "relative",
    width: "100%",
    userSelect: "text",
  },
  pageShellRegionMode: {
    userSelect: "none",
  },
  overlayStage: {
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
  },
  overlayBox: {
    position: "absolute",
    borderWidth: 2,
    borderStyle: "solid",
    borderColor: "#FACC15",
    borderRadius: 6,
    boxSizing: "border-box",
  },
  overlayLabel: {
    position: "absolute",
    left: 0,
    top: -24,
    maxWidth: 220,
    color: "#0f172a",
    fontSize: 11,
    fontWeight: 700,
    lineHeight: 1.2,
    padding: "4px 6px",
    borderRadius: 999,
    boxShadow: "0 6px 16px rgba(15, 23, 42, 0.12)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  selectionBox: {
    position: "absolute",
    background: "rgba(14, 165, 233, 0.18)",
    border: "1px solid rgba(14, 165, 233, 0.34)",
    borderRadius: 4,
    boxSizing: "border-box",
  },
  regionBox: {
    position: "absolute",
    border: "2px solid #0ea5e9",
    background: "rgba(14, 165, 233, 0.12)",
    borderRadius: 8,
    boxSizing: "border-box",
  },
  regionCaptureLayer: {
    position: "absolute",
    inset: 0,
    pointerEvents: "auto",
    cursor: "crosshair",
  },
  regionDraftBox: {
    position: "absolute",
    border: "2px dashed #0ea5e9",
    background: "rgba(14, 165, 233, 0.10)",
    borderRadius: 8,
    boxSizing: "border-box",
  },
  loadingState: {
    minHeight: 320,
    display: "grid",
    placeItems: "center",
    color: "var(--muted)",
    fontSize: 13,
  },
  errorState: {
    minHeight: 320,
    display: "grid",
    placeItems: "center",
    color: "var(--negative)",
    fontSize: 13,
    textAlign: "center",
    padding: 16,
  },
};
