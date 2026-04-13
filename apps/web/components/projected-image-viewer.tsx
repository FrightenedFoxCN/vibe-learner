"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useRef, useState } from "react";
import type { PdfRect, ProjectedPdfOverlay } from "@vibe-learner/shared";

interface ProjectedImageViewerProps {
  fileUrl: string;
  title: string;
  overlays?: ProjectedPdfOverlay[];
  onInsertReference?: (text: string) => void;
}

export function ProjectedImageViewer({
  fileUrl,
  title,
  overlays = [],
  onInsertReference,
}: ProjectedImageViewerProps) {
  const imageShellRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null);
  const draftRegionRef = useRef<PdfRect | null>(null);
  const [draftRegion, setDraftRegion] = useState<PdfRect | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<PdfRect | null>(null);

  const clearSelection = () => {
    dragStateRef.current = null;
    draftRegionRef.current = null;
    setDraftRegion(null);
    setSelectedRegion(null);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!imageShellRef.current) return;
    const rect = imageShellRef.current.getBoundingClientRect();
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: clamp01((event.clientX - rect.left) / Math.max(rect.width, 1)),
      startY: clamp01((event.clientY - rect.top) / Math.max(rect.height, 1)),
    };
    draftRegionRef.current = null;
    setDraftRegion(null);
    setSelectedRegion(null);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId || !imageShellRef.current) return;
    const rect = imageShellRef.current.getBoundingClientRect();
    const nextRegion = buildRect(
      dragState.startX,
      dragState.startY,
      clamp01((event.clientX - rect.left) / Math.max(rect.width, 1)),
      clamp01((event.clientY - rect.top) / Math.max(rect.height, 1)),
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

  const insertRegionReference = () => {
    if (!selectedRegion || !onInsertReference) return;
    onInsertReference(
      `请结合当前投射图片《${title}》这个选区回答：` +
      ` [x=${selectedRegion.x.toFixed(3)}, y=${selectedRegion.y.toFixed(3)}, w=${selectedRegion.width.toFixed(3)}, h=${selectedRegion.height.toFixed(3)}]`
    );
    clearSelection();
  };

  return (
    <div style={styles.wrap}>
      <div style={styles.floatingBar}>
        <span style={styles.selectionBadge}>{selectedRegion ? "已框选" : "图片框选"}</span>
        {selectedRegion ? (
          <button type="button" style={styles.actionButton} onClick={insertRegionReference}>
            插入选区
          </button>
        ) : null}
        {(selectedRegion || draftRegion) ? (
          <button type="button" style={styles.clearButton} onClick={clearSelection}>
            清除
          </button>
        ) : null}
      </div>

      <div
        ref={imageShellRef}
        style={styles.imageShell}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishRegionSelection}
        onPointerCancel={finishRegionSelection}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={fileUrl} alt={title} style={styles.image} />

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
                  borderColor: overlay.color ?? "#F97316",
                  background: `${overlay.color ?? "#F97316"}20`,
                }}
                title={overlay.label || overlay.quoteText || overlay.kind}
              >
                {index === 0 && (overlay.label || overlay.quoteText) ? (
                  <span style={{ ...styles.overlayLabel, background: overlay.color ?? "#F97316" }}>
                    {overlay.label || overlay.quoteText}
                  </span>
                ) : null}
              </div>
            ))
          )}

          {selectedRegion ? (
            <div
              style={{
                ...styles.selectionBox,
                left: `${selectedRegion.x * 100}%`,
                top: `${selectedRegion.y * 100}%`,
                width: `${selectedRegion.width * 100}%`,
                height: `${selectedRegion.height * 100}%`,
              }}
            />
          ) : null}

          {draftRegion ? (
            <div
              style={{
                ...styles.draftBox,
                left: `${draftRegion.x * 100}%`,
                top: `${draftRegion.y * 100}%`,
                width: `${draftRegion.width * 100}%`,
                height: `${draftRegion.height * 100}%`,
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
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
    position: "relative",
    minHeight: "100%",
    paddingTop: 42,
  },
  floatingBar: {
    position: "absolute",
    top: 10,
    right: 10,
    zIndex: 3,
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
  selectionBadge: {
    height: 28,
    display: "inline-flex",
    alignItems: "center",
    padding: "0 10px",
    borderRadius: 999,
    background: "rgba(15, 23, 42, 0.05)",
    color: "var(--ink-2)",
    fontSize: 12,
    fontWeight: 700,
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
  imageShell: {
    position: "relative",
    width: "100%",
    cursor: "crosshair",
    userSelect: "none",
  },
  image: {
    display: "block",
    width: "100%",
    height: "auto",
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
    borderColor: "#F97316",
    borderRadius: 8,
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
    border: "2px solid #0ea5e9",
    background: "rgba(14, 165, 233, 0.14)",
    borderRadius: 8,
    boxSizing: "border-box",
  },
  draftBox: {
    position: "absolute",
    border: "2px dashed #0ea5e9",
    background: "rgba(14, 165, 233, 0.10)",
    borderRadius: 8,
    boxSizing: "border-box",
  },
};
