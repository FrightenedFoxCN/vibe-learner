"use client";

import type {
  PersonaProfile,
  TavernMessage,
  TavernParticipant,
  TavernRoomDetail,
  TavernRoomSummary,
  TavernRun,
  TavernRunRecoveryChain,
} from "@vibe-learner/shared";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
} from "react";

import { type SceneLibraryItemPayload } from "../lib/api";
import { AppLink } from "../lib/app-navigation";
import {
  RUN_STATUS_LABELS,
  STEP_STATUS_LABELS,
  TAVERN_COPY,
} from "../lib/tavern-copy";
import {
  authoritativeFacilitatedRecovery,
  projectParticipantStates,
} from "../lib/tavern-workspace-state";
import { MaterialIcon } from "./material-icon";
import { ProviderTruth } from "./provider-truth";
import { RichTextMessage } from "./rich-text-message";

import type { TavernStoragePort } from "../lib/tavern-workspace-ports";

export function TavernHeader({
  room,
  notice,
  busy,
  runPending,
  onCreate,
  onRefresh,
  onArchiveToggle,
}: {
  room: TavernRoomDetail["room"] | null;
  notice: string;
  busy: boolean;
  runPending: boolean;
  onCreate: () => void;
  onRefresh: () => void;
  onArchiveToggle: () => void;
}) {
  return (
    <header className="tavern-header">
      <div>
        <p className="tavern-eyebrow">Tavern Workspace</p>
        <h1>{room?.title || "角色酒馆"}</h1>
        <p className="tavern-header-status" role="status" aria-live="polite">
          <span
            className={
              !room
                ? "tavern-status-dot empty"
                : room.status === "archived"
                  ? "tavern-status-dot archived"
                  : "tavern-status-dot"
            }
            aria-hidden="true"
          />
          {busy ? "处理中 · " : ""}
          {notice}
          {room ? ` · revision ${room.revision}` : ""}
          <ProviderTruth scope="tavern" />
        </p>
      </div>
      <div className="tavern-header-actions">
        {room ? (
          <>
            <button
              type="button"
              className="tavern-button secondary"
              onClick={onRefresh}
              disabled={busy}
            >
              <MaterialIcon name="refresh" size={16} />
              刷新
            </button>
            <button
              type="button"
              className="tavern-button secondary"
              onClick={onArchiveToggle}
              disabled={busy || runPending}
            >
              {room.status === "active" ? "归档" : "恢复使用"}
            </button>
          </>
        ) : null}
        <button
          type="button"
          className="tavern-button primary"
          onClick={onCreate}
          disabled={busy}
        >
          <MaterialIcon name="add" size={16} />
          新建酒馆
        </button>
      </div>
    </header>
  );
}

export function TavernSessionPanel({
  rooms,
  activeRoomId,
  busy,
  hasMore,
  loadingMore,
  historyTruncated,
  pageError,
  onOpen,
  onLoadMore,
}: {
  rooms: TavernRoomSummary[];
  activeRoomId: string;
  busy: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  historyTruncated: boolean;
  pageError: string;
  onOpen: (roomId: string) => void;
  onLoadMore: () => void;
}) {
  return (
    <section
      className="tavern-panel tavern-session-panel"
      aria-labelledby="tavern-session-title"
    >
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Tavern Session Panel</p>
          <h2 id="tavern-session-title">最近酒馆</h2>
        </div>
        <span className="tavern-count">{rooms.length}</span>
      </div>
      {rooms.length ? (
        <div className="tavern-room-list">
          {rooms.map((room) => (
            <button
              type="button"
              key={room.id}
              className={`tavern-room-item${room.id === activeRoomId ? " active" : ""}`}
              onClick={() => onOpen(room.id)}
              disabled={busy}
              aria-pressed={room.id === activeRoomId}
            >
              <span className="tavern-room-item-title">{room.title}</span>
              <span className="tavern-room-item-meta">
                {room.participantNames
                  .map((name) => name || "未命名角色")
                  .join(" · ") || "无角色"}
              </span>
              <span className="tavern-room-item-meta">
                {room.messageCount} 条消息 ·{" "}
                {room.status === "archived"
                  ? "已归档"
                  : formatShortTime(room.updatedAt)}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="tavern-empty-copy">
          还没有房间。选择 1–6 位人格即可创建。
        </p>
      )}
      <div className="tavern-room-page-status">
        {pageError ? <p role="alert">{pageError}</p> : null}
        {hasMore ? (
          <button
            type="button"
            className="tavern-button secondary tavern-room-more"
            onClick={onLoadMore}
            disabled={busy || loadingMore}
          >
            <MaterialIcon name="expand_more" size={16} />
            {loadingMore
              ? "正在载入…"
              : pageError
                ? "重试载入更多"
                : "载入更多房间"}
          </button>
        ) : rooms.length ? (
          <p>{historyTruncated ? "已显示最近 100 个房间" : "已显示全部房间"}</p>
        ) : null}
      </div>
    </section>
  );
}

export function TavernSetupPanel({
  storage,
  personas,
  scenes,
  busy,
  titleInputRef,
  onCancel,
  onCreate,
}: {
  storage: TavernStoragePort;
  personas: PersonaProfile[];
  scenes: SceneLibraryItemPayload[];
  busy: boolean;
  titleInputRef: RefObject<HTMLInputElement | null>;
  onCancel?: () => void;
  onCreate: (input: {
    title: string;
    personaIds: string[];
    sceneId: string;
    openingPrompt: string;
  }) => Promise<void>;
}) {
  const initialCreationDraft = storage.readTavernCreationDraft();
  const [title, setTitle] = useState(initialCreationDraft?.title ?? "新酒馆");
  const [selectedIds, setSelectedIds] = useState(
    initialCreationDraft?.personaIds ?? [],
  );
  const [sceneId, setSceneId] = useState(initialCreationDraft?.sceneId ?? "");
  const [openingPrompt, setOpeningPrompt] = useState(
    initialCreationDraft?.openingPrompt ?? "",
  );
  const [validation, setValidation] = useState("");
  const usableScenes = scenes.filter((scene) => Boolean(scene.sceneProfile));

  const togglePersona = (personaId: string) => {
    setSelectedIds((current) => {
      if (current.includes(personaId))
        return current.filter((id) => id !== personaId);
      if (current.length >= 6) {
        setValidation("每个酒馆最多加入 6 位人格。");
        return current;
      }
      setValidation("");
      return [...current, personaId];
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setValidation("请填写酒馆标题。");
      return;
    }
    if (selectedIds.length < 1 || selectedIds.length > 6) {
      setValidation("请选择 1–6 位人格角色。");
      return;
    }
    setValidation("");
    await onCreate({
      title: title.trim(),
      personaIds: selectedIds,
      sceneId,
      openingPrompt: openingPrompt.trim(),
    });
  };

  return (
    <section
      className="tavern-panel tavern-setup-panel"
      aria-labelledby="tavern-setup-title"
    >
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Tavern Setup Panel</p>
          <h2 id="tavern-setup-title">创建房间</h2>
        </div>
        {onCancel ? (
          <button
            type="button"
            className="tavern-text-button"
            onClick={onCancel}
          >
            收起
          </button>
        ) : null}
      </div>
      <form
        className="tavern-setup-form"
        onSubmit={(event) => void submit(event)}
        aria-busy={busy}
        aria-describedby={validation ? "tavern-setup-error" : undefined}
      >
        <label>
          <span>标题</span>
          <input
            ref={titleInputRef}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={80}
            disabled={busy}
          />
        </label>
        <fieldset>
          <legend>
            人格角色 <span>{selectedIds.length}/6</span>
          </legend>
          {personas.length ? (
            <div className="tavern-persona-options">
              {personas.map((persona) => (
                <label
                  key={persona.id}
                  className={selectedIds.includes(persona.id) ? "selected" : ""}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(persona.id)}
                    onChange={() => togglePersona(persona.id)}
                    disabled={busy}
                  />
                  <span>
                    <strong>{persona.name || "未命名角色"}</strong>
                    <small>{persona.relationship || persona.summary}</small>
                  </span>
                </label>
              ))}
            </div>
          ) : (
            <p className="tavern-empty-copy">
              人格库为空。先前往{" "}
              <AppLink path="/persona-spectrum" className="tavern-inline-link">
                人格色谱
              </AppLink>{" "}
              创建角色。
            </p>
          )}
        </fieldset>
        <label>
          <span>场景（可选）</span>
          <select
            value={sceneId}
            onChange={(event) => setSceneId(event.target.value)}
            disabled={busy}
          >
            <option value="">不使用场景</option>
            {usableScenes.map((scene) => (
              <option key={scene.sceneId} value={scene.sceneId}>
                {scene.sceneName || scene.sceneProfile?.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>开场白（可选）</span>
          <textarea
            value={openingPrompt}
            onChange={(event) => setOpeningPrompt(event.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="描述初始情境；它会作为可见的导演消息保存。"
            disabled={busy}
          />
        </label>
        {validation ? (
          <p
            id="tavern-setup-error"
            className="tavern-field-error"
            role="alert"
          >
            {validation}
          </p>
        ) : null}
        <button
          type="submit"
          className="tavern-button primary full"
          disabled={busy || !personas.length}
        >
          {busy ? "正在创建…" : "创建并进入"}
        </button>
      </form>
    </section>
  );
}

export function TavernConversationPanel({
  room,
  participants,
  messages,
  messageCount,
  hasOlder,
  loading,
  loadingOlder,
  olderDisabled,
  onLoadOlder,
}: {
  room: TavernRoomDetail["room"] | null;
  participants: TavernParticipant[];
  messages: TavernMessage[];
  messageCount: number;
  hasOlder: boolean;
  loading: boolean;
  loadingOlder: boolean;
  olderDisabled: boolean;
  onLoadOlder: () => Promise<boolean>;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingOlderAnchorRef = useRef<{
    height: number;
    top: number;
    firstSequence: number;
    viewportOffset: number;
  } | null>(null);
  const previousLatestSequence = useRef(0);
  const latestSequence = messages[messages.length - 1]?.sequence ?? 0;
  const names = useMemo(
    () =>
      new Map(
        participants.map((participant) => [
          participant.personaId,
          participant.displayName || "未命名角色",
        ]),
      ),
    [participants],
  );

  useEffect(() => {
    if (latestSequence > previousLatestSequence.current) {
      if (pendingOlderAnchorRef.current) return;
      const scrollBox = scrollRef.current;
      if (scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
      previousLatestSequence.current = latestSequence;
    }
  }, [latestSequence]);

  useLayoutEffect(() => {
    const anchor = pendingOlderAnchorRef.current;
    const scrollBox = scrollRef.current;
    const firstSequence = messages[0]?.sequence;
    if (
      anchor &&
      scrollBox &&
      firstSequence !== undefined &&
      firstSequence < anchor.firstSequence
    ) {
      const anchorElement = scrollBox.querySelector<HTMLElement>(
        `[data-tavern-sequence="${anchor.firstSequence}"]`,
      );
      const priorBehavior = scrollBox.style.scrollBehavior;
      scrollBox.style.scrollBehavior = "auto";
      if (anchorElement) {
        const currentViewportOffset =
          anchorElement.getBoundingClientRect().top -
          scrollBox.getBoundingClientRect().top;
        scrollBox.scrollTop += currentViewportOffset - anchor.viewportOffset;
      } else {
        scrollBox.scrollTop =
          anchor.top + scrollBox.scrollHeight - anchor.height;
      }
      scrollBox.style.scrollBehavior = priorBehavior;
      pendingOlderAnchorRef.current = null;
    }
  }, [messages.length, messages[0]?.sequence]);

  const loadOlder = async () => {
    const scrollBox = scrollRef.current;
    const firstSequence = messages[0]?.sequence ?? 0;
    const firstMessage = scrollBox?.querySelector<HTMLElement>(
      `[data-tavern-sequence="${firstSequence}"]`,
    );
    const viewportOffset =
      firstMessage && scrollBox
        ? firstMessage.getBoundingClientRect().top -
          scrollBox.getBoundingClientRect().top
        : 0;
    pendingOlderAnchorRef.current = scrollBox
      ? {
          height: scrollBox.scrollHeight,
          top: scrollBox.scrollTop,
          firstSequence,
          viewportOffset,
        }
      : null;
    if (!(await onLoadOlder())) pendingOlderAnchorRef.current = null;
  };

  return (
    <section
      className="tavern-panel tavern-conversation-panel"
      aria-labelledby="tavern-conversation-title"
    >
      <div className="tavern-panel-heading conversation-heading">
        <div>
          <p className="tavern-kicker">Tavern Conversation Panel</p>
          <h2 id="tavern-conversation-title">对话记录</h2>
        </div>
        <span className="tavern-count">
          {messages.length}/{messageCount}
        </span>
      </div>
      <p className="sr-only" aria-live="polite">
        {loadingOlder
          ? "正在载入更早消息"
          : latestSequence
            ? `最新消息序号 ${latestSequence}`
            : ""}
      </p>
      <div
        className="tavern-transcript"
        ref={scrollRef}
        aria-label="酒馆对话记录"
        aria-busy={loading || loadingOlder}
      >
        {hasOlder ? (
          <button
            type="button"
            className="tavern-load-older"
            onClick={() => void loadOlder()}
            disabled={loadingOlder || olderDisabled}
          >
            {loadingOlder ? "载入中…" : "载入更早消息"}
          </button>
        ) : messages.length ? (
          <p className="tavern-history-start">已到达对话起点</p>
        ) : null}

        {loading && !messages.length ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="hourglass_top" size={24} />
            <p>正在恢复最近对话…</p>
          </div>
        ) : !room ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="forum" size={28} />
            <p>先创建或打开一个酒馆，然后开始对话。</p>
          </div>
        ) : !messages.length ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="forum" size={28} />
            <p>这里还很安静。选择角色并发送第一句话。</p>
          </div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`tavern-message ${message.authorKind}`}
              data-tavern-sequence={message.sequence}
            >
              <div className="tavern-message-meta">
                <strong>{messageAuthorLabel(message)}</strong>
                <time dateTime={message.createdAt}>
                  #{message.sequence} · {formatShortTime(message.createdAt)}
                </time>
              </div>
              <div className="tavern-message-body">
                <RichTextMessage content={message.content} />
                {message.action ? (
                  <p className="tavern-message-action">
                    动作：{message.action}
                  </p>
                ) : null}
                {message.addressedParticipantIds.length ? (
                  <p className="tavern-message-addressed">
                    回应给{" "}
                    {message.addressedParticipantIds
                      .map((id) => names.get(id) || "房间角色")
                      .join("、")}
                  </p>
                ) : null}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

export function ParticipantRoster({
  states,
  selectedIds,
  disabled,
  onToggle,
}: {
  states: ReturnType<typeof projectParticipantStates>;
  selectedIds: string[];
  disabled: boolean;
  onToggle: (personaId: string) => void;
}) {
  return (
    <section
      className="tavern-panel participant-roster"
      aria-labelledby="participant-roster-title"
    >
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Participant Roster</p>
          <h2 id="participant-roster-title">角色与目标</h2>
        </div>
        <span className="tavern-count">{selectedIds.length} 已选</span>
      </div>
      {states.length ? (
        <div className="tavern-roster-list">
          {states.map(({ participant, state }) => {
            const selected = selectedIds.includes(participant.personaId);
            const displayName = participant.displayName || "未命名角色";
            const stateLabel =
              selected && state === "idle"
                ? "本轮目标"
                : STEP_STATUS_LABELS[state];
            return (
              <label
                key={participant.personaId}
                className={`tavern-roster-item${selected ? " selected" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onToggle(participant.personaId)}
                />
                <span className="tavern-avatar" aria-hidden="true">
                  {displayName.slice(0, 1)}
                </span>
                <span className="tavern-roster-copy">
                  <strong>{displayName}</strong>
                  <small className={`state-${state}`}>{stateLabel}</small>
                </span>
              </label>
            );
          })}
        </div>
      ) : (
        <p className="tavern-empty-copy">打开房间后在这里选择本轮发言角色。</p>
      )}
      <p className="tavern-panel-footnote">
        选 1 位为单聊；选 2–4 位时，服务器按名册顺序引导讨论。
      </p>
    </section>
  );
}

export function InteractionComposer({
  storage,
  roomId,
  roomAvailable,
  roomActive,
  participants,
  selectedIds,
  latestMessage,
  recovery,
  busy,
  recoveryBusy,
  retrying,
  canCancel,
  canceling,
  onTurn,
  onCancel,
  onRetry,
}: {
  storage: TavernStoragePort;
  roomId: string;
  roomAvailable: boolean;
  roomActive: boolean;
  participants: TavernParticipant[];
  selectedIds: string[];
  latestMessage: TavernMessage | null;
  recovery: ReturnType<typeof authoritativeFacilitatedRecovery>;
  busy: boolean;
  recoveryBusy: boolean;
  retrying: boolean;
  canCancel: boolean;
  canceling: boolean;
  onTurn: (
    input:
      | { kind: "user_message"; content: string }
      | { kind: "continue"; anchorMessageId: string },
    guidance: string,
  ) => Promise<boolean>;
  onCancel: () => Promise<boolean>;
  onRetry: (run: TavernRun) => void;
}) {
  const initialDraft = storage.readTavernRoomDraft(roomId);
  const [message, setMessage] = useState(initialDraft.message);
  const [guidance, setGuidance] = useState(initialDraft.guidance);
  const [focusRequestVersion, setFocusRequestVersion] = useState(0);
  const composingRef = useRef(false);
  const suppressCompositionEnterRef = useRef(false);
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const mountedRoomIdRef = useRef(roomId);
  const handledFocusRequestRef = useRef(0);
  const namesById = useMemo(
    () =>
      new Map(
        participants.map((participant) => [
          participant.personaId,
          participant.displayName || "未命名角色",
        ]),
      ),
    [participants],
  );
  const recipientNames = [...participants]
    .sort((left, right) => left.displayOrder - right.displayOrder)
    .filter((participant) => selectedIds.includes(participant.personaId))
    .map((participant) => namesById.get(participant.personaId))
    .filter(Boolean);
  const unfinishedNames =
    recovery?.unfinishedPersonaIds.map(
      (personaId) => namesById.get(personaId) || "房间角色",
    ) ?? [];
  const showRecovery = Boolean(
    roomActive && recovery && (!canCancel || retrying),
  );
  const canRun =
    roomActive && selectedIds.length >= 1 && selectedIds.length <= 4 && !busy;

  useEffect(() => {
    const current = storage.readTavernRoomDraft(roomId);
    storage.writeTavernRoomDraft(roomId, {
      message,
      guidance,
      pendingTurn: current.pendingTurn,
    });
  }, [guidance, message, roomId, storage]);

  useEffect(() => {
    mountedRoomIdRef.current = roomId;
    return () => {
      mountedRoomIdRef.current = "";
    };
  }, [roomId]);

  useEffect(() => {
    if (
      focusRequestVersion === 0 ||
      handledFocusRequestRef.current >= focusRequestVersion
    )
      return;
    if (busy) return;
    if (!roomActive || message || guidance) {
      handledFocusRequestRef.current = focusRequestVersion;
      return;
    }
    const expectedRoomId = roomId;
    const frame = window.requestAnimationFrame(() => {
      if (
        mountedRoomIdRef.current !== expectedRoomId ||
        handledFocusRequestRef.current >= focusRequestVersion
      )
        return;
      handledFocusRequestRef.current = focusRequestVersion;
      const input = messageInputRef.current;
      if (!input || !input.isConnected || input.disabled) return;
      input.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [busy, focusRequestVersion, guidance, message, roomActive, roomId]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || !canRun) return;
    const completed = await onTurn(
      { kind: "user_message", content },
      guidance.trim(),
    );
    if (completed) {
      setMessage("");
      setGuidance("");
      setFocusRequestVersion((current) => current + 1);
    }
  };

  const continueConversation = async () => {
    if (!latestMessage || !canRun) return;
    const completed = await onTurn(
      { kind: "continue", anchorMessageId: latestMessage.id },
      guidance.trim(),
    );
    if (completed) setGuidance("");
  };

  const cancelConversation = async () => {
    if (!canCancel || canceling) return;
    if (await onCancel()) {
      setMessage("");
      setGuidance("");
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (
      composingRef.current ||
      event.nativeEvent.isComposing ||
      event.nativeEvent.keyCode === 229 ||
      suppressCompositionEnterRef.current
    ) {
      suppressCompositionEnterRef.current = false;
      return;
    }
    event.preventDefault();
    void sendMessage();
  };

  return (
    <section
      className="tavern-panel interaction-composer"
      aria-labelledby="interaction-composer-title"
    >
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Interaction Composer</p>
          <h2 id="interaction-composer-title">发起互动</h2>
        </div>
      </div>
      <p className="tavern-recipient-preview">
        {recipientNames.length
          ? `本轮回应：${recipientNames.join(" → ")}`
          : "请先选择至少一位角色"}
      </p>
      {showRecovery && recovery ? (
        <div
          className="tavern-recovery-callout"
          role="status"
          aria-live="polite"
        >
          <div>
            <strong>
              {recovery.chainStatus === "recovered"
                ? "上次未完成的多人互动已由重试恢复"
                : "上次多人互动还有角色未回应"}
            </strong>
            {recovery.chainStatus === "recovered" ? (
              <p>
                {recovery.completedCount}/{recovery.totalCount}{" "}
                {TAVERN_COPY.recovered}
              </p>
            ) : (
              <p>
                {recovery.completedCount}/{recovery.totalCount} 位已回应；
                {unfinishedNames.join("、")}{" "}
                尚未完成。已保存的回应不会重复生成。
              </p>
            )}
          </div>
          {recovery.chainStatus === "recoverable" ? (
            <button
              type="button"
              className="tavern-button secondary full"
              onClick={() => onRetry(recovery.run)}
              disabled={recoveryBusy || !roomActive}
            >
              {retrying ? "正在重试未完成角色…" : "仅重试未完成角色"}
            </button>
          ) : null}
        </div>
      ) : null}
      <label className="tavern-composer-label">
        <span>你的消息</span>
        <textarea
          ref={messageInputRef}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => {
            composingRef.current = true;
            suppressCompositionEnterRef.current = false;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
            suppressCompositionEnterRef.current = true;
            window.setTimeout(() => {
              suppressCompositionEnterRef.current = false;
            }, 0);
          }}
          disabled={!roomActive || busy}
          maxLength={4000}
          rows={4}
          placeholder={
            roomActive
              ? "输入消息。Enter 发送，Shift + Enter 换行。"
              : roomAvailable
                ? TAVERN_COPY.archived
                : "请先创建或打开一个酒馆。"
          }
        />
      </label>
      <label className="tavern-composer-label">
        <span>下一轮引导（可选，不会显示在对话中）</span>
        <textarea
          value={guidance}
          onChange={(event) => setGuidance(event.target.value)}
          disabled={!roomActive || busy}
          maxLength={1000}
          rows={2}
          placeholder="例如：让角色互相回应，但保留各自立场。"
        />
      </label>
      <div className="tavern-composer-actions">
        <button
          type="button"
          className="tavern-button primary"
          onClick={() => void sendMessage()}
          disabled={!canRun || !message.trim()}
        >
          <MaterialIcon name="send" size={16} />
          {busy ? "生成中…" : "发送并回应"}
        </button>
        <button
          type="button"
          className="tavern-button secondary"
          onClick={() => void continueConversation()}
          disabled={!canRun || !latestMessage}
        >
          继续角色互动
        </button>
        {canCancel ? (
          <button
            type="button"
            className="tavern-button danger"
            onClick={() => void cancelConversation()}
            disabled={canceling}
          >
            <MaterialIcon name="close" size={16} />
            {canceling ? "正在取消…" : "取消接收结果"}
          </button>
        ) : null}
      </div>
      {busy ? (
        <p className="tavern-panel-footnote" role="status">
          请求已交给服务器。取消会立即拒收结果，但已发出的模型请求可能运行到超时。
        </p>
      ) : null}
    </section>
  );
}

export function ReliabilityDetails({
  runs,
  retryableRuns,
  recoveryChains,
  participants,
  roomActive,
  busy,
  onRetry,
}: {
  runs: TavernRun[];
  retryableRuns: TavernRun[];
  recoveryChains: TavernRunRecoveryChain[];
  participants: TavernParticipant[];
  roomActive: boolean;
  busy: boolean;
  onRetry: (run: TavernRun) => void;
}) {
  const retryableIds = new Set(retryableRuns.map((run) => run.id));
  const recoveredRootIds = new Set(
    recoveryChains
      .filter((chain) => chain.chainStatus === "recovered")
      .map((chain) => chain.rootRunId),
  );
  const names = new Map(
    participants.map((participant) => [
      participant.personaId,
      participant.displayName || "未命名角色",
    ]),
  );
  return (
    <details className="tavern-panel reliability-details">
      <summary>
        <span>
          <span className="tavern-kicker">Reliability Details</span>
          <strong>可靠性摘要</strong>
        </span>
        <span
          className="tavern-count"
          aria-label={`${retryableRuns.length} 个待恢复项`}
        >
          待恢复 {retryableRuns.length}
        </span>
      </summary>
      <div className="tavern-reliability-content">
        <p className="tavern-panel-footnote">
          这里只显示可读恢复摘要；完整 Harness trace 可在全局调试层查看。
        </p>
        {runs.length ? (
          runs.slice(0, 12).map((run) => {
            const repairCount = [
              ...run.harnessTrace,
              ...run.speakerSteps.flatMap((step) =>
                step.harnessTrace ? [step.harnessTrace] : [],
              ),
            ].filter((trace) => trace.status === "repaired").length;
            return (
              <div className="tavern-run-summary" key={run.id}>
                <div className="tavern-run-title-row">
                  <strong>{RUN_STATUS_LABELS[run.status]}</strong>
                  <span>
                    {run.mode === "direct" ? "单角色" : "多人引导"} ·{" "}
                    {formatShortTime(run.createdAt)}
                  </span>
                </div>
                <ul>
                  {run.speakerSteps.map((step) => (
                    <li key={`${run.id}-${step.stepIndex}`}>
                      <span>{names.get(step.personaId) || "房间角色"}</span>
                      <span>
                        {step.status === "blocked"
                          ? TAVERN_COPY.blocked
                          : STEP_STATUS_LABELS[step.status]}
                      </span>
                    </li>
                  ))}
                </ul>
                {repairCount ? (
                  <p className="tavern-repair-note">
                    本轮有 {repairCount} 项输出经校验后自动修正。
                  </p>
                ) : null}
                {retryableIds.has(run.id) ? (
                  <button
                    type="button"
                    className="tavern-button secondary full"
                    onClick={() => onRetry(run)}
                    disabled={!roomActive || busy}
                  >
                    仅重试未完成角色
                  </button>
                ) : recoveredRootIds.has(run.id) ? (
                  <p className="tavern-repair-note">
                    该部分结果已由后续范围重试完整恢复。
                  </p>
                ) : run.parentRunId ? (
                  <p className="tavern-repair-note">{TAVERN_COPY.retryScope}</p>
                ) : null}
              </div>
            );
          })
        ) : (
          <p className="tavern-empty-copy">
            发起互动后，这里会显示每位角色的生成与恢复结果。
          </p>
        )}
      </div>
    </details>
  );
}

function messageAuthorLabel(message: TavernMessage): string {
  if (message.authorKind === "persona")
    return message.personaName || "房间角色";
  if (message.authorKind === "user") return "你";
  if (message.authorKind === "director") return "导演引导";
  return "系统";
}

function formatShortTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
