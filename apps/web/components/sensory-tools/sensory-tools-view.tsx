import { useRef } from "react";

import { TopNav } from "../layout/top-nav";
import { AsyncFeedback } from "../ui/async-feedback";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { countEnabledAvailable, toolKey } from "./sensory-tools-model";
import type { useSensoryToolsController } from "./use-sensory-tools-controller";

type Controller = ReturnType<typeof useSensoryToolsController>;
type StageRow = Controller["stageRows"][number];

const filterLabel =
  "grid min-w-0 gap-1 text-xs text-muted [@media(max-width:640px)]:basis-full";
const filterInput =
  "min-h-11 min-w-11 max-w-full border border-solid border-border bg-bg px-2.5 py-2 text-ink";
const checkbox = "m-0 size-[18px] min-h-[18px] min-w-[18px] shrink-0 accent-accent";
const hint = "m-0 text-[13px] text-muted";

export function SensoryToolsView({ controller }: { controller: Controller }) {
  const {
    loading,
    savingKey,
    error,
    saveMessage,
    config,
    batchMode,
    visibleCount,
    stageRows,
  } = controller;
  const feedbackAction = useRef<Element | null>(null);

  return (
    <main
      onClickCapture={(event) => {
        feedbackAction.current = (event.target as Element).closest("button, input");
      }}
      className="with-app-nav mx-auto grid min-h-screen max-w-[1280px] content-start gap-5 px-8 pt-[38px] pb-14"
    >
      <TopNav currentPath="/sensory-tools" />
      <header>
        <h1 className="m-0 text-[28px] leading-[1.2] font-extrabold tracking-[-0.02em] text-ink">
          感官工具
        </h1>
      </header>
      <AsyncFeedback
        actionRef={feedbackAction}
        pending={Boolean(savingKey)}
        error={error ? `配置操作失败：${error}` : ""}
        message={
          loading
            ? "正在加载工具配置…"
            : savingKey
              ? "正在保存工具配置…"
              : saveMessage || "更改后自动保存。"
        }
      />
      {!loading && config ? (
        <section className="grid gap-3.5">
          <SensoryToolsToolbar controller={controller} stages={config.stages} />
          {batchMode ? (
            <p className={hint}>
              批量操作仅影响当前筛选结果中的可用工具；阶段关闭时，启用工具不会开启阶段。
            </p>
          ) : null}
          {!visibleCount ? (
            <p className={`${hint} py-4`}>没有匹配的工具，请调整搜索或筛选。</p>
          ) : null}
          {stageRows.map((row) => (
            <SensoryStage key={row.stage.name} row={row} controller={controller} />
          ))}
        </section>
      ) : null}
    </main>
  );
}

function SensoryToolsToolbar({
  controller,
  stages,
}: {
  controller: Controller;
  stages: NonNullable<Controller["config"]>["stages"];
}) {
  const {
    query,
    setQuery,
    stageFilter,
    setStageFilter,
    availability,
    setAvailability,
    showDescriptions,
    setShowDescriptions,
    batchMode,
    setBatchMode,
    visibleCount,
  } = controller;

  return (
    <div className="flex flex-wrap items-end gap-3 border border-solid border-border bg-panel p-3">
      <label className={filterLabel}>
        搜索工具
        <input
          className={`${filterInput} w-[260px] [@media(max-width:640px)]:w-full`}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="名称、用途或分类"
        />
      </label>
      <label className={filterLabel}>
        工作阶段
        <select
          className={filterInput}
          value={stageFilter}
          onChange={(event) => setStageFilter(event.target.value)}
        >
          <option value="">全部阶段</option>
          {stages.map((stage) => (
            <option key={stage.name} value={stage.name}>
              {stage.label}
            </option>
          ))}
        </select>
      </label>
      <label className={filterLabel}>
        可用性
        <select
          className={filterInput}
          value={availability}
          onChange={(event) => setAvailability(event.target.value)}
        >
          <option value="">全部工具</option>
          <option value="available">可用</option>
          <option value="unavailable">不可用</option>
        </select>
      </label>
      <label className="flex min-h-11 min-w-0 cursor-pointer items-center gap-2 text-xs text-muted [@media(max-width:640px)]:basis-full">
        <input
          className={checkbox}
          type="checkbox"
          checked={showDescriptions}
          onChange={(event) => setShowDescriptions(event.target.checked)}
        />
        展开用途说明
      </label>
      <Button
        aria-pressed={batchMode}
        className="aria-pressed:border-accent aria-pressed:bg-accent-soft aria-pressed:enabled:hover:bg-accent-soft"
        onClick={() => setBatchMode((value) => !value)}
      >
        批量管理
      </Button>
      <p className={hint} role="status">
        找到 {visibleCount} 个工具
      </p>
    </div>
  );
}

function SensoryStage({ row, controller }: { row: StageRow; controller: Controller }) {
  const { stage, hasMatches, groups } = row;
  const { batchMode, savingKey, showDescriptions, handleCategoryToggle, handleToggle } =
    controller;

  return (
    // Keep the rows mounted while filtering so native details keep their disclosure state.
    <article
      className={
        hasMatches
          ? "grid min-w-0 gap-3 border border-solid border-border bg-panel p-3.5"
          : "hidden"
      }
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="m-0 text-lg text-ink">
            {stage.label}
            <span className="ml-2 text-sm font-medium text-muted">
              ({countEnabledAvailable(stage.tools)}/{stage.tools.length})
            </span>
          </h2>
          <p className="m-0 mt-1 text-[13px] text-muted">{stage.description}</p>
        </div>
        {stage.stageEnabled ? (
          <Badge variant="positive">阶段可用</Badge>
        ) : (
          <Badge variant="negative">
            阶段关闭{stage.stageDisabledReason ? `：${stage.stageDisabledReason}` : ""}
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 [@media(max-width:760px)]:grid-cols-1">
        {groups.map((group) => (
          <div
            key={group.key}
            className={
              group.matchingTools.length
                ? "grid min-w-0 content-start gap-2 border border-solid border-border bg-panel p-2.5"
                : "hidden"
            }
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[11px] font-bold tracking-[0.06em] text-muted uppercase">
                {group.label}
              </div>
              {batchMode ? (
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    disabled={Boolean(savingKey)}
                    onClick={() =>
                      handleCategoryToggle(stage.name, group.matchingTools, true)
                    }
                  >
                    启用筛选结果
                  </Button>
                  <Button
                    disabled={Boolean(savingKey)}
                    onClick={() =>
                      handleCategoryToggle(stage.name, group.matchingTools, false)
                    }
                  >
                    停用筛选结果
                  </Button>
                </div>
              ) : null}
            </div>
            <div className="grid gap-2">
              {group.tools.map(({ tool, matches }) => {
                const itemKey = toolKey(stage.name, tool.name);
                return (
                  <div
                    key={itemKey}
                    className={
                      matches
                        ? "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2.5 border border-solid border-border bg-bg p-2.5"
                        : "hidden"
                    }
                  >
                    <div className="grid gap-1">
                      <div className="text-sm font-semibold text-ink">{tool.label}</div>
                      <details open={showDescriptions || undefined}>
                        <summary className="flex min-h-9 cursor-pointer items-center py-1.5 text-xs text-muted">
                          用途说明
                        </summary>
                        <p className="mx-0 my-1 text-xs leading-[1.6] text-muted">
                          {tool.description}
                        </p>
                      </details>
                      {!tool.available ? (
                        <div className="text-xs text-negative">
                          不可用：{tool.unavailableReason || "当前环境不支持"}
                        </div>
                      ) : null}
                    </div>
                    <label className="grid size-11 cursor-pointer place-items-center">
                      <input
                        className={checkbox}
                        type="checkbox"
                        aria-label={tool.label}
                        checked={tool.enabled}
                        disabled={!tool.available}
                        aria-busy={savingKey === itemKey}
                        onChange={(event) =>
                          handleToggle(stage.name, tool.name, event.target.checked)
                        }
                      />
                    </label>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
