import dynamic from "next/dynamic";
import { MaterialIcon } from "../ui/material-icon";
import type { useStudyPreview } from "./use-study-preview";

const ProjectedPdfViewer = dynamic(
  () => import("./projected-pdf-viewer").then((module) => module.ProjectedPdfViewer),
  { ssr: false },
);
const ProjectedImageViewer = dynamic(
  () =>
    import("./projected-image-viewer").then((module) => module.ProjectedImageViewer),
  { ssr: false },
);

export function StudyPreviewPanel({
  preview,
  onClose,
}: {
  preview: ReturnType<typeof useStudyPreview>;
  onClose: () => void;
}) {
  const {
    previewState: effectivePreview,
    previewPage,
    previewPageCount,
    previewTitle,
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
  } = preview;

  if (!effectivePreview) {
    return (
      <aside
        id="study-material-panel"
        className="study-dialog-preview-window study-dialog-preview-no-material"
        aria-label="教材预览"
      >
        <div className="study-dialog-pdf-header-top">
          <h2 className="study-dialog-pdf-title">教材</h2>
          <ClosePreview onClose={onClose} />
        </div>
        <p>当前会话没有可预览的教材或附件。</p>
      </aside>
    );
  }

  return (
    <aside
      id="study-material-panel"
      className="study-dialog-preview-window"
      aria-label="教材预览"
    >
      <div className="study-dialog-pdf-header">
        <div className="study-dialog-pdf-header-top">
          <div className="study-dialog-pdf-header-meta">
            <span className="study-dialog-pdf-title">{previewTitle}</span>
          </div>
          <div className="study-dialog-pdf-header-actions">
            {previewFileUrl ? (
              <a
                href={previewFileUrl}
                target="_blank"
                rel="noreferrer"
                className="study-dialog-pdf-icon-link"
                title="下载原件"
                aria-label="下载原件"
              >
                <MaterialIcon name="download" size={15} />
              </a>
            ) : null}
            <button
              type="button"
              className="study-dialog-pdf-icon-btn"
              onClick={goBack}
              disabled={!canGoBack}
              title="上一页"
              aria-label="上一页"
            >
              <MaterialIcon name="chevron_left" size={16} />
            </button>
            <button
              type="button"
              className="study-dialog-pdf-icon-btn"
              onClick={() => requestPage(1)}
              disabled={!canGoForward}
              title="下一页"
              aria-label="下一页"
            >
              <MaterialIcon name="chevron_right" size={16} />
            </button>
            <ClosePreview onClose={onClose} />
          </div>
        </div>
      </div>
      <div className="study-dialog-preview-stage">
        {previewFileUrl ? (
          <div className="study-dialog-preview-canvas">
            {isImage ? (
              <ProjectedImageViewer
                fileUrl={previewFileUrl}
                title={previewTitle}
                overlays={previewOverlays}
                onInsertReference={insertReference}
              />
            ) : (
              <ProjectedPdfViewer
                fileUrl={previewFileUrl}
                title={previewTitle}
                pageNumber={previewPage}
                overlays={previewOverlays}
                onPageRequest={requestPage}
                onPageCountChange={updatePageCount}
                onInsertReference={insertReference}
              />
            )}
            <div className="study-dialog-preview-meta-float">
              <span className="study-dialog-preview-meta-chip">
                {effectivePreview.kind === "attachment_pdf"
                  ? "会话材料"
                  : effectivePreview.kind === "attachment_image"
                    ? "会话图片"
                    : effectivePreview.kind === "generated_image"
                      ? "AI 图像"
                      : "教材材料"}
              </span>
              {effectivePreview.kind === "attachment_image" ||
              effectivePreview.kind === "generated_image" ? (
                <span className="study-dialog-preview-meta-chip">图像</span>
              ) : (
                <button
                  type="button"
                  className="study-dialog-preview-meta-chip study-dialog-preview-meta-chip-button"
                  onClick={jumpToPreviewPage}
                  title="输入页码跳转"
                  aria-label="输入页码跳转"
                >
                  {`${previewPage}${previewPageCount > 0 ? ` / ${previewPageCount}` : ""}`}
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="study-dialog-preview-empty-state">当前页暂时无法渲染。</div>
        )}
      </div>
    </aside>
  );
}

function ClosePreview({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      className="study-dialog-pdf-icon-btn"
      onClick={onClose}
      title="关闭教材预览"
      aria-label="关闭教材预览"
    >
      <MaterialIcon name="close" size={15} />
    </button>
  );
}
