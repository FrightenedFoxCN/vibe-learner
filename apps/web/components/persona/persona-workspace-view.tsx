"use client";

import { Fragment } from "react";
import { PERSONA_SLOT_KIND_LABELS, PERSONA_SLOT_KINDS, type PersonaCard, type PersonaProfile, type PersonaSlotKind } from "@vibe-learner/shared";
import { TopNav } from "../../components/top-nav";
import { MaterialIcon } from "../../components/material-icon";
import { ModelFallbackNotice } from "../../components/model-fallback-notice";
import { ProviderTruth } from "../../components/provider-truth";

import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import { PersonaCardView, PersonaProfileCard, IconGlyphButton } from "./persona-library-cards";
import { styles, BASIC_PANE_WIDTH, SIDEBAR_PANE_WIDTH } from "./persona-workspace-styles";

const SLOT_KIND_HINTS: Record<string, string> = {
  worldview: "描述人格对学习、知识、成长的基本信念，会长期影响讲解立场。",
  past_experiences: "描述关键经历与背景，解释“为什么这个人格会这样教学”。",
  thinking_style: "描述推理与验证方式，例如是否先讲前提、是否强调反例。",
  teaching_method: "描述课堂推进方法，例如拆解步骤、提问节奏、练习设计。",
  narrative_mode: "描述叙事密度，建议直接使用“稳态导学”或“轻剧情陪伴”等中文表达。",
  encouragement_style: "描述鼓励策略，应当具体可执行，避免泛泛鼓励。",
  correction_style: "描述纠错方式，建议先指出可改进点，再给下一步动作。",
  custom: "自定义插槽，用于补充特殊设定。"
};

export function PersonaWorkspaceView({ controller }: { controller: PersonaWorkspaceController }) {
  const {
    activateLibraryPersona,
    configImportInputRef,
    personas,
    selectedPersonaId,
    draft,
    activatePersonaDraft,
    updatePersonaAssistInput,
    assistPending,
    slotAssistIndex,
    assistError,
    assistModelRecoveries,
    retainRatio,
    setRetainRatio,
    systemPromptSuggestion,
    systemPromptSuggestionSource,
    applySystemPromptSuggestion,
    dismissSystemPromptSuggestion,
    handleAssistSlot,
    handleAssistSetting,
    configMessage,
    configError,
    generatedCards,
    cardGenerationMode,
    setCardGenerationMode,
    cardKeywordInput,
    setCardKeywordInput,
    cardLongTextFile,
    setCardLongTextFile,
    cardGenerateCount,
    setCardGenerateCount,
    clearBeforeBackfill,
    setClearBeforeBackfill,
    cardActionPending,
    cardMessage,
    cardError,
    generatedPersonaMeta,
    applyGeneratedCardsToDraft,
    insertCardsIntoDraft,
    handleGenerateCards,
    cardSearchQuery,
    setCardSearchQuery,
    cardDeletePendingId,
    draggingPersonaCardId,
    slotInsertIndex,
    draggingSlotIndex,
    expandedSlotIndex,
    setExpandedSlotIndex,
    movePulse,
    isCompactLayout,
    isRewritePopoverOpen,
    setIsRewritePopoverOpen,
    isSystemPromptExpanded,
    setIsSystemPromptExpanded,
    collapsedSidebarSections,
    personaLibraryQuery,
    setPersonaLibraryQuery,
    savingPersona,
    saveError,
    loadError,
    personaDeletePendingId,
    personaLibraryMessage,
    personaLibraryError,
    handleCreatePersona,
    handleUpdatePersona,
    handleReloadSelectedPersona,
    handleDeletePersona,
    rewritePopoverRef,
    selectedPersona,
    isReadonlyPersona,
    filteredPersonaCards,
    builtinPersonas,
    userPersonas,
    runtimePromptPreview,
    pageNotice,
    updateDraft,
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
    handleNewPersonaDraft,
    handleDuplicatePersonaDraft,
    handleExportConfig,
    handleDownloadTemplate,
    handleImportConfig,
    handlePersonaCardDragStart,
    handlePersonaCardDragEnd,
    toggleSidebarSection,
    handleDeletePersonaCard,
  } = controller;
  const renderPersonaCard = (card: PersonaCard) => <PersonaCardView
    key={card.id} card={card} dragging={draggingPersonaCardId === card.id}
    deletePending={cardDeletePendingId === card.id} onDragStart={handlePersonaCardDragStart}
    onDragEnd={handlePersonaCardDragEnd} onInsert={card => insertCardsIntoDraft([card])} onDelete={handleDeletePersonaCard}
  />;
  const renderPersonaLibraryCard = (persona: PersonaProfile) => <PersonaProfileCard
    key={persona.id} persona={persona} isSelected={persona.id === selectedPersonaId}
    deletePending={personaDeletePendingId === persona.id} onActivate={activateLibraryPersona} onDelete={handleDeletePersona}
  />;
return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/persona-spectrum" />

      <div style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 style={styles.pageTitle}>人格色谱</h1>
          <ProviderTruth scope="persona" />
          <div style={styles.notice}>{pageNotice}</div>
        </div>
      </div>

      {loadError ? <div role="alert" style={styles.errorBanner}>加载失败: {loadError}</div> : null}

      <div
        style={{
          ...styles.workspaceShell,
          ...(isCompactLayout ? styles.workspaceShellCompact : {}),
        }}
      >
        <div
          style={{
            ...styles.mainColumn,
            ...(isCompactLayout ? styles.mainColumnCompact : {}),
          }}
        >
          <div
            style={{
              ...styles.editorArea,
              ...(isCompactLayout ? styles.editorAreaCompact : {}),
            }}
          >
            <div
              style={{
                ...styles.basicPane,
                ...(isCompactLayout ? styles.compactPane : {}),
                width: isCompactLayout ? "100%" : BASIC_PANE_WIDTH,
                flexShrink: 0,
              }}
            >
              <div style={styles.basicPaneHead}>
                <span style={styles.basicPaneTitle}>基本设定</span>
                <div style={styles.basicPaneActions}>
                  <div ref={rewritePopoverRef} style={styles.rewritePopoverWrap}>
                    <button
                      type="button"
                      style={{ ...styles.basicIconButton, ...(assistPending ? styles.basicIconButtonDisabled : {}) }}
                      disabled={assistPending}
                      onClick={() => setIsRewritePopoverOpen((current) => !current)}
                      title={assistPending ? "AI 重写中" : "AI 重写"}
                      aria-label={assistPending ? "AI 重写中" : "AI 重写"}
                    >
                      <MaterialIcon name={assistPending ? "hourglass_top" : "auto_awesome"} size={16} />
                    </button>
                    {isRewritePopoverOpen ? (
                      <div style={styles.rewritePopover}>
                        <div style={styles.rewritePopoverSection}>
                          <span style={styles.panelTitle}>保留原文比例</span>
                          <span style={styles.rewritePopoverValue}>{(retainRatio * 100).toFixed(0)}%</span>
                        </div>
                        <input
                          style={styles.range}
                          type="range"
                          min={0}
                          max={1}
                          step={0.05}
                          value={retainRatio}
                          onChange={(e) => updatePersonaAssistInput(() => setRetainRatio(Number(e.target.value)))}
                        />
                        <p style={styles.rewritePopoverHint}>数值越高，AI 重写时越接近原始设定。</p>
                        <button
                          type="button"
                          style={styles.rewritePopoverButton}
                          onClick={() => { void handleAssistSetting(); }}
                        >
                          开始重写
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...styles.basicIconButtonPrimary, ...(savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={savingPersona}
                    onClick={handleNewPersonaDraft}
                    title={savingPersona ? "保存中" : "新建人格草稿"}
                    aria-label={savingPersona ? "保存中" : "新建人格草稿"}
                  >
                    <MaterialIcon name="add_circle" size={18} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(!selectedPersona || savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={!selectedPersona || savingPersona}
                    onClick={handleDuplicatePersonaDraft}
                    title={savingPersona ? "保存中" : "复制为新人格"}
                    aria-label={savingPersona ? "保存中" : "复制为新人格"}
                  >
                    <MaterialIcon name="library_add" size={16} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(!selectedPersona || savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={!selectedPersona || savingPersona}
                    onClick={() => { void handleReloadSelectedPersona(); }}
                    title={savingPersona ? "保存中" : "重新载入人格"}
                    aria-label={savingPersona ? "保存中" : "重新载入人格"}
                  >
                    <MaterialIcon name="refresh" size={16} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(savingPersona || isReadonlyPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={savingPersona || isReadonlyPersona}
                    onClick={() => void (selectedPersonaId ? handleUpdatePersona() : handleCreatePersona())}
                    title={savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"}
                    aria-label={savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"}
                  >
                    <MaterialIcon name="save" size={16} />
                  </button>
                </div>
              </div>
              <section style={styles.basicPaneCard}>
                <div style={styles.basicPanePrimarySection}>
                <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>人格</label>
                <select
                  style={styles.select}
                  value={selectedPersonaId}
                  onChange={(event) => {
                    void activatePersonaDraft(event.target.value);
                  }}
                >
                  <option value="">新建人格（未保存）</option>
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}（{p.source === "builtin" ? "内置" : "用户"}）</option>
                  ))}
                </select>
              </div>

              <div style={styles.fieldGroup}>
                <label htmlFor="persona-draft-name" style={styles.fieldLabel}>名称</label>
                <input id="persona-draft-name" style={styles.input} value={draft.name} onChange={(e) => updateDraft("name", e.target.value)} />
              </div>

              <div style={styles.summaryFieldGroup}>
                <label style={styles.fieldLabel}>摘要</label>
                <textarea style={styles.summaryTextarea} value={draft.summary} onChange={(e) => updateDraft("summary", e.target.value)} />
              </div>

              <div style={styles.compactGrid}>
                <div style={styles.fieldGroup}>
                  <label style={styles.fieldLabel}>关系</label>
                  <input
                    style={styles.input}
                    value={draft.relationship}
                    onChange={(e) => updateDraft("relationship", e.target.value)}
                    placeholder="例如：师生、学伴、导师"
                  />
                </div>
                <div style={styles.fieldGroup}>
                  <label style={styles.fieldLabel}>学习者称呼</label>
                  <input
                    style={styles.input}
                    value={draft.learnerAddress}
                    onChange={(e) => updateDraft("learnerAddress", e.target.value)}
                    placeholder="例如：同学、伙伴、学员"
                  />
                </div>
              </div>

              <ModelFallbackNotice recoveries={assistModelRecoveries} />
        {assistError ? <span role="alert" style={styles.errorInline}>{assistError}</span> : null}
                </div>

              <div style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.fieldGroup}>
                  <button
                    type="button"
                    style={styles.collapsibleFieldToggle}
                    onClick={() => setIsSystemPromptExpanded((current) => !current)}
                  >
                    <span style={styles.fieldLabel}>附加系统约束（可选）</span>
                    <span style={styles.sidebarToggleIcon}>
                      <MaterialIcon name={isSystemPromptExpanded ? "expand_more" : "chevron_right"} size={16} />
                    </span>
                  </button>
                  {isSystemPromptExpanded ? (
                    <>
                      <textarea
                        style={styles.textareaLg}
                        value={draft.systemPrompt}
                        onChange={(e) => updateDraft("systemPrompt", e.target.value)}
                        placeholder="例如：始终优先引用教材原话；避免过度角色扮演；默认先给步骤再给总结。"
                      />
                      {systemPromptSuggestion ? (
                        <div style={styles.promptSuggestionCard}>
                          <div style={styles.promptSuggestionHeader}>
                            <span style={styles.panelTitle}>AI 建议</span>
                            <span style={styles.promptSuggestionSource}>{systemPromptSuggestionSource || "AI 生成"}</span>
                          </div>
                          <p style={styles.promptSuggestionNote}>
                            这只会写入上面的附加约束。
                          </p>
                          <p style={styles.promptSuggestionBody}>{systemPromptSuggestion}</p>
                          <div style={styles.actionsRow}>
                            <button type="button" style={styles.primaryBtn} onClick={applySystemPromptSuggestion}>
                              应用建议
                            </button>
                            <button type="button" style={styles.ghostBtn} onClick={dismissSystemPromptSuggestion}>
                              忽略建议
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </div>

              <section style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.actionsRow}>
                  <button style={styles.ghostBtn} type="button" onClick={handleDownloadTemplate}>下载模板</button>
                  <button style={styles.ghostBtn} type="button" onClick={handleExportConfig}>导出配置</button>
                  <button type="button" style={styles.ghostBtn} onClick={() => configImportInputRef.current?.click()}>导入配置</button>
                  <input ref={configImportInputRef} type="file" accept="application/json,.json" style={styles.hiddenInput} onChange={handleImportConfig} />
                </div>
                {saveError ? <span role="alert" style={styles.errorInline}>{saveError}</span> : null}
                {isReadonlyPersona ? (
                  <span style={styles.mutedText}>内置人格只读；点击复制按钮可保留当前设定并另存为新人格。</span>
                ) : null}
                {configMessage ? <span role="status" style={styles.mutedText}>{configMessage}</span> : null}
                {configError ? <span role="alert" style={styles.errorInline}>{configError}</span> : null}
              </section>
              </section>
            </div>
            <div
              style={{
                ...styles.slotsPane,
                ...(isCompactLayout ? styles.compactPane : {}),
              }}
            >
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>人格插槽</span>
                <div style={styles.panelHeaderActions}>
                  <button type="button" style={styles.ghostBtn} onClick={handleClearSlots} disabled={!draft.slots.length}>清空</button>
                  <button type="button" style={styles.ghostBtn} onClick={() => handleAddSlot("custom")}>添加</button>
                  <button type="button" style={styles.ghostBtn} onClick={handleSortSlotsByPriority}>按优先级整理</button>
                </div>
              </div>
              <div style={styles.panelBody}>
              <div style={styles.slotPaneContent}>
              <div
                style={{
                  ...styles.slotDropArea,
                  ...((slotInsertIndex !== null || draggingSlotIndex !== null) ? styles.slotDropZoneActive : null),
                }}
              >
                <div style={styles.slotList}>
                  <div
                    style={{
                      ...styles.slotInsertMarker,
                      ...(slotInsertIndex === 0 ? styles.slotInsertMarkerActive : null),
                    }}
                    onDragOver={(event) => {
                      if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                      event.preventDefault();
                      handleSlotInsertDragOver(0);
                    }}
                    onDrop={(event) => {
                      if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                      event.preventDefault();
                      handleSlotInsertDrop(0);
                    }}
                  />
                  {draft.slots.length ? draft.slots.map((slot, index) => (
                    <Fragment key={`${slot.kind}:${slot.label}:${index}`}>
                      <div
                        style={{
                          ...styles.slotCard,
                          ...(draggingSlotIndex === index ? styles.slotCardDragging : null),
                          ...(movePulse?.index === index
                            ? movePulse.direction === -1
                              ? styles.slotCardMoveUp
                              : styles.slotCardMoveDown
                            : null),
                        }}
                        onDragOver={(event) => handleSlotCardDragOver(event, index)}
                        onDrop={(event) => handleSlotCardDrop(event, index)}
                      >
                        <div
                          style={styles.slotHeader}
                          onClick={() => setExpandedSlotIndex((prev) => (prev === index ? null : index))}
                        >
                          <div style={styles.slotHeaderMain}>
                            <span
                              style={styles.dragHandle}
                              title="拖动排序"
                                aria-label="拖动排序"
                              draggable
                              onDragStart={(e) => { e.stopPropagation(); handleDragStart(index); }}
                              onDragEnd={handleDragEnd}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MaterialIcon name="drag_indicator" size={16} />
                            </span>
                            <select
                              style={styles.slotKindSelect}
                              value={slot.kind}
                              onChange={(e) => handleUpdateSlot(index, "kind", e.target.value)}
                              disabled={Boolean(slot.locked)}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {!PERSONA_SLOT_KINDS.some((kind) => kind === slot.kind) ? (
                                <option value={slot.kind}>{slot.label || slot.kind}（自定义）</option>
                              ) : null}
                              {PERSONA_SLOT_KINDS.map((k) => (
                                <option key={k} value={k}>{PERSONA_SLOT_KIND_LABELS[k]}</option>
                              ))}
                            </select>
                            <input
                              style={styles.slotLabelInput}
                              value={slot.label}
                              placeholder="显示标签"
                              onChange={(e) => handleUpdateSlot(index, "label", e.target.value)}
                              disabled={Boolean(slot.locked)}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <div style={styles.slotHeaderActions}>
                              <button
                                type="button"
                                style={styles.slotToggleBtn}
                                onClick={(e) => { e.stopPropagation(); setExpandedSlotIndex((prev) => (prev === index ? null : index)); }}
                              >
                                <MaterialIcon name={expandedSlotIndex === index ? "expand_more" : "chevron_right"} size={16} />
                              </button>
                              <button
                                type="button"
                                style={styles.removeBtn}
                                onClick={(e) => { e.stopPropagation(); handleRemoveSlot(index); }}
                              ><MaterialIcon name="close" size={16} /></button>
                            </div>
                          </div>
                          {expandedSlotIndex !== index ? (
                            <span style={styles.slotPreview}>{slot.content.slice(0, 56) || "—"}</span>
                          ) : null}
                        </div>
                        {expandedSlotIndex === index ? (
                          <>
                            <textarea
                              style={styles.slotContent}
                              value={slot.content}
                              placeholder={`请填写"${PERSONA_SLOT_KIND_LABELS[slot.kind as PersonaSlotKind] ?? slot.kind}"的具体内容。`}
                              onChange={(e) => handleUpdateSlot(index, "content", e.target.value)}
                              disabled={Boolean(slot.locked)}
                            />
                            <div style={styles.weightRow}>
                              <span style={styles.fieldLabel}>权重 {slot.weight ?? 50}</span>
                              <input
                                style={styles.range}
                                type="range"
                                min={0}
                                max={100}
                                step={1}
                                value={slot.weight ?? 50}
                                onChange={(e) => handleUpdateSlot(index, "weight", Number(e.target.value))}
                                disabled={Boolean(slot.locked)}
                              />
                            </div>
                            <div style={styles.actionsRow}>
                              <IconGlyphButton icon="arrow_upward" label="上移" onClick={() => handleMoveSlot(index, -1)} />
                              <IconGlyphButton icon="arrow_downward" label="下移" onClick={() => handleMoveSlot(index, 1)} />
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title={slot.locked ? "解锁" : "锁定"}
                                aria-label={slot.locked ? "解锁" : "锁定"}
                                onClick={() => handleUpdateSlot(index, "locked", !slot.locked)}
                              >
                                <MaterialIcon name={slot.locked ? "lock_open" : "lock"} size={15} />
                              </button>
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title="AI 重写"
                                aria-label="AI 重写"
                                onClick={() => void handleAssistSlot(index)}
                                disabled={assistPending || slotAssistIndex === index || Boolean(slot.locked)}
                              >
                                <MaterialIcon name={slotAssistIndex === index ? "hourglass_top" : "auto_awesome"} size={15} />
                              </button>
                            </div>
                          </>
                        ) : null}
                      </div>
                      <div
                        style={{
                          ...styles.slotInsertMarker,
                          ...(slotInsertIndex === index + 1 ? styles.slotInsertMarkerActive : null),
                        }}
                        onDragOver={(event) => {
                          if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                          event.preventDefault();
                          handleSlotInsertDragOver(index + 1);
                        }}
                        onDrop={(event) => {
                          if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                          event.preventDefault();
                          handleSlotInsertDrop(index + 1);
                        }}
                      />
                    </Fragment>
                  )) : (
                    <div
                      style={{
                        ...styles.emptySlotDropTarget,
                        ...(slotInsertIndex === 0 ? styles.emptySlotDropTargetActive : null),
                      }}
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

              <div style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.fieldGroup}>
                  <div style={styles.fieldHeaderRow}>
                    <label style={styles.fieldLabel}>运行时人格提示词预览</label>
                  </div>
                  <pre style={styles.runtimePromptPreview}>{runtimePromptPreview}</pre>
                </div>
              </div>
              </div>{/* panelBody */}
            </div>
          </div>
        </div>
        <aside
          style={{
            ...styles.sidebarPane,
            ...(isCompactLayout ? styles.sidebarPaneCompact : {}),
            width: isCompactLayout ? "100%" : SIDEBAR_PANE_WIDTH,
            flexShrink: 0,
          }}
        >
          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("generate")}>
              <span style={styles.panelTitle}>生成卡片</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("generate") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("generate") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>精确卡片数量（可选）</span>
                  <input
                    style={styles.input}
                    type="number"
                    min={1}
                    max={24}
                    step={1}
                    value={cardGenerateCount}
                    onChange={(e) => updatePersonaAssistInput(() => setCardGenerateCount(e.target.value))}
                    placeholder="留空由模型决定，填写后精确生成 1–24 张"
                  />
                </label>
                <label style={styles.checkboxRow}>
                  <input
                    type="checkbox"
                    checked={clearBeforeBackfill}
                    onChange={(event) => setClearBeforeBackfill(event.target.checked)}
                  />
                  <span style={styles.checkboxLabel}>应用前清空摘要、关系、称呼、参考提示和全部插槽</span>
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={cardGenerationMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updatePersonaAssistInput(() => setCardGenerationMode("keywords"))}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={cardGenerationMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updatePersonaAssistInput(() => setCardGenerationMode("long_text"))}
                    >
                      长文本提取
                    </button>
                  </div>
                  <button
                    style={styles.sidebarIconButton}
                    type="button"
                    disabled={cardActionPending !== null}
                    onClick={() => void handleGenerateCards(cardGenerationMode)}
                    title={
                      cardGenerationMode === "keywords"
                        ? (cardActionPending === "generate_keywords" ? "生成中" : "根据关键词生成人格卡片")
                        : (cardActionPending === "generate_long_text" ? "提取中" : "根据长文本提取人格卡片")
                    }
                    aria-label={
                      cardGenerationMode === "keywords"
                        ? (cardActionPending === "generate_keywords" ? "生成中" : "根据关键词生成人格卡片")
                        : (cardActionPending === "generate_long_text" ? "提取中" : "根据长文本提取人格卡片")
                    }
                  >
                    <MaterialIcon
                      name={
                        cardGenerationMode === "keywords"
                          ? (cardActionPending === "generate_keywords" ? "hourglass_top" : "auto_awesome")
                          : (cardActionPending === "generate_long_text" ? "hourglass_top" : "description")
                      }
                      size={14}
                    />
                  </button>
                </div>
                {cardGenerationMode === "keywords" ? (
                  <label key="keywords-mode" style={styles.fieldGroup}>
                    <input
                      style={styles.input}
                      value={cardKeywordInput}
                      onChange={(e) => updatePersonaAssistInput(() => setCardKeywordInput(e.target.value))}
                      placeholder="例如：冷静学术、学院派导师、侦探式推理"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => updatePersonaAssistInput(() => setCardLongTextFile(event.target.files?.[0] ?? null))}
                    />
                    {cardLongTextFile ? <span style={styles.mutedText}>{cardLongTextFile.name}</span> : null}
                  </label>
                )}
                {cardError ? <p role="alert" style={styles.errorText}>{cardError}</p> : null}
                {cardMessage ? <p role="status" style={styles.sidebarHint}>{cardMessage}</p> : null}
                {(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress) ? (
                  <div style={styles.generatedResultCard}>
                    <strong style={styles.generatedResultTitle}>{generatedPersonaMeta.summary || "本轮生成人格草案"}</strong>
                    <p style={styles.generatedResultMeta}>
                      {generatedCards.length} 张卡片
                      {generatedPersonaMeta.relationship ? ` · ${generatedPersonaMeta.relationship}` : ""}
                      {generatedPersonaMeta.learnerAddress ? ` · 称呼：${generatedPersonaMeta.learnerAddress}` : ""}
                    </p>
                    {generatedCards.length ? (
                      <ul style={styles.generatedCardPreviewList}>
                        {generatedCards.map((card) => (
                          <li key={card.id} style={styles.generatedCardPreviewItem}>
                            <strong>{card.title}</strong>
                            <span>{card.label}：{card.content}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <div style={styles.sidebarActionRow}>
                      <button
                        style={styles.sidebarIconButton}
                        type="button"
                        disabled={!(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress)}
                        onClick={applyGeneratedCardsToDraft}
                        title="应用到当前编辑区"
                        aria-label="应用到当前编辑区"
                      >
                        <MaterialIcon name="input" size={14} />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("results")}>
              <span style={styles.panelTitle}>卡片库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("results") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("results") ? (
              <div style={styles.sidebarSectionBody}>
                <input
                  style={styles.input}
                  value={cardSearchQuery}
                  onChange={(e) => setCardSearchQuery(e.target.value)}
                  placeholder="搜索标题、内容、标签、关键词"
                />
                {filteredPersonaCards.length ? (
                  <div style={styles.cardList}>
                    {filteredPersonaCards.map((card) => renderPersonaCard(card))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("persona-library")}>
              <span style={styles.panelTitle}>人格库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("persona-library") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("persona-library") ? (
              <div style={styles.sidebarSectionBody}>
                <input
                  style={styles.input}
                  value={personaLibraryQuery}
                  onChange={(e) => setPersonaLibraryQuery(e.target.value)}
                  placeholder="搜索人格名称、摘要、关系或称呼"
                />
                {personaLibraryMessage ? <p role="status" style={styles.sidebarHint}>{personaLibraryMessage}</p> : null}
                {personaLibraryError ? <p role="alert" style={styles.errorText}>{personaLibraryError}</p> : null}

                {builtinPersonas.length ? (
                  <div style={styles.cardList}>
                    {builtinPersonas.map(renderPersonaLibraryCard)}
                  </div>
                ) : null}

                {userPersonas.length ? (
                  <div style={styles.cardList}>
                    {userPersonas.map(renderPersonaLibraryCard)}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

        </aside>
      </div>
    </main>
  );
}
