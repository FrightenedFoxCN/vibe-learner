import type { DiagnosticLinkPage } from "./diagnostic-query";

export function diagnosticLinkPagination(
  page: DiagnosticLinkPage | null,
  retainedCount: number,
) {
  if (page?.gap === "diagnostic_store_unavailable") {
    return {
      alert: retainedCount
        ? "关联请求续页不可用；已读取的关联仍保留，请重试。"
        : "关联请求暂不可用，请重试。",
      status: null,
      next: retainedCount ? "重试读取关联请求" : null,
    };
  }
  if (page?.gap === "no_correlation_recorded_or_retained") {
    return {
      alert: null,
      status: retainedCount ? "暂无更多保留的关联请求。" : "没有记录或保留关联请求。",
      next: null,
    };
  }
  return {
    alert: null,
    status: null,
    // v1 does not include has_more; a full page may require an empty terminal read.
    next: page?.items.length === 100 ? "继续读取关联请求" : null,
  };
}
