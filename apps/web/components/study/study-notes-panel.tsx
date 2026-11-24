import { useEffect, useRef, useState } from "react";
import { isStudyNoteDraftDirty, type StudyNoteDraft } from "../../lib/study-notes-view";
import { useStudyNotes, type StudyNotesOpenRequest } from "./use-study-notes";
import "./study-notes.css";

interface StudyNotesPanelProps {
  sessionId: string;
  visible: boolean;
  openRequest: StudyNotesOpenRequest | null;
  onOpenRequestHandled: (request: StudyNotesOpenRequest) => void;
  memoryKeys: string[];
  onClose: () => void;
  readDraft: (sessionId: string) => StudyNoteDraft | null;
  storeDraft: (sessionId: string, draft: StudyNoteDraft | null) => void;
}

export function StudyNotesPanel(props: StudyNotesPanelProps) {
  const notes = useStudyNotes(props);
  const { draft, conflict } = notes;
  const editorRef = useRef<HTMLFormElement>(null);
  const openedNoteId = draft?.original?.id;
  useEffect(() => {
    if (props.visible && openedNoteId)
      editorRef.current?.scrollIntoView({ block: "nearest" });
  }, [openedNoteId, props.visible]);
  const disabled = notes.detailBusy || notes.writeBusy;
  const dirty = draft ? isStudyNoteDraftDirty(draft) : false;
  const tooLong =
    draft &&
    ([...draft.fields.title].length > 160 || [...draft.fields.content].length > 4_000);
  const canSave =
    draft &&
    dirty &&
    !tooLong &&
    !draft.unconfirmed &&
    !conflict &&
    Boolean(draft.fields.title.trim() && draft.fields.content.trim());

  return (
    <aside
      id="study-notes-panel"
      className="study-notes-panel"
      aria-labelledby="study-notes-heading"
      hidden={!props.visible}
    >
      <header className="study-notes-row study-notes-top">
        <h2 id="study-notes-heading">笔记</h2>
        <button type="button" onClick={props.onClose}>
          关闭
        </button>
      </header>
      <div className="study-notes-body">
        <form
          className="study-notes-row"
          role="search"
          aria-label="会话笔记"
          onSubmit={(event) => {
            event.preventDefault();
            notes.search();
          }}
        >
          <input
            type="search"
            value={notes.queryInput}
            maxLength={120}
            aria-label="搜索标题和正文"
            placeholder="搜索标题或正文"
            onChange={(event) => notes.setQueryInput(event.target.value)}
          />
          <button type="submit">搜索</button>
          <button
            type="button"
            className="study-notes-primary"
            disabled={notes.writeBusy}
            onClick={notes.newNote}
          >
            新建
          </button>
        </form>
        {notes.loading ? (
          <p role="status" className="study-notes-muted">
            正在读取笔记…
          </p>
        ) : null}
        {notes.listError ? (
          <div role="alert" className="study-notes-row">
            <span>{notes.listError}</span>
            <button type="button" onClick={notes.reload}>
              重试
            </button>
          </div>
        ) : null}
        {notes.list ? (
          notes.list.items.length ? (
            <ul className="study-notes-list" aria-label="已保存的笔记">
              {notes.list.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-current={draft?.original?.id === item.id ? "true" : undefined}
                    disabled={notes.writeBusy}
                    onClick={() => void notes.openNote(item.id)}
                  >
                    <strong>{item.title}</strong>
                    <span>{item.excerpt}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="study-notes-muted">没有匹配的已保存笔记。</p>
          )
        ) : null}
        {notes.list?.next_offset != null ? (
          <button type="button" disabled={notes.loading} onClick={notes.loadMore}>
            加载更多
          </button>
        ) : null}
        {notes.notice ? (
          <p className="study-notes-muted" role="status">
            {notes.notice}
          </p>
        ) : null}
        {notes.error ? (
          <p className="study-notes-error" role="alert">
            {notes.error}
          </p>
        ) : null}
        {notes.detailBusy ? (
          <p role="status" className="study-notes-muted">
            正在读回笔记…
          </p>
        ) : null}
        {draft ? (
          <form
            ref={editorRef}
            className="study-notes-editor"
            aria-label="编辑笔记"
            onSubmit={(event) => {
              event.preventDefault();
              notes.save();
            }}
          >
            <p className="study-notes-muted" role="status">
              {notes.writeBusy
                ? "正在提交…"
                : dirty
                  ? "未保存草稿"
                  : draft.original
                    ? "已保存 · 版本 " + draft.original.revision
                    : "新笔记"}
            </p>
            <label>
              标题
              <input
                value={draft.fields.title}
                maxLength={320}
                required
                disabled={disabled}
                onChange={(event) => notes.change("title", event.target.value)}
              />
            </label>
            <label>
              正文
              <textarea
                value={draft.fields.content}
                rows={7}
                maxLength={8_000}
                required
                disabled={disabled}
                onChange={(event) => notes.change("content", event.target.value)}
              />
            </label>
            {tooLong ? (
              <p className="study-notes-error" role="alert">
                标题最多 160 字符，正文最多 4,000 字符。
              </p>
            ) : null}
            {draft.unconfirmed && !notes.writeBusy ? (
              <div className="study-notes-warning">
                <p>上次保存结果未确认。请先核对已保存列表，避免写入重复笔记。</p>
                <button type="button" onClick={notes.confirmReviewed}>
                  已核对，继续编辑
                </button>
              </div>
            ) : null}
            {conflict ? (
              <div className="study-notes-warning">
                <p>服务器最新版本：{conflict.revision}。</p>
                {conflict.latest ? (
                  <>
                    <details open>
                      <summary>对照最新标题和正文</summary>
                      <strong>{conflict.latest.title}</strong>
                      <pre>{conflict.latest.content}</pre>
                    </details>
                    <button type="button" disabled={disabled} onClick={notes.rebase}>
                      以最新版本为基准，保留草稿
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => void notes.compareLatest()}
                  >
                    读回最新版本
                  </button>
                )}
              </div>
            ) : null}
            <div className="study-notes-row">
              <button
                type="submit"
                className="study-notes-primary"
                disabled={disabled || !canSave}
              >
                保存
              </button>
              <button type="button" disabled={notes.writeBusy} onClick={notes.discard}>
                关闭编辑
              </button>
              {draft.original ? (
                <button
                  type="button"
                  className="study-notes-danger"
                  disabled={disabled || Boolean(conflict) || draft.unconfirmed}
                  onClick={notes.remove}
                >
                  删除
                </button>
              ) : null}
            </div>
          </form>
        ) : null}
        <details className="study-notes-tools">
          <summary>导入与导出</summary>
          <div className="study-notes-row">
            <button
              type="button"
              disabled={notes.exportBusy}
              onClick={() => void notes.downloadExport(false)}
            >
              导出 JSON
            </button>
            {notes.exportAfter ? (
              <button
                type="button"
                disabled={notes.exportBusy}
                onClick={() => void notes.downloadExport(true)}
              >
                导出下一批
              </button>
            ) : null}
          </div>
          <label>
            导入 JSON（追加，不覆盖）
            <input
              type="file"
              accept=".json,application/json"
              disabled={disabled}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (file) notes.importArchive(file);
              }}
            />
          </label>
          {props.memoryKeys.length ? (
            <LegacyMemoryPicker
              keys={props.memoryKeys}
              disabled={disabled}
              onImport={notes.importMemory}
            />
          ) : null}
        </details>
      </div>
    </aside>
  );
}

function LegacyMemoryPicker({
  keys,
  disabled,
  onImport,
}: {
  keys: string[];
  disabled: boolean;
  onImport: (selection: string[]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const active = selected.filter((key) => keys.includes(key));
  return (
    <details>
      <summary>从会话的旧记忆复制</summary>
      <div className="study-notes-legacy" role="group" aria-label="选择旧记忆">
        {keys.map((key) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={active.includes(key)}
              disabled={disabled || (!active.includes(key) && active.length >= 200)}
              onChange={(event) => {
                const checked = event.currentTarget.checked;
                setSelected(
                  checked ? [...active, key] : active.filter((entry) => entry !== key),
                );
              }}
            />
            {key}
          </label>
        ))}
      </div>
      <button
        type="button"
        disabled={disabled || !active.length}
        onClick={() => {
          onImport(active);
          setSelected([]);
        }}
      >
        复制所选（保留原记忆）
      </button>
    </details>
  );
}
