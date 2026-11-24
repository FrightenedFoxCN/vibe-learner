"use client";

import {
  PERSONA_SLOT_KIND_LABELS,
  type PersonaCard,
  type PersonaProfile,
  type PersonaSlotKind,
} from "@vibe-learner/shared";
import { MaterialIcon, type MaterialIconName } from "../ui/material-icon";

import styles from "./persona-workspace.module.css";

export function PersonaCardView({
  card,
  dragging,
  deletePending,
  onDragStart,
  onDragEnd,
  onInsert,
  onDelete,
}: {
  card: PersonaCard;
  dragging: boolean;
  deletePending: boolean;
  onDragStart: (id: string) => void;
  onDragEnd: () => void;
  onInsert: (card: PersonaCard) => void;
  onDelete: (id: string, trigger: HTMLElement) => void;
}) {
  return (
    <article
      key={card.id}
      className={styles.personaSlotLibraryCard}
      data-dragging={dragging}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-2">
          <button
            data-card-action="true"
            type="button"
            className="inline-flex size-[30px] flex-none cursor-grab items-center justify-center border border-border bg-panel text-ink"
            title="拖拽插入到左侧人格插槽"
            aria-label="拖拽插入到左侧人格插槽"
            draggable
            onDragStart={() => onDragStart(card.id)}
            onDragEnd={onDragEnd}
          >
            <MaterialIcon name="drag_indicator" size={16} />
          </button>
          <span className="min-w-0 text-[13px] font-bold text-ink">{card.title}</span>
        </div>
        <span className="p-0 text-[11px] text-muted">卡片</span>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[11px] text-muted">
        <span>
          {PERSONA_SLOT_KIND_LABELS[card.kind as PersonaSlotKind] ?? card.label}
        </span>
        {card.tags.length ? <span>{card.tags.join(" · ")}</span> : null}
      </div>
      <p className="m-0 text-[13px] leading-[1.7] text-ink">{card.content}</p>
      <div className="flex items-center justify-end gap-1">
        <button
          data-card-action="true"
          className={styles.sidebarIconButton}
          type="button"
          onClick={() => onInsert(card)}
          title="插入当前人格"
          aria-label="插入当前人格"
        >
          <MaterialIcon name="input" size={16} />
        </button>
        <details className="secondary-actions">
          <summary>删除操作</summary>
          <button
            data-card-action="true"
            className={styles.sidebarIconButton}
            type="button"
            disabled={deletePending}
            onClick={(event) => void onDelete(card.id, event.currentTarget)}
            title={deletePending ? "删除中" : "删除"}
            aria-label={deletePending ? "删除中" : "删除"}
          >
            <MaterialIcon name={deletePending ? "hourglass_top" : "delete"} size={16} />
          </button>
        </details>
      </div>
    </article>
  );
}

export function PersonaProfileCard({
  persona,
  isSelected,
  deletePending,
  onActivate,
  onDelete,
}: {
  persona: PersonaProfile;
  isSelected: boolean;
  deletePending: boolean;
  onActivate: (persona: PersonaProfile) => void;
  onDelete: (persona: PersonaProfile) => void;
}) {
  return (
    <article
      key={persona.id}
      className={styles.personaLibraryCard}
      data-selected={isSelected}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-2">
          <span className="min-w-0 text-[13px] font-bold text-ink">{persona.name}</span>
        </div>
        <span className="p-0 text-[11px] text-muted">
          {persona.source === "builtin" ? "内置人格" : "用户人格"}
        </span>
      </div>
      <p className="m-0 text-[13px] leading-[1.7] text-ink">
        {persona.summary || "未填写摘要"}
      </p>
      <div className="flex flex-wrap gap-1.5 text-[11px] text-muted">
        <span>{persona.relationship || "未填写关系"}</span>
        <span>称呼：{persona.learnerAddress || "未填写"}</span>
        <span>{persona.slots.length} 个插槽</span>
      </div>
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          className={styles.sidebarIconButton}
          data-primary={isSelected}
          disabled={deletePending}
          onClick={() => onActivate(persona)}
          title={isSelected ? "编辑中" : "载入"}
          aria-label={isSelected ? "编辑中" : "载入"}
        >
          <MaterialIcon name={isSelected ? "check_circle" : "file_open"} size={16} />
        </button>
        {persona.source === "user" ? (
          <details className="secondary-actions">
            <summary>删除操作</summary>
            <button
              type="button"
              className={styles.sidebarIconButton}
              disabled={deletePending}
              onClick={() => void onDelete(persona)}
              title={deletePending ? "删除中" : "删除"}
              aria-label={deletePending ? "删除中" : "删除"}
            >
              <MaterialIcon
                name={deletePending ? "hourglass_top" : "delete"}
                size={16}
              />
            </button>
          </details>
        ) : null}
      </div>
    </article>
  );
}

export function IconGlyphButton({
  icon,
  label,
  onClick,
}: {
  icon: MaterialIconName;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.iconBtn}
      title={label}
      aria-label={label}
      onClick={onClick}
    >
      <MaterialIcon name={icon} size={15} />
    </button>
  );
}
