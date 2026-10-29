"use client";

import { useEffect, useState } from "react";
import type { DocumentPageNumbering, LearningPlan } from "@vibe-learner/shared";
import { getDocumentPageNumbering } from "../lib/data/documents";
import { formatPhysicalPdfRanges } from "../lib/planning-page-scope";

export function PlanPageScope({ plan }: { plan: LearningPlan }) {
  const ranges = plan.planningIntent?.pdfPageRanges;
  const explicit = ranges?.status === "user_explicit" ? ranges.value : [];
  const boundaryPages = [
    ...new Set(explicit.flatMap((range) => [range.pageStart, range.pageEnd])),
  ].slice(0, 64);
  const key = boundaryPages.join(",");
  const [numbering, setNumbering] = useState<DocumentPageNumbering | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setNumbering(null);
    setFailed(false);
    const pages = key ? key.split(",").map(Number) : [];
    if (plan.documentId && pages.length)
      getDocumentPageNumbering(plan.documentId, pages)
        .then((value) => {
          if (active) setNumbering(value);
        })
        .catch(() => {
          if (active) setFailed(true);
        });
    return () => {
      active = false;
    };
  }, [plan.id, plan.documentId, key]);
  if (!explicit.length) return null;
  return (
    <section
      className="plan-revision-panel plan-revision-content"
      aria-label="计划页码范围"
    >
      <h2>PDF 物理页范围：{formatPhysicalPdfRanges(explicit)}</h2>
      <p>
        这是创建计划时保存的限定范围；所有排期锚点、内容切片和取证均使用从 1 开始的 PDF
        页序。
      </p>
      {numbering ? (
        <>
          <p>
            印刷页标签来自当前教材的 PDF 元数据（教材版本 {numbering.documentRevision}
            ），只作对照，不替代物理页。
          </p>
          <ul>
            {numbering.pages.map((page) => (
              <li key={page.physicalPdfPage}>
                PDF 物理第 {page.physicalPdfPage} 页 →{" "}
                {page.printedPage
                  ? `印刷标签 ${page.printedPage.label}`
                  : "未提供印刷标签"}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>
          {failed
            ? "印刷页标签暂时不可用；已保存的物理页范围仍有效。"
            : "正在读取页码对照…"}
        </p>
      )}
    </section>
  );
}
