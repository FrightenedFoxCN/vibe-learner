"use client";

import { PERSONA_SLOT_KIND_LABELS, type PersonaCard, type PersonaProfile, type PersonaSlotKind } from "@vibe-learner/shared";
import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";

import { styles } from "./persona-workspace-styles";

export function PersonaCardView({ card, dragging, deletePending, onDragStart, onDragEnd, onInsert, onDelete }: {
  card: PersonaCard; dragging: boolean; deletePending: boolean;
  onDragStart: (id: string) => void; onDragEnd: () => void;
  onInsert: (card: PersonaCard) => void; onDelete: (id: string) => void;
}) {
    return (
      <article
        key={card.id}
        style={{
          ...styles.personaSlotLibraryCard,
          ...(dragging ? styles.personaSlotLibraryCardDragging : null),
        }}
      >
        <div style={styles.libraryCardHeader}>
          <div style={styles.libraryCardTitleRow}>
            <button
              data-card-action="true"
              type="button"
              style={styles.libraryCardDragHandle}
              title="拖拽插入到左侧人格插槽"
              aria-label="拖拽插入到左侧人格插槽"
              draggable
              onDragStart={() => onDragStart(card.id)}
              onDragEnd={onDragEnd}
            >
              <MaterialIcon name="drag_indicator" size={16} />
            </button>
            <span style={styles.libraryCardTitle}>{card.title}</span>
          </div>
          <span style={styles.libraryCardBadge}>卡片</span>
        </div>
        <div style={styles.libraryCardMetaRow}>
          <span>{PERSONA_SLOT_KIND_LABELS[card.kind as PersonaSlotKind] ?? card.label}</span>
          {card.tags.length ? <span>{card.tags.join(" · ")}</span> : null}
        </div>
        <p style={styles.libraryCardContent}>{card.content}</p>
        <div style={styles.sidebarCardActions}>
          <button
            data-card-action="true"
            style={styles.sidebarIconButton}
            type="button"
            onClick={() => onInsert(card)}
            title="插入当前人格"
            aria-label="插入当前人格"
          >
            <MaterialIcon name="input" size={16} />
          </button>
          <button
            data-card-action="true"
            style={styles.sidebarIconButton}
            type="button"
            disabled={deletePending}
            onClick={() => void onDelete(card.id)}
            title={deletePending ? "删除中" : "删除"}
            aria-label={deletePending ? "删除中" : "删除"}
          >
            <MaterialIcon name={deletePending ? "hourglass_top" : "delete"} size={16} />
          </button>
        </div>
      </article>
    );
  }

export function PersonaProfileCard({ persona, isSelected, deletePending, onActivate, onDelete }: {
  persona: PersonaProfile; isSelected: boolean; deletePending: boolean;
  onActivate: (persona: PersonaProfile) => void; onDelete: (persona: PersonaProfile) => void;
}) {
    return (
      <article
        key={persona.id}
        style={{
          ...styles.personaLibraryCard,
          ...(isSelected ? styles.personaLibraryCardSelected : null),
        }}
      >
        <div style={styles.libraryCardHeader}>
          <div style={styles.libraryCardTitleRow}>
            <span style={styles.libraryCardTitle}>{persona.name}</span>
          </div>
          <span style={styles.libraryCardBadge}>
            {persona.source === "builtin" ? "内置人格" : "用户人格"}
          </span>
        </div>
        <p style={styles.libraryCardContent}>{persona.summary || "未填写摘要"}</p>
        <div style={styles.libraryCardMetaRow}>
          <span>{persona.relationship || "未填写关系"}</span>
          <span>称呼：{persona.learnerAddress || "未填写"}</span>
          <span>{persona.slots.length} 个插槽</span>
        </div>
        <div style={styles.sidebarCardActions}>
          <button
            type="button"
            style={isSelected ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
            onClick={() => onActivate(persona)}
            title={isSelected ? "编辑中" : "载入"}
            aria-label={isSelected ? "编辑中" : "载入"}
          >
            <MaterialIcon name={isSelected ? "check_circle" : "file_open"} size={16} />
          </button>
          {persona.source === "user" ? (
            <button
              type="button"
              style={styles.sidebarIconButton}
              disabled={deletePending}
              onClick={() => void onDelete(persona)}
              title={deletePending ? "删除中" : "删除"}
              aria-label={deletePending ? "删除中" : "删除"}
            >
              <MaterialIcon name={deletePending ? "hourglass_top" : "delete"} size={16} />
            </button>
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
    <button type="button" style={styles.iconBtn} title={label} aria-label={label} onClick={onClick}>
      <MaterialIcon name={icon} size={15} />
    </button>
  );
}
