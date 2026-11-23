"use client";

import type { PointerEvent as ReactPointerEvent } from "react";
import { useRef, useState } from "react";
import type { PdfRect, ProjectedPdfOverlay } from "@vibe-learner/shared";

import { MaterialIcon } from "../ui/material-icon";
import type { StudyOverlayStyle } from "./study-overlay-style";
import "./study-image-viewer.css";

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
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
  } | null>(null);
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
    event.preventDefault();
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
    if (!dragState || dragState.pointerId !== event.pointerId || !imageShellRef.current)
      return;
    event.preventDefault();
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
        ` [x=${selectedRegion.x.toFixed(3)}, y=${selectedRegion.y.toFixed(3)}, w=${selectedRegion.width.toFixed(3)}, h=${selectedRegion.height.toFixed(3)}]`,
    );
    clearSelection();
  };

  return (
    <div className="study-image-viewer-wrap">
      <div className="study-image-viewer-floating-bar">
        <span className="study-image-viewer-selection-badge">
          <MaterialIcon name="crop_free" size={14} />
        </span>
        {selectedRegion ? (
          <button
            type="button"
            className="study-image-viewer-icon-button study-image-viewer-icon-action-button"
            onClick={insertRegionReference}
            title="插入选区"
            aria-label="插入选区"
          >
            <MaterialIcon name="input" size={15} />
          </button>
        ) : null}
        {selectedRegion || draftRegion ? (
          <button
            type="button"
            className="study-image-viewer-icon-button"
            onClick={clearSelection}
            title="清除"
            aria-label="清除"
          >
            <MaterialIcon name="close" size={15} />
          </button>
        ) : null}
      </div>

      <div
        ref={imageShellRef}
        className="study-image-viewer-image-shell"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishRegionSelection}
        onPointerCancel={finishRegionSelection}
      >
        <img src={fileUrl} alt={title} className="study-image-viewer-image" />

        <div className="study-image-viewer-overlay-stage">
          {overlays.map((overlay) =>
            overlay.rects.map((rect, index) => (
              <div
                key={`${overlay.id}:${index}`}
                className="study-image-viewer-overlay-box"
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
                  <span className="study-image-viewer-overlay-label">
                    {overlay.label || overlay.quoteText}
                  </span>
                ) : null}
              </div>
            )),
          )}

          {selectedRegion ? (
            <div
              className="study-image-viewer-selection-box"
              style={{
                left: `${selectedRegion.x * 100}%`,
                top: `${selectedRegion.y * 100}%`,
                width: `${selectedRegion.width * 100}%`,
                height: `${selectedRegion.height * 100}%`,
              }}
            />
          ) : null}

          {draftRegion ? (
            <div
              className="study-image-viewer-draft-box"
              style={{
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
