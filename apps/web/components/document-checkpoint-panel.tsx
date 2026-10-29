"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentCheckpoint, DocumentRecord } from "@vibe-learner/shared";
import { getDocumentCheckpoint, processDocument } from "../lib/data/documents";
import { isApiHttpError } from "../lib/http-error";

const storageKey = "vibe-learner:document-checkpoint:v1";
const defaultPort = { getDocumentCheckpoint, processDocument };

export function DocumentCheckpointPanel({
  documentId,
  status,
  onContinue,
  blocked = false,
  port = defaultPort,
}: {
  documentId: string;
  status: string;
  onContinue: (document: DocumentRecord) => void;
  blocked?: boolean;
  port?: typeof defaultPort;
}) {
  const [record, setRecord] = useState<DocumentCheckpoint | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [uncertain, setUncertain] = useState(false);
  const [result, setResult] = useState<DocumentRecord | null>(null);
  const lifetime = useRef(0),
    flight = useRef(false);
  useEffect(() => {
    const epoch = ++lifetime.current;
    let id = documentId;
    if (id) {
      try {
        window.sessionStorage.setItem(storageKey, id);
      } catch {
        /* persistence remains optional for known server checkpoints */
      }
    } else {
      try {
        id = window.sessionStorage.getItem(storageKey) ?? "";
      } catch {
        /* query needs a selected document */
      }
    }
    setSourceId(id);
    setRecord(null);
    setResult(null);
    setNotice("");
    setUncertain(false);
    flight.current = false;
    setBusy(false);
    if (id)
      port
        .getDocumentCheckpoint(id)
        .then((value) => {
          if (epoch === lifetime.current) {
            setRecord(value);
            setResult(value.result);
          }
        })
        .catch((error) => {
          if (epoch !== lifetime.current) return;
          if (isApiHttpError(error) && error.status === 404) return;
          setNotice("暂时无法读取保存进度，请稍后查询。");
        });
    return () => {
      lifetime.current = epoch + 1;
    };
  }, [documentId, status, port]);
  async function query() {
    if (flight.current || !sourceId) return;
    const epoch = lifetime.current;
    flight.current = true;
    setBusy(true);
    try {
      let value = await port.getDocumentCheckpoint(sourceId, record?.operationId);
      if (value.childOperationId)
        value = await port.getDocumentCheckpoint(sourceId, value.childOperationId);
      if (epoch !== lifetime.current) return;
      setRecord(value);
      setResult(value.result);
      setNotice("");
      if (value.operationStatus !== "running" && value.childOperationId !== null)
        setUncertain(false);
    } catch {
      if (epoch === lifetime.current)
        setNotice("查询失败，已保存的进度不会被清除。请稍后重试。");
    } finally {
      if (epoch === lifetime.current) {
        flight.current = false;
        setBusy(false);
      }
    }
  }
  async function resume() {
    if (
      !record ||
      flight.current ||
      blocked ||
      !["failed", "interrupted"].includes(record.operationStatus)
    )
      return;
    const epoch = lifetime.current;
    flight.current = true;
    setBusy(true);
    setNotice("正在从保存进度继续处理…");
    try {
      const document = await port.processDocument(sourceId, {
        forceOcr: record.forceOcr,
        resumeFromOperationId: record.operationId,
      });
      if (epoch !== lifetime.current) return;
      setResult(document);
      setUncertain(false);
      setNotice("教材处理已提交。可以使用当前目标生成计划。");
      try {
        const saved = await port.getDocumentCheckpoint(sourceId);
        if (epoch === lifetime.current) setRecord(saved);
      } catch {
        if (epoch === lifetime.current)
          setNotice("教材处理已提交，保存进度暂时无法刷新。可以稍后查询。");
      }
    } catch {
      if (epoch === lifetime.current) {
        setUncertain(true);
        setNotice("续跑结果尚未确认。请查询保存进度；再次继续会使用同一个续跑身份。");
      }
    } finally {
      if (epoch === lifetime.current) {
        flight.current = false;
        setBusy(false);
      }
    }
  }
  if (!record && !notice) return null;
  return (
    <section
      className="plan-revision-panel plan-revision-content"
      aria-label="教材处理保存进度"
      aria-busy={busy}
    >
      <h2>教材处理保存进度</h2>
      {record && (
        <>
          <p>
            已保存 {record.completedPageCount}/{record.pageCount} 页 ·{" "}
            {record.stage === "study_units"
              ? `已保存 ${record.studyUnits.length} 个 Study Units`
              : record.stage === "parsed"
                ? "解析已完成，等待清洗或提交"
                : "逐页提取进度"}
          </p>
          <p>
            {record.projectionState === "checkpoint_only"
              ? "这是中间成果，尚未提交为可学习教材。续跑会保留已完成页，再进行校验与保存。"
              : "该次教材处理已提交。"}
          </p>
          {record.storageLimited && (
            <p>保存进度已达到容量上限；仅复用成功保存的部分，其余内容需要重新处理。</p>
          )}
          {!!record.pages.length && (
            <details>
              <summary>查看最近保存的页面片段</summary>
              {record.pages.map((page) => (
                <p key={page.pageNumber}>
                  PDF 第 {page.pageNumber} 页：{page.textPreview || "本页暂无文本"}
                </p>
              ))}
            </details>
          )}
          {!!record.studyUnits.length && (
            <ul>
              {record.studyUnits.map((unit) => (
                <li key={unit.id}>
                  {unit.title} · PDF {unit.pageStart}–{unit.pageEnd}
                </li>
              ))}
            </ul>
          )}
          {["failed", "interrupted"].includes(record.operationStatus) &&
            !record.childOperationId &&
            !result && (
              <button
                type="button"
                disabled={busy || blocked}
                onClick={() => void resume()}
              >
                {uncertain ? "继续同一次续跑" : "从保存进度继续处理"}
              </button>
            )}
          {result && (
            <button
              type="button"
              disabled={busy || blocked}
              onClick={() => onContinue(result)}
            >
              使用该教材生成计划
            </button>
          )}
        </>
      )}
      {notice && <p role="status">{notice}</p>}
      <button type="button" disabled={busy} onClick={() => void query()}>
        查询保存进度
      </button>
    </section>
  );
}
