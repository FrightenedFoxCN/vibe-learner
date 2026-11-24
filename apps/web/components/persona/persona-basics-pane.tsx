import { MaterialIcon } from "../ui/material-icon";
import { ModelFallbackNotice } from "../ui/model-fallback-notice";
import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import styles from "./persona-workspace.module.css";

export function PersonaBasicsPane({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    requestImportConfig,
    configImportInputRef,
    personas,
    personaDeletePendingId,
    selectedPersonaId,
    draft,
    activatePersonaDraft,
    assistError,
    assistModelRecoveries,
    systemPromptSuggestion,
    systemPromptSuggestionSource,
    applySystemPromptSuggestion,
    dismissSystemPromptSuggestion,
    configMessage,
    configError,
    isSystemPromptExpanded,
    setIsSystemPromptExpanded,
    saveError,
    isReadonlyPersona,
    updateDraft,
    handleDuplicatePersonaDraft,
    handleExportConfig,
    handleDownloadTemplate,
    handleImportConfig,
  } = controller;

  return (
    <div className={styles.basicPane}>
      <PersonaBasicsToolbar controller={controller} />
      {isReadonlyPersona ? (
        <div className={styles.readonlyBanner} role="status">
          <span>内置人格只读，不可直接覆盖保存。</span>
          <button
            type="button"
            className={styles.ghostBtn}
            onClick={handleDuplicatePersonaDraft}
          >
            复制为新人格
          </button>
        </div>
      ) : null}
      <section className="flex min-h-0 flex-1 flex-col pt-3">
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="grid gap-1">
            <label
              htmlFor="persona-select"
              className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase"
            >
              人格
            </label>
            <select
              className={styles.textField}
              id="persona-select"
              value={selectedPersonaId}
              onChange={(event) => {
                void activatePersonaDraft(
                  event.currentTarget.value,
                  undefined,
                  event.currentTarget,
                );
              }}
            >
              <option value="">新建人格（未保存）</option>
              {personas.map((p) => (
                <option
                  key={p.id}
                  value={p.id}
                  disabled={personaDeletePendingId === p.id}
                >
                  {p.name}（{p.source === "builtin" ? "内置" : "用户"}）
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-1">
            <label
              htmlFor="persona-draft-name"
              className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase"
            >
              名称
            </label>
            <input
              id="persona-draft-name"
              className={styles.textField}
              value={draft.name}
              onChange={(e) => updateDraft("name", e.target.value)}
            />
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-1">
            <label className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
              摘要
            </label>
            <textarea
              aria-label="摘要"
              className={styles.summaryTextarea}
              value={draft.summary}
              onChange={(e) => updateDraft("summary", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-2.5">
            <div className="grid gap-1">
              <label className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
                关系
              </label>
              <input
                className={styles.textField}
                aria-label="关系"
                value={draft.relationship}
                onChange={(e) => updateDraft("relationship", e.target.value)}
                placeholder="例如：师生、学伴、导师"
              />
            </div>
            <div className="grid gap-1">
              <label className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
                学习者称呼
              </label>
              <input
                className={styles.textField}
                aria-label="学习者称呼"
                value={draft.learnerAddress}
                onChange={(e) => updateDraft("learnerAddress", e.target.value)}
                placeholder="例如：同学、伙伴、学员"
              />
            </div>
          </div>

          <ModelFallbackNotice recoveries={assistModelRecoveries} />
          {assistError ? (
            <span className="text-[12px] text-negative">{assistError}</span>
          ) : null}
        </div>

        <div className={styles.basicPaneSection}>
          <div className="grid gap-1">
            <button
              type="button"
              className="flex w-full cursor-pointer items-center justify-between border-none bg-transparent p-0 text-left"
              aria-expanded={isSystemPromptExpanded}
              onClick={() => setIsSystemPromptExpanded((current) => !current)}
            >
              <span className="text-[11px] font-semibold tracking-[0.04em] text-muted uppercase">
                附加系统约束（可选）
              </span>
              <span className="inline-flex items-center text-muted">
                <MaterialIcon
                  name={isSystemPromptExpanded ? "expand_more" : "chevron_right"}
                  size={16}
                />
              </span>
            </button>
            {isSystemPromptExpanded ? (
              <>
                <textarea
                  className={styles.systemPromptField}
                  aria-label="附加系统约束"
                  value={draft.systemPrompt}
                  onChange={(e) => updateDraft("systemPrompt", e.target.value)}
                  placeholder="例如：始终优先引用教材原话；避免过度角色扮演；默认先给步骤再给总结。"
                />
                {systemPromptSuggestion ? (
                  <div className={styles.promptSuggestionCard}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
                        AI 建议
                      </span>
                      <span className="text-[12px] text-muted">
                        {systemPromptSuggestionSource || "AI 生成"}
                      </span>
                    </div>
                    <p className="m-0 text-[12px] leading-[1.5] text-muted">
                      这只会写入上面的附加约束。
                    </p>
                    <p className="m-0 text-[14px] leading-[1.65] whitespace-pre-wrap text-ink">
                      {systemPromptSuggestion}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className={styles.primaryBtn}
                        onClick={applySystemPromptSuggestion}
                      >
                        应用建议
                      </button>
                      <button
                        type="button"
                        className={styles.ghostBtn}
                        onClick={dismissSystemPromptSuggestion}
                      >
                        忽略建议
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        </div>

        <section className={styles.basicPaneSection}>
          <div className="flex flex-wrap items-center gap-2">
            <button
              className={styles.ghostBtn}
              type="button"
              onClick={handleDownloadTemplate}
            >
              下载模板
            </button>
            <button
              className={styles.ghostBtn}
              type="button"
              onClick={handleExportConfig}
            >
              导出配置
            </button>
            <button
              type="button"
              className={styles.ghostBtn}
              onClick={(event) => requestImportConfig(event.currentTarget)}
            >
              导入配置
            </button>
            <input
              ref={configImportInputRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleImportConfig}
            />
          </div>
          {saveError ? (
            <span className="text-[12px] text-negative">{saveError}</span>
          ) : null}

          {configMessage ? (
            <span role="status" className="text-[12px] text-muted">
              {configMessage}
            </span>
          ) : null}
          {configError ? (
            <span className="text-[12px] text-negative">{configError}</span>
          ) : null}
        </section>
      </section>
    </div>
  );
}

function PersonaBasicsToolbar({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const {
    selectedPersonaId,
    updatePersonaAssistInput,
    assistPending,
    retainRatio,
    setRetainRatio,
    handleAssistSetting,
    isRewritePopoverOpen,
    setIsRewritePopoverOpen,
    savingPersona,
    personaDeletePendingId,
    handleCreatePersona,
    handleUpdatePersona,
    handleReloadSelectedPersona,
    rewritePopoverRef,
    selectedPersona,
    isReadonlyPersona,
    handleNewPersonaDraft,
    handleDuplicatePersonaDraft,
  } = controller;
  const deletingSelected =
    Boolean(selectedPersonaId) && selectedPersonaId === personaDeletePendingId;

  return (
    <div className="relative flex min-h-6 flex-wrap items-center justify-between gap-3 pr-1 pb-2.5">
      <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
        基本设定
      </span>
      <div className="flex flex-wrap gap-2">
        <div ref={rewritePopoverRef} className="static inline-flex">
          <button
            type="button"
            className={styles.basicActionButton}
            disabled={assistPending}
            onClick={() => setIsRewritePopoverOpen((current) => !current)}
            title={assistPending ? "AI 重写中" : "AI 重写"}
            aria-label={assistPending ? "AI 重写中" : "AI 重写"}
          >
            <MaterialIcon
              name={assistPending ? "hourglass_top" : "auto_awesome"}
              size={15}
            />
            <span>重写</span>
          </button>
          {isRewritePopoverOpen ? (
            <div className={styles.rewritePopover}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
                  保留原文比例
                </span>
                <span className="text-[12px] font-semibold text-ink">
                  {(retainRatio * 100).toFixed(0)}%
                </span>
              </div>
              <input
                className="w-full"
                type="range"
                aria-label="保留原文比例"
                min={0}
                max={1}
                step={0.05}
                value={retainRatio}
                onChange={(e) =>
                  updatePersonaAssistInput(() => setRetainRatio(Number(e.target.value)))
                }
              />
              <p className="m-0 text-[12px] leading-[1.5] text-muted">
                数值越高，AI 重写时越接近原始设定。
              </p>
              <button
                type="button"
                className="inline-flex cursor-pointer items-center justify-center border-none bg-accent px-3 py-0 text-[12px] font-semibold text-white"
                onClick={() => {
                  void handleAssistSetting();
                }}
              >
                开始重写
              </button>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          className={styles.basicActionButton}
          disabled={savingPersona}
          onClick={(event) => void handleNewPersonaDraft(event.currentTarget)}
          title={savingPersona ? "保存中" : "新建人格草稿"}
          aria-label={savingPersona ? "保存中" : "新建人格草稿"}
        >
          <MaterialIcon name="add_circle" size={15} />
          <span>新建</span>
        </button>
        <button
          type="button"
          className={styles.basicActionButton}
          disabled={!selectedPersona || savingPersona}
          onClick={handleDuplicatePersonaDraft}
          title={savingPersona ? "保存中" : "复制为新人格"}
          aria-label={savingPersona ? "保存中" : "复制为新人格"}
        >
          <MaterialIcon name="library_add" size={15} />
          <span>复制</span>
        </button>
        <button
          type="button"
          className={styles.basicActionButton}
          disabled={!selectedPersona || savingPersona || deletingSelected}
          onClick={(event) => void handleReloadSelectedPersona(event.currentTarget)}
          title={savingPersona ? "保存中" : "重新载入人格"}
          aria-label={savingPersona ? "保存中" : "重新载入人格"}
        >
          <MaterialIcon name="refresh" size={15} />
          <span>重载</span>
        </button>
        <button
          type="button"
          className={styles.basicActionButton}
          data-primary="true"
          disabled={savingPersona || isReadonlyPersona || deletingSelected}
          onClick={() =>
            void (selectedPersonaId ? handleUpdatePersona() : handleCreatePersona())
          }
          title={savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"}
          aria-label={
            savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"
          }
        >
          <MaterialIcon name="save" size={15} />
          <span>{selectedPersonaId ? "保存" : "创建"}</span>
        </button>
      </div>
    </div>
  );
}
