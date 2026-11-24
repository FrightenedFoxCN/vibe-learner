"use client";

import dynamic from "next/dynamic";
import { useDeferredValue, useId, useRef, useState, type KeyboardEvent } from "react";
import {
  formatStudyMarkdown,
  type MarkdownAction,
} from "../../lib/study-note-markdown";

const Preview = dynamic(() => import("./study-note-markdown-preview"), {
  ssr: false,
  loading: () => (
    <p className="study-notes-muted" role="status">
      正在加载预览…
    </p>
  ),
});

const ACTIONS: readonly [MarkdownAction, string][] = [
  ["heading", "标题"],
  ["bold", "粗体"],
  ["italic", "斜体"],
  ["strike", "删除线"],
  ["quote", "引用"],
  ["bullet", "无序列表"],
  ["numbered", "编号列表"],
  ["task", "任务列表"],
  ["link", "链接"],
  ["code", "行内代码"],
  ["fence", "代码块"],
  ["table", "表格"],
  ["math", "公式"],
];
type Mode = "source" | "preview" | "split";

export function StudyNoteMarkdownEditor({
  value,
  expanded,
  disabled,
  limit,
  onChange,
}: {
  value: string;
  expanded: boolean;
  disabled: boolean;
  limit: number;
  onChange: (value: string) => void;
}) {
  const [mode, setMode] = useState<Mode>(expanded ? "split" : "source");
  const editor = useRef<HTMLTextAreaElement>(null);
  const statusId = useId();
  const count = Array.from(value).length;
  const preview = useDeferredValue(value);

  function format(action: MarkdownAction) {
    const field = editor.current;
    if (!field || disabled || mode === "preview") return;
    const edit = formatStudyMarkdown(
      field.value,
      field.selectionStart,
      field.selectionEnd,
      action,
    );
    const next =
      field.value.slice(0, edit.from) + edit.text + field.value.slice(edit.to);
    field.focus({ preventScroll: true });
    field.setSelectionRange(edit.from, edit.to);
    // insertText keeps the edit in the browser's native undo stack where supported.
    if (!document.execCommand("insertText", false, edit.text)) {
      field.setRangeText(edit.text, edit.from, edit.to);
    }
    onChange(next);
    field.setSelectionRange(edit.selectionStart, edit.selectionEnd);
  }

  function onEditorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.nativeEvent.isComposing ||
      !(event.metaKey || event.ctrlKey) ||
      event.altKey ||
      event.shiftKey
    )
      return;
    const key = event.key.toLowerCase();
    if (key !== "b" && key !== "i") return;
    event.preventDefault();
    format(key === "b" ? "bold" : "italic");
  }

  return (
    <div className="study-markdown-editor">
      <div
        className="study-notes-row study-markdown-modes"
        role="group"
        aria-label="Markdown 显示方式"
      >
        <button
          type="button"
          aria-pressed={mode === "source"}
          onClick={() => setMode("source")}
        >
          源码
        </button>
        <button
          type="button"
          aria-pressed={mode === "preview"}
          onClick={() => setMode("preview")}
        >
          预览
        </button>
        {expanded ? (
          <button
            type="button"
            aria-pressed={mode === "split"}
            onClick={() => setMode("split")}
          >
            分栏
          </button>
        ) : null}
        <span
          id={statusId}
          className={count > limit ? "study-notes-error" : "study-notes-muted"}
        >
          {count.toLocaleString()} / {limit.toLocaleString()} 字符
        </span>
      </div>
      {expanded && mode !== "preview" ? (
        <div
          className="study-notes-row study-markdown-tools"
          role="group"
          aria-label="Markdown 格式"
        >
          {ACTIONS.map(([action, label]) => (
            <button
              key={action}
              type="button"
              disabled={disabled}
              onClick={() => format(action)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
      <div
        className={
          mode === "split"
            ? "study-markdown-panes study-markdown-split"
            : "study-markdown-panes"
        }
      >
        <textarea
          ref={editor}
          value={value}
          rows={7}
          maxLength={limit * 2}
          aria-label="Markdown 正文"
          aria-describedby={statusId}
          hidden={mode === "preview"}
          disabled={disabled}
          spellCheck={false}
          placeholder="用 Markdown 写下你的笔记…"
          onChange={(event) => onChange(event.currentTarget.value)}
          onKeyDown={onEditorKeyDown}
        />
        {mode !== "source" ? (
          <section className="study-markdown-preview" aria-label="Markdown 预览">
            {count > limit ? (
              <p className="study-notes-muted">正文超出长度上限，暂不预览。</p>
            ) : (
              <Preview source={preview} />
            )}
          </section>
        ) : null}
      </div>
    </div>
  );
}
