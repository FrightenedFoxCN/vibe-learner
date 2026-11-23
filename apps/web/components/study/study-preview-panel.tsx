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
  hasPlan,
}: {
  preview: ReturnType<typeof useStudyPreview>;
  hasPlan: boolean;
}) {
  const {
    previewState: effectivePreview,
    isPdfPreviewOpen,
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
    setIsPdfPreviewOpen,
  } = preview;

  if (!effectivePreview) {
    return (
      <div className="study-dialog-empty-dock">
        {hasPlan
          ? "当前计划未关联教材，可直接围绕章节目标展开对话。"
          : "请先在计划页完成教材上传或目标计划生成。"}
      </div>
    );
  }

  if (!isPdfPreviewOpen) {
    return (
      <button
        type="button"
        className="study-dialog-preview-dock"
        onClick={() => setIsPdfPreviewOpen(true)}
        aria-label="打开材料预览"
        title="打开材料预览"
      >
        <MaterialIcon name="menu_book" size={16} />
        {isImage ? "图像" : `p.${previewPage}`}
      </button>
    );
  }

  return (
    <aside className="study-dialog-preview-window">
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
            <button
              type="button"
              className="study-dialog-pdf-icon-btn"
              onClick={() => setIsPdfPreviewOpen(false)}
              title="收拢"
              aria-label="收拢"
            >
              <MaterialIcon name="close" size={15} />
            </button>
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
