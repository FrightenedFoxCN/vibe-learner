import { useState } from "react";
import {
  PERSONA_SLOT_KIND_LABELS,
  PERSONA_SLOT_KINDS,
  type PersonaCard,
  type PersonaProfile,
} from "@vibe-learner/shared";
import { PersonaCardView, PersonaProfileCard } from "./persona-library-cards";
import { PersonaSidebarSection } from "./persona-sidebar-section";
import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import styles from "./persona-workspace.module.css";

export function PersonaCardLibrary({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    insertCardsIntoDraft,
    cardSearchQuery,
    setCardSearchQuery,
    cardDeletePendingId,
    draggingPersonaCardId,
    collapsedSidebarSections,
    filteredPersonaCards,
    handlePersonaCardDragStart,
    handlePersonaCardDragEnd,
    toggleSidebarSection,
    handleDeletePersonaCard,
  } = controller;
  const [cardKind, setCardKind] = useState("");
  const visibleCards = filteredPersonaCards.filter(
    (card) => !cardKind || card.kind === cardKind,
  );
  const renderPersonaCard = (card: PersonaCard) => (
    <PersonaCardView
      key={card.id}
      card={card}
      dragging={draggingPersonaCardId === card.id}
      deletePending={cardDeletePendingId === card.id}
      onDragStart={handlePersonaCardDragStart}
      onDragEnd={handlePersonaCardDragEnd}
      onInsert={(card) => insertCardsIntoDraft([card])}
      onDelete={handleDeletePersonaCard}
    />
  );
  return (
    <PersonaSidebarSection
      title="卡片库"
      expanded={!collapsedSidebarSections.includes("results")}
      onToggle={() => toggleSidebarSection("results")}
    >
      <input
        className={styles.textField}
        aria-label="搜索卡片库"
        value={cardSearchQuery}
        onChange={(e) => setCardSearchQuery(e.target.value)}
        placeholder="搜索标题、内容、标签、关键词"
      />
      <select
        className="library-filter"
        aria-label="筛选卡片类型"
        value={cardKind}
        onChange={(event) => setCardKind(event.target.value)}
      >
        <option value="">全部类型</option>
        {PERSONA_SLOT_KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {PERSONA_SLOT_KIND_LABELS[kind]}
          </option>
        ))}
      </select>
      <p role="status" className="m-0 text-[12px] leading-[1.6] text-muted">
        {visibleCards.length} 张卡片
      </p>
      {visibleCards.length ? (
        <div className="grid gap-1.5">
          {visibleCards.map((card) => renderPersonaCard(card))}
        </div>
      ) : (
        <p className="m-0 text-[12px] leading-[1.6] text-muted">
          没有匹配的卡片，请调整搜索或筛选。
        </p>
      )}
    </PersonaSidebarSection>
  );
}

export function PersonaProfileLibrary({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    activateLibraryPersona,
    selectedPersonaId,
    collapsedSidebarSections,
    personaLibraryQuery,
    setPersonaLibraryQuery,
    personaDeletePendingId,
    personaLibraryMessage,
    personaLibraryError,
    handleDeletePersona,
    builtinPersonas,
    userPersonas,
    toggleSidebarSection,
  } = controller;
  const [personaSource, setPersonaSource] = useState("");
  const visibleBuiltin = personaSource === "user" ? [] : builtinPersonas;
  const visibleUser = personaSource === "builtin" ? [] : userPersonas;
  const renderPersonaLibraryCard = (persona: PersonaProfile) => (
    <PersonaProfileCard
      key={persona.id}
      persona={persona}
      isSelected={persona.id === selectedPersonaId}
      deletePending={personaDeletePendingId === persona.id}
      onActivate={activateLibraryPersona}
      onDelete={handleDeletePersona}
    />
  );
  return (
    <PersonaSidebarSection
      title="人格库"
      expanded={!collapsedSidebarSections.includes("persona-library")}
      onToggle={() => toggleSidebarSection("persona-library")}
    >
      <input
        className={styles.textField}
        aria-label="搜索人格库"
        value={personaLibraryQuery}
        onChange={(e) => setPersonaLibraryQuery(e.target.value)}
        placeholder="搜索人格名称、摘要、关系或称呼"
      />
      <select
        className="library-filter"
        aria-label="筛选人格来源"
        value={personaSource}
        onChange={(event) => setPersonaSource(event.target.value)}
      >
        <option value="">全部来源</option>
        <option value="builtin">内置人格</option>
        <option value="user">用户人格</option>
      </select>
      <p role="status" className="m-0 text-[12px] leading-[1.6] text-muted">
        {visibleBuiltin.length + visibleUser.length} 个人格
      </p>
      {!visibleBuiltin.length && !visibleUser.length ? (
        <p className="m-0 text-[12px] leading-[1.6] text-muted">
          没有匹配的人格，请调整搜索或筛选。
        </p>
      ) : null}
      {personaLibraryMessage ? (
        <p role="status" className="m-0 text-[12px] leading-[1.6] text-muted">
          {personaLibraryMessage}
        </p>
      ) : null}
      {personaLibraryError ? (
        <p className="m-0 text-[12px] leading-[1.5] text-negative">
          {personaLibraryError}
        </p>
      ) : null}

      {visibleBuiltin.length ? (
        <div className="grid gap-1.5">
          {visibleBuiltin.map(renderPersonaLibraryCard)}
        </div>
      ) : null}

      {visibleUser.length ? (
        <div className="grid gap-1.5">{visibleUser.map(renderPersonaLibraryCard)}</div>
      ) : null}
    </PersonaSidebarSection>
  );
}
