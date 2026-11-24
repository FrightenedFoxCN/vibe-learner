import { Fragment, useRef } from "react";
import {
  PERSONA_SLOT_KIND_LABELS,
  PERSONA_SLOT_KINDS,
  type PersonaSlotKind,
} from "@vibe-learner/shared";
import { MaterialIcon } from "../ui/material-icon";
import { IconGlyphButton } from "./persona-library-cards";
import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import styles from "./persona-workspace.module.css";

export function PersonaSlotsPane({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    draft,
    assistPending,
    slotAssistIndex,
    handleAssistSlot,
    draggingPersonaCardId,
    slotInsertIndex,
    draggingSlotId,
    expandedSlotId,
    setExpandedSlotId,
    movePulse,
    runtimePromptPreview,
    handleAddSlot,
    handleClearSlots,
    handleUpdateSlot,
    handleRemoveSlot,
    handleMoveSlot,
    handleSortSlotsByPriority,
    handleDragStart,
    handleSlotInsertDragOver,
    handleSlotCardDragOver,
    handleSlotCardDrop,
    handleSlotInsertDrop,
    handleDragEnd,
  } = controller;
  const addSlotRef = useRef<HTMLButtonElement>(null);

  function removeSlot(slotId: string, trigger: HTMLElement) {
    const card = trigger.closest<HTMLElement>("[data-persona-slot]");
    if (card?.contains(document.activeElement)) {
      const cards = Array.from(
        card.parentElement?.querySelectorAll("[data-persona-slot]") ?? [],
      );
      const index = cards.indexOf(card);
      const adjacent = cards[index + 1] ?? cards[index - 1];
      (
        adjacent?.querySelector<HTMLElement>("[data-persona-slot-toggle]") ??
        addSlotRef.current
      )?.focus({ preventScroll: true });
    }
    handleRemoveSlot(slotId);
  }

  return (
    <div className={styles.slotsPane}>
      <div className={styles.panelHeader}>
        <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
          人格插槽
        </span>
        <div className="inline-flex flex-wrap items-center gap-2">
          <details className={styles.batchMenu}>
            <summary className={styles.batchSummary}>批量操作</summary>
            <div className={styles.batchPopover}>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={handleSortSlotsByPriority}
              >
                按优先级整理
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={(event) => void handleClearSlots(event.currentTarget)}
                disabled={!draft.slots.length}
              >
                清空全部插槽
              </button>
            </div>
          </details>
          <button
            type="button"
            className={styles.ghostBtn}
            ref={addSlotRef}
            onClick={() => handleAddSlot("custom")}
          >
            添加
          </button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-[18px] pt-4 pb-[18px]">
        <div className="mx-auto grid w-full max-w-[760px] min-w-0">
          <div
            className={styles.slotDropArea}
            data-active={slotInsertIndex !== null || draggingSlotId !== null}
          >
            <div className="grid">
              <div
                className={styles.slotInsertMarker}
                data-active={slotInsertIndex === 0}
                onDragOver={(event) => {
                  if (!draggingPersonaCardId && draggingSlotId === null) return;
                  event.preventDefault();
                  handleSlotInsertDragOver(0);
                }}
                onDrop={(event) => {
                  if (!draggingPersonaCardId && draggingSlotId === null) return;
                  event.preventDefault();
                  handleSlotInsertDrop(0);
                }}
              />
              {draft.slots.length ? (
                draft.slots.map((slot, index) => (
                  <Fragment key={slot.draftSlotId}>
                    <div
                      className={styles.slotCard}
                      data-persona-slot
                      data-dragging={draggingSlotId === slot.draftSlotId}
                      data-move={
                        movePulse?.slotId === slot.draftSlotId
                          ? movePulse.direction === -1
                            ? "up"
                            : "down"
                          : undefined
                      }
                      onDragOver={(event) => handleSlotCardDragOver(event, index)}
                      onDrop={(event) => handleSlotCardDrop(event, index)}
                    >
                      <div
                        className="grid min-w-0 cursor-pointer gap-1"
                        onClick={() =>
                          setExpandedSlotId((prev) =>
                            prev === slot.draftSlotId ? null : slot.draftSlotId,
                          )
                        }
                      >
                        <div className="grid min-w-0 grid-cols-[18px_minmax(110px,132px)_minmax(0,1fr)_auto] items-center gap-1.5">
                          <span
                            className="inline-flex cursor-grab items-center justify-center p-0 text-muted select-none"
                            title="拖动排序"
                            aria-label="拖动排序"
                            draggable
                            onDragStart={(e) => {
                              e.stopPropagation();
                              handleDragStart(slot.draftSlotId, index);
                            }}
                            onDragEnd={handleDragEnd}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MaterialIcon name="drag_indicator" size={16} />
                          </span>
                          <select
                            className={styles.slotKindSelect}
                            aria-label={`插槽 ${index + 1} 类型`}
                            value={slot.kind}
                            onChange={(e) =>
                              handleUpdateSlot(slot.draftSlotId, "kind", e.target.value)
                            }
                            disabled={Boolean(slot.locked)}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {!PERSONA_SLOT_KINDS.some((kind) => kind === slot.kind) ? (
                              <option value={slot.kind}>
                                {slot.label || slot.kind}（自定义）
                              </option>
                            ) : null}
                            {PERSONA_SLOT_KINDS.map((k) => (
                              <option key={k} value={k}>
                                {PERSONA_SLOT_KIND_LABELS[k]}
                              </option>
                            ))}
                          </select>
                          <input
                            className={styles.slotLabelInput}
                            aria-label={`插槽 ${index + 1} 标签`}
                            value={slot.label}
                            placeholder="显示标签"
                            onChange={(e) =>
                              handleUpdateSlot(
                                slot.draftSlotId,
                                "label",
                                e.target.value,
                              )
                            }
                            disabled={Boolean(slot.locked)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <div className="inline-flex shrink-0 items-center gap-0.5">
                            <button
                              type="button"
                              className="inline-flex size-6 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent p-0 text-muted"
                              aria-label={`${expandedSlotId === slot.draftSlotId ? "收起" : "展开"}插槽 ${slot.label || index + 1}`}
                              aria-expanded={expandedSlotId === slot.draftSlotId}
                              data-persona-slot-toggle
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedSlotId((prev) =>
                                  prev === slot.draftSlotId ? null : slot.draftSlotId,
                                );
                              }}
                            >
                              <MaterialIcon
                                name={
                                  expandedSlotId === slot.draftSlotId
                                    ? "expand_more"
                                    : "chevron_right"
                                }
                                size={16}
                              />
                            </button>
                            <button
                              type="button"
                              className="flex size-6 flex-none cursor-pointer items-center justify-center border-none bg-transparent text-muted"
                              aria-label={`删除插槽 ${slot.label || index + 1}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                removeSlot(slot.draftSlotId, e.currentTarget);
                              }}
                            >
                              <MaterialIcon name="close" size={16} />
                            </button>
                          </div>
                        </div>
                        {expandedSlotId !== slot.draftSlotId ? (
                          <span className="block max-w-[56ch] min-w-0 truncate pl-6 text-[11px] text-muted">
                            {slot.content.slice(0, 56) || "—"}
                          </span>
                        ) : null}
                      </div>
                      {expandedSlotId === slot.draftSlotId ? (
                        <>
                          <textarea
                            className={styles.slotContent}
                            aria-label={`插槽 ${index + 1} 内容`}
                            value={slot.content}
                            placeholder={`请填写"${PERSONA_SLOT_KIND_LABELS[slot.kind as PersonaSlotKind] ?? slot.kind}"的具体内容。`}
                            onChange={(e) =>
                              handleUpdateSlot(
                                slot.draftSlotId,
                                "content",
                                e.target.value,
                              )
                            }
                            disabled={Boolean(slot.locked)}
                          />
                          <div className="grid grid-cols-[auto_1fr] items-center gap-1.5">
                            <span className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
                              权重 {slot.weight ?? 50}
                            </span>
                            <input
                              className="w-full"
                              type="range"
                              aria-label={`插槽 ${index + 1} 权重`}
                              min={0}
                              max={100}
                              step={1}
                              value={slot.weight ?? 50}
                              onChange={(e) =>
                                handleUpdateSlot(
                                  slot.draftSlotId,
                                  "weight",
                                  Number(e.target.value),
                                )
                              }
                              disabled={Boolean(slot.locked)}
                            />
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <IconGlyphButton
                              icon="arrow_upward"
                              label="上移"
                              onClick={() => handleMoveSlot(slot.draftSlotId, -1)}
                            />
                            <IconGlyphButton
                              icon="arrow_downward"
                              label="下移"
                              onClick={() => handleMoveSlot(slot.draftSlotId, 1)}
                            />
                            <button
                              type="button"
                              className={styles.iconBtn}
                              title={slot.locked ? "解锁" : "锁定"}
                              aria-label={slot.locked ? "解锁" : "锁定"}
                              onClick={() =>
                                handleUpdateSlot(
                                  slot.draftSlotId,
                                  "locked",
                                  !slot.locked,
                                )
                              }
                            >
                              <MaterialIcon
                                name={slot.locked ? "lock_open" : "lock"}
                                size={15}
                              />
                            </button>
                            <button
                              type="button"
                              className={styles.iconBtn}
                              title="AI 重写"
                              aria-label="AI 重写"
                              onClick={() => void handleAssistSlot(slot.draftSlotId)}
                              disabled={
                                assistPending ||
                                slotAssistIndex === index ||
                                Boolean(slot.locked)
                              }
                            >
                              <MaterialIcon
                                name={
                                  slotAssistIndex === index
                                    ? "hourglass_top"
                                    : "auto_awesome"
                                }
                                size={15}
                              />
                            </button>
                          </div>
                        </>
                      ) : null}
                    </div>
                    <div
                      className={styles.slotInsertMarker}
                      data-active={slotInsertIndex === index + 1}
                      onDragOver={(event) => {
                        if (!draggingPersonaCardId && draggingSlotId === null) return;
                        event.preventDefault();
                        handleSlotInsertDragOver(index + 1);
                      }}
                      onDrop={(event) => {
                        if (!draggingPersonaCardId && draggingSlotId === null) return;
                        event.preventDefault();
                        handleSlotInsertDrop(index + 1);
                      }}
                    />
                  </Fragment>
                ))
              ) : (
                <div
                  className={styles.emptySlotDropTarget}
                  data-active={slotInsertIndex === 0}
                  onDragOver={(event) => {
                    if (!draggingPersonaCardId) return;
                    event.preventDefault();
                    handleSlotInsertDragOver(0);
                  }}
                  onDrop={(event) => {
                    if (!draggingPersonaCardId) return;
                    event.preventDefault();
                    handleSlotInsertDrop(0);
                  }}
                >
                  拖到这里插入第一张人格卡片
                </div>
              )}
            </div>
          </div>
        </div>

        <div className={styles.basicPaneSection}>
          <div className="grid gap-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
                运行时人格提示词预览
              </label>
            </div>
            <pre className="m-0 min-h-24 max-h-[156px] overflow-auto border border-border bg-bg px-3 py-2.5 text-[12px] leading-[1.6] whitespace-pre-wrap text-ink">
              {runtimePromptPreview}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
