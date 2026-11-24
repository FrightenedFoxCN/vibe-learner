import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { StudyNote, StudyNoteList } from "@vibe-learner/shared";
import {
  InvalidStudyNotesArchiveError,
  StudyNoteRevisionConflictError,
  studyNotesData,
} from "../../lib/data/study-notes";
import { isApiHttpError } from "../../lib/http-error";
import {
  draftFromNote,
  isStudyNoteDraftDirty,
  rebaseStudyNoteDraft,
  StudyNotesView,
  type StudyNoteDraft,
} from "../../lib/study-notes-view";

export interface StudyNotesOpenRequest {
  sessionId: string;
  noteId: string;
  noteRevision: number;
}

interface Options {
  sessionId: string;
  visible: boolean;
  openRequest: StudyNotesOpenRequest | null;
  onOpenRequestHandled: (request: StudyNotesOpenRequest) => void;
  readDraft: (sessionId: string) => StudyNoteDraft | null;
  storeDraft: (sessionId: string, next: StudyNoteDraft | null) => void;
}

export function useStudyNotes({
  sessionId,
  visible,
  openRequest,
  onOpenRequestHandled,
  readDraft,
  storeDraft,
}: Options) {
  const [view] = useState(() => new StudyNotesView(sessionId));
  const [draft, setDraft] = useState(() => readDraft(sessionId));
  const [query, setQuery] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [listEpoch, setListEpoch] = useState(0);
  const [list, setList] = useState<StudyNoteList | null>(null);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [detailBusy, setDetailBusy] = useState(false);
  const [writeBusy, setWriteBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState<{
    revision: number;
    latest?: StudyNote;
  } | null>(null);
  const [exportAfter, setExportAfter] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const handledRequest = useRef<StudyNotesOpenRequest | null>(null);

  useLayoutEffect(() => () => view.close(), [view]);

  const updateDraft = useCallback(
    (next: StudyNoteDraft | null) => {
      setDraft(next);
      storeDraft(
        sessionId,
        next && (next.unconfirmed || isStudyNoteDraftDirty(next)) ? next : null,
      );
    },
    [sessionId, storeDraft],
  );

  const reload = useCallback(() => {
    view.cancel("list");
    setList(null);
    setListError("");
    setListEpoch((value) => value + 1);
  }, [view]);

  const loadList = useCallback(
    async (offset: number) => {
      const token = view.begin("list", JSON.stringify([query, offset]));
      setLoading(true);
      setListError("");
      try {
        const page = await studyNotesData.list(sessionId, {
          q: query,
          offset,
          signal: token.signal,
        });
        if (!view.current(token)) return;
        setList((old) => {
          if (!offset || !old) return page;
          const ids = new Set(old.items.map((item) => item.id));
          return {
            ...page,
            items: [...old.items, ...page.items.filter((item) => !ids.has(item.id))],
          };
        });
      } catch {
        if (view.current(token)) setListError("未能读取笔记，请重试。");
      } finally {
        if (view.current(token)) {
          view.finish(token);
          setLoading(false);
        }
      }
    },
    [query, sessionId, view],
  );

  useEffect(() => {
    if (!visible) return;
    void loadList(0);
    return () => view.cancel("list");
  }, [visible, loadList, listEpoch, view]);

  const canLeaveDraft = useCallback(
    () =>
      !draft ||
      (!draft.unconfirmed && !isStudyNoteDraftDirty(draft)) ||
      window.confirm("放弃当前未保存的笔记草稿？"),
    [draft],
  );

  const openNote = useCallback(
    async (noteId: string, referenceRevision?: number) => {
      if (view.busy("write")) return;
      if (
        draft?.original?.id === noteId &&
        (draft.unconfirmed || isStudyNoteDraftDirty(draft))
      ) {
        setNotice("这条笔记正在编辑。草稿已保留。");
        return;
      }
      if (!canLeaveDraft()) return;
      const token = view.begin("detail", noteId);
      setDetailBusy(true);
      setError("");
      setNotice("");
      try {
        const note = await studyNotesData.get(sessionId, noteId, token.signal);
        if (!view.current(token)) return;
        updateDraft(draftFromNote(note));
        setConflict(null);
        if (referenceRevision !== undefined && referenceRevision !== note.revision) {
          setNotice("这条笔记在聊天检索后已修改，当前显示最新保存版本。");
        }
      } catch (err) {
        if (view.current(token))
          setError(
            isApiHttpError(err) && err.status === 404
              ? "这条笔记已不可用，可能已删除。"
              : "未能打开笔记，请重试。",
          );
      } finally {
        if (view.current(token)) {
          view.finish(token);
          setDetailBusy(false);
        }
      }
    },
    [canLeaveDraft, draft, sessionId, updateDraft, view],
  );

  useEffect(() => {
    if (
      !visible ||
      writeBusy ||
      !openRequest ||
      openRequest.sessionId !== sessionId ||
      handledRequest.current === openRequest
    )
      return;
    handledRequest.current = openRequest;
    void openNote(openRequest.noteId, openRequest.noteRevision);
    onOpenRequestHandled(openRequest);
  }, [onOpenRequestHandled, openNote, openRequest, sessionId, visible, writeBusy]);

  function switchEditor(next: StudyNoteDraft | null) {
    if (view.busy("write") || !canLeaveDraft()) return;
    view.cancel("detail");
    setDetailBusy(false);
    updateDraft(next);
    setConflict(null);
    setNotice("");
    setError("");
  }

  async function write(
    target: string,
    action: (current: () => boolean) => Promise<string>,
  ) {
    if (view.busy("write") || view.busy("detail")) return;
    const token = view.begin("write", target);
    const current = () => view.current(token);
    setWriteBusy(true);
    setError("");
    setNotice("");
    try {
      const message = await action(current);
      if (!current()) return;
      setNotice(message);
      reload();
    } catch (err) {
      if (!current()) return;
      if (err instanceof StudyNoteRevisionConflictError) {
        setConflict({ revision: err.current_revision });
        setError("同一条笔记已有更新。草稿未被覆盖，请先比较最新版本。");
      } else if (isApiHttpError(err) && err.status === 404) {
        setError("笔记或会话已不存在。草稿仍可复制。");
      } else if (
        err instanceof InvalidStudyNotesArchiveError ||
        (isApiHttpError(err) && err.status < 500)
      ) {
        setError("请求未通过校验，请检查笔记、归档格式或旧记忆键。");
      } else {
        setError("暂未确认写入结果。请查看已保存的列表，不要直接重试。");
        reload();
      }
    } finally {
      if (current()) {
        view.finish(token);
        setWriteBusy(false);
      }
    }
  }

  function save() {
    if (
      !draft ||
      draft.unconfirmed ||
      conflict ||
      !isStudyNoteDraftDirty(draft) ||
      !draft.fields.title.trim() ||
      !draft.fields.content.trim()
    )
      return;
    const { original, fields } = draft;
    void write(original?.id ?? "new", async (current) => {
      const unconfirmed = { ...draft, unconfirmed: true };
      updateDraft(unconfirmed);
      try {
        const note = original
          ? await studyNotesData.replace(sessionId, original.id, {
              ...fields,
              expected_revision: original.revision,
            })
          : await studyNotesData.create(sessionId, fields);
        // A late receipt can clear only its own originating draft.
        if (readDraft(sessionId) === unconfirmed) storeDraft(sessionId, null);
        if (current()) {
          updateDraft(draftFromNote(note));
          setConflict(null);
        }
      } catch (err) {
        if (
          isApiHttpError(err) &&
          err.status < 500 &&
          readDraft(sessionId) === unconfirmed
        ) {
          if (current()) updateDraft(draft);
          else storeDraft(sessionId, draft);
        }
        throw err;
      }
      return "笔记已保存。";
    });
  }

  function remove() {
    const original = draft?.original;
    if (
      !original ||
      conflict ||
      draft.unconfirmed ||
      !window.confirm("删除这条已保存的笔记？当前草稿也会关闭。")
    )
      return;
    void write(original.id, async (current) => {
      await studyNotesData.remove(sessionId, original.id, original.revision);
      if (current()) updateDraft(null);
      return "笔记已删除。";
    });
  }

  async function compareLatest() {
    if (!draft?.original || !conflict || view.busy("write")) return;
    const token = view.begin("detail", draft.original.id);
    setDetailBusy(true);
    try {
      const latest = await studyNotesData.get(
        sessionId,
        draft.original.id,
        token.signal,
      );
      if (view.current(token)) setConflict({ revision: latest.revision, latest });
    } catch (err) {
      if (view.current(token))
        setError(
          isApiHttpError(err) && err.status === 404
            ? "笔记已删除。草稿仍可复制。"
            : "未能读取最新版本，请重试。",
        );
    } finally {
      if (view.current(token)) {
        view.finish(token);
        setDetailBusy(false);
      }
    }
  }

  function rebase() {
    if (!conflict?.latest || !draft) return;
    updateDraft(rebaseStudyNoteDraft(draft, conflict.latest));
    setConflict(null);
    setError("");
    setNotice("已读回最新版本；草稿仍未保存。确认内容后可再次保存。");
  }

  async function downloadExport(next: boolean) {
    if (view.busy("export")) return;
    const after = next ? exportAfter : null;
    if (next && !after) return;
    const token = view.begin("export", after ?? "first");
    setExportBusy(true);
    setError("");
    try {
      const archive = await studyNotesData.exportPage(sessionId, {
        after: after ?? undefined,
        signal: token.signal,
      });
      if (!view.current(token)) return;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(archive)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = after
        ? "study-notes-v1-" + after + ".json"
        : "study-notes-v1.json";
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      setExportAfter(archive.next_after ?? null);
    } catch {
      if (view.current(token)) setError("未能导出笔记，请重试。");
    } finally {
      if (view.current(token)) {
        view.finish(token);
        setExportBusy(false);
      }
    }
  }

  function importArchive(file: File) {
    if (file.size > 5 * 1024 * 1024) {
      setError("JSON 归档不可超过 5 MiB。");
      return;
    }
    void write("archive", async (current) => {
      let archive: unknown;
      try {
        archive = JSON.parse(await file.text());
      } catch {
        throw new InvalidStudyNotesArchiveError();
      }
      if (!current()) return "";
      const receipt = await studyNotesData.importArchive(sessionId, archive);
      return "已导入 " + receipt.note_ids.length + " 条笔记。";
    });
  }

  function importMemory(keys: string[]) {
    void write("legacy", async () => {
      const receipt = await studyNotesData.importMemory(sessionId, keys);
      return "已复制 " + receipt.note_ids.length + " 条旧记忆。";
    });
  }

  return {
    draft,
    queryInput,
    setQueryInput,
    list,
    loading,
    listError,
    detailBusy,
    writeBusy,
    error,
    notice,
    conflict,
    exportAfter,
    exportBusy,
    reload,
    search: () => {
      setQuery(queryInput.trim());
      reload();
    },
    loadMore: () => {
      if (list?.next_offset != null && !view.busy("list"))
        void loadList(list.next_offset);
    },
    openNote,
    save,
    remove,
    compareLatest,
    rebase,
    downloadExport,
    importArchive,
    importMemory,
    newNote: () => switchEditor(draftFromNote(null)),
    discard: () => switchEditor(null),
    change: (field: "title" | "content", value: string) => {
      if (draft && !view.busy("write") && !view.busy("detail"))
        updateDraft({ ...draft, fields: { ...draft.fields, [field]: value } });
    },
    confirmReviewed: () => {
      if (draft && !view.busy("write")) updateDraft({ ...draft, unconfirmed: false });
    },
  };
}
