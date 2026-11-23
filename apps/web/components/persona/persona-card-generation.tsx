import { MaterialIcon } from "../ui/material-icon";
import { collectReferenceHintsFromCards } from "../../lib/persona-editor-model";
import { PersonaSidebarSection } from "./persona-sidebar-section";
import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import styles from "./persona-workspace.module.css";

export function PersonaCardGeneration({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    draft,
    updatePersonaAssistInput,
    generatedCards,
    selectedGeneratedCardIds,
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
    toggleGeneratedCardSelection,
    rejectGeneratedCard,
    insertCardsIntoDraft,
    handleGenerateCards,
    collapsedSidebarSections,
    toggleSidebarSection,
  } = controller;
  const selectedGeneratedCards = generatedCards.filter((card) =>
    selectedGeneratedCardIds.includes(card.id),
  );
  const generatedReferenceHints =
    collectReferenceHintsFromCards(selectedGeneratedCards);
  const existingReferenceHints = draft.referenceHints;
  const referenceAdded = generatedReferenceHints.filter(
    (item) => !existingReferenceHints.includes(item),
  );
  const referenceRetained = generatedReferenceHints.filter((item) =>
    existingReferenceHints.includes(item),
  );
  const referenceRemoved = clearBeforeBackfill
    ? existingReferenceHints.filter((item) => !generatedReferenceHints.includes(item))
    : [];
  return (
    <PersonaSidebarSection
      title="生成卡片"
      expanded={!collapsedSidebarSections.includes("generate")}
      onToggle={() => toggleSidebarSection("generate")}
    >
      <label className="grid gap-1">
        <span className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
          精确卡片数量（可选）
        </span>
        <input
          className={styles.textField}
          type="number"
          min={1}
          max={24}
          step={1}
          value={cardGenerateCount}
          onChange={(e) =>
            updatePersonaAssistInput(() => setCardGenerateCount(e.target.value))
          }
          placeholder="留空由模型决定，填写后精确生成 1–24 张"
        />
      </label>
      <div className="flex flex-nowrap items-center justify-between gap-2">
        <div className={styles.modeSwitch}>
          <button
            type="button"
            className={styles.modeSwitchButton}
            data-active={cardGenerationMode === "keywords"}
            onClick={() =>
              updatePersonaAssistInput(() => setCardGenerationMode("keywords"))
            }
          >
            关键词搜索
          </button>
          <button
            type="button"
            className={styles.modeSwitchButton}
            data-active={cardGenerationMode === "long_text"}
            onClick={() =>
              updatePersonaAssistInput(() => setCardGenerationMode("long_text"))
            }
          >
            长文本提取
          </button>
        </div>
        <button
          className={styles.sidebarIconButton}
          type="button"
          disabled={cardActionPending !== null}
          onClick={() => void handleGenerateCards(cardGenerationMode)}
          title={
            cardGenerationMode === "keywords"
              ? cardActionPending === "generate_keywords"
                ? "生成中"
                : "根据关键词生成人格卡片"
              : cardActionPending === "generate_long_text"
                ? "提取中"
                : "根据长文本提取人格卡片"
          }
          aria-label={
            cardGenerationMode === "keywords"
              ? cardActionPending === "generate_keywords"
                ? "生成中"
                : "根据关键词生成人格卡片"
              : cardActionPending === "generate_long_text"
                ? "提取中"
                : "根据长文本提取人格卡片"
          }
        >
          <MaterialIcon
            name={
              cardGenerationMode === "keywords"
                ? cardActionPending === "generate_keywords"
                  ? "hourglass_top"
                  : "auto_awesome"
                : cardActionPending === "generate_long_text"
                  ? "hourglass_top"
                  : "description"
            }
            size={14}
          />
        </button>
      </div>
      {cardGenerationMode === "keywords" ? (
        <label key="keywords-mode" className="grid gap-1">
          <input
            className={styles.textField}
            aria-label="卡片生成关键词"
            value={cardKeywordInput}
            onChange={(e) =>
              updatePersonaAssistInput(() => setCardKeywordInput(e.target.value))
            }
            placeholder="例如：冷静学术、学院派导师、侦探式推理"
          />
        </label>
      ) : (
        <label key="long-text-mode" className="grid gap-1">
          <input
            type="file"
            aria-label="长文本文件"
            accept=".txt,.md,text/plain,text/markdown"
            className={styles.fileInput}
            onChange={(event) =>
              updatePersonaAssistInput(() =>
                setCardLongTextFile(event.target.files?.[0] ?? null),
              )
            }
          />
          {cardLongTextFile ? (
            <span className="text-[12px] text-muted">{cardLongTextFile.name}</span>
          ) : null}
        </label>
      )}
      {cardError ? (
        <p className="m-0 text-[12px] leading-[1.5] text-negative">{cardError}</p>
      ) : null}
      {cardMessage ? (
        <p role="status" className="m-0 text-[12px] leading-[1.6] text-muted">
          {cardMessage}
        </p>
      ) : null}
      {generatedCards.length ||
      generatedPersonaMeta.summary ||
      generatedPersonaMeta.relationship ||
      generatedPersonaMeta.learnerAddress ? (
        <div className={styles.generatedResultCard}>
          <strong className="text-[13px] text-ink">
            {generatedPersonaMeta.summary || "本轮生成人格草案"}
          </strong>
          <p className="m-0 text-[11px] leading-[1.4] text-muted">
            {generatedCards.length} 张卡片
            {generatedPersonaMeta.relationship
              ? ` · ${generatedPersonaMeta.relationship}`
              : ""}
            {generatedPersonaMeta.learnerAddress
              ? ` · 称呼：${generatedPersonaMeta.learnerAddress}`
              : ""}
          </p>
          {generatedCards.length ? (
            <ul className="m-0 grid max-h-[180px] gap-1.5 overflow-y-auto pt-1 pl-[18px]">
              {generatedCards.map((card) => (
                <li
                  key={card.id}
                  className="grid gap-0.5 text-[11px] leading-[1.45] text-muted"
                >
                  <label className="flex items-center gap-2 text-[12px] leading-[1.4] text-ink">
                    <input
                      type="checkbox"
                      checked={selectedGeneratedCardIds.includes(card.id)}
                      onChange={() => toggleGeneratedCardSelection(card.id)}
                      aria-label={`选择${card.title}`}
                    />
                    <span>纳入批量应用</span>
                  </label>
                  <strong>{card.title}</strong>
                  <span>
                    {card.label}：{card.content}
                  </span>
                  <button
                    type="button"
                    className={styles.ghostBtn}
                    onClick={() => insertCardsIntoDraft([card])}
                  >
                    仅合并这张卡片
                  </button>
                  <button
                    type="button"
                    className={styles.ghostBtn}
                    onClick={() => rejectGeneratedCard(card.id)}
                  >
                    拒绝这张卡片
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="proposal-diff">
            {!draft.name.trim() ? (
              <p role="note">名称尚未填写：应用后请填写名称再保存。</p>
            ) : null}
            {(
              [
                ["摘要", draft.summary, generatedPersonaMeta.summary],
                ["关系", draft.relationship, generatedPersonaMeta.relationship],
                ["称呼", draft.learnerAddress, generatedPersonaMeta.learnerAddress],
              ] as const
            ).map(([label, before, proposed]) => (
              <p key={label}>
                <strong>{label}</strong>
                <br />
                <del>{before || "空"}</del> →{" "}
                <ins>
                  {proposed || (clearBeforeBackfill ? "将清空" : before || "保持为空")}
                </ins>
              </p>
            ))}
            <p>
              批量应用：已选择 {selectedGeneratedCardIds.length}/{generatedCards.length}{" "}
              张卡片。插槽：
              {clearBeforeBackfill
                ? `删除现有 ${draft.slots.length} 个，再插入已选卡片`
                : "保留现有插槽，合并已选卡片（自动去重）"}
              。
            </p>
            <details>
              <summary>查看完整参考提示 diff</summary>
              <p>
                新增：
                {referenceAdded.length ? referenceAdded.join("、") : "无"}
              </p>
              <p>
                保留：
                {referenceRetained.length ? referenceRetained.join("、") : "无"}
              </p>
              {clearBeforeBackfill ? (
                <p>
                  清空：
                  {referenceRemoved.length ? referenceRemoved.join("、") : "无"}
                </p>
              ) : null}
            </details>
          </div>
          <details className="secondary-actions">
            <summary>替换选项（会清空当前内容）</summary>
            <label className="flex items-center gap-2 text-[12px] leading-[1.4] text-ink">
              <input
                type="checkbox"
                checked={clearBeforeBackfill}
                onChange={(event) => setClearBeforeBackfill(event.target.checked)}
              />
              <span className="text-muted">
                应用前清空摘要、关系、称呼、参考提示和全部插槽
              </span>
            </label>
          </details>
          <div className="flex flex-wrap items-center justify-end gap-1">
            <button
              className={styles.sidebarIconButton}
              type="button"
              disabled={
                !(
                  generatedCards.length ||
                  generatedPersonaMeta.summary ||
                  generatedPersonaMeta.relationship ||
                  generatedPersonaMeta.learnerAddress
                )
              }
              onClick={async (event) => {
                const applied = await applyGeneratedCardsToDraft(event.currentTarget);
                if (applied && !draft.name.trim())
                  document.getElementById("persona-draft-name")?.focus();
              }}
              title="应用到当前编辑区"
              aria-label="应用到当前编辑区"
            >
              <MaterialIcon name="input" size={14} />
            </button>
          </div>
        </div>
      ) : null}
    </PersonaSidebarSection>
  );
}
