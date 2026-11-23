import { TopNav } from "../layout/top-nav";
import { Alert } from "../ui/alert";
import { Button } from "../ui/button";
import { StackedBarChart } from "./model-usage-chart";
import { formatNumber, workflowLabel } from "./model-usage-data";
import {
  CallRecordsTable,
  DailyBucketTable,
  FeatureModelSummaryTable,
  FeatureSummaryTable,
  UsageSection,
} from "./model-usage-tables";
import type { ModelUsageController } from "./use-model-usage-controller";

const field = "grid min-w-0 grow basis-[150px] gap-1 text-[11px] text-muted";
const control =
  "min-h-11 w-full min-w-0 border border-solid border-border bg-bg px-2.5 py-1.5 text-ink focus-visible:outline-2 focus-visible:outline-accent";

function UsageFilters({
  timeZone,
  timeZoneOptions,
  workflowFilter,
  operationFilter,
  dateFrom,
  dateTo,
  workflowOptions,
  operationOptions,
  onTimeZoneChange,
  onWorkflowChange,
  onOperationChange,
  onDateFromChange,
  onDateToChange,
  onExport,
}: ModelUsageController["filters"]) {
  return (
    <section
      className="mb-2 flex flex-wrap items-end gap-2.5 border border-solid border-border bg-panel p-3"
      aria-label="用量筛选"
    >
      <label className={field}>
        显示时区
        <select
          className={control}
          value={timeZone}
          onChange={(event) => onTimeZoneChange(event.target.value)}
        >
          {timeZoneOptions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label className={field}>
        Workflow
        <select
          className={control}
          value={workflowFilter}
          onChange={(event) => onWorkflowChange(event.target.value)}
        >
          <option value="">全部 workflow</option>
          {workflowOptions.map((value) => (
            <option key={value} value={value}>
              {workflowLabel(value)}
            </option>
          ))}
        </select>
      </label>
      <label className={field}>
        Operation
        <select
          className={control}
          value={operationFilter}
          onChange={(event) => onOperationChange(event.target.value)}
        >
          <option value="">全部 operation</option>
          {operationOptions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label className={field}>
        起始日期
        <input
          className={control}
          type="date"
          value={dateFrom}
          onChange={(event) => onDateFromChange(event.target.value)}
        />
      </label>
      <label className={field}>
        结束日期
        <input
          className={control}
          type="date"
          value={dateTo}
          onChange={(event) => onDateToChange(event.target.value)}
        />
      </label>
      <Button variant="primary" onClick={onExport}>
        导出当前筛选 CSV
      </Button>
    </section>
  );
}

function UsageSummary({ count, totals }: ModelUsageController["summary"]) {
  const cards = [
    { label: "总 Token", value: formatNumber(totals.total) },
    { label: "输入 Token", value: formatNumber(totals.prompt) },
    { label: "输出 Token", value: formatNumber(totals.completion) },
    { label: "调用次数", value: count },
  ];
  return (
    <dl className="m-0 mb-7 flex flex-wrap gap-3">
      {cards.map(({ label, value }) => (
        <div
          className="flex min-w-0 flex-[1_1_160px] flex-col gap-1 border border-solid border-border px-[18px] py-3.5"
          key={label}
        >
          <dt className="text-[11px] tracking-wider text-muted uppercase">{label}</dt>
          <dd className="m-0 text-2xl font-bold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ModelUsageView({
  ready,
  hasAggregateOnlyHistory,
  loading,
  error,
  filters,
  summary,
  days,
  featureSummary,
  featureModelSummary,
  buckets,
  calls,
}: ModelUsageController) {
  return (
    <main className="with-app-nav min-h-screen min-w-0 bg-bg text-ink">
      <TopNav currentPath="/model-usage" />
      <div className="mx-auto min-w-0 max-w-[900px] px-3 pt-8 pb-16 sm:px-6">
        <h1 className="m-0 mb-6 text-[28px] leading-[1.2] font-extrabold tracking-tight">
          用量审计
        </h1>
        {loading && (
          <p role="status" className="m-0 py-3 text-[13px] text-muted">
            加载中…
          </p>
        )}
        {error && (
          <Alert variant="negative" className="mb-4">
            {error}
          </Alert>
        )}
        {ready && (
          <>
            {hasAggregateOnlyHistory ? (
              <p role="status">旧版接口仅提供全量聚合，无法按调用筛选或导出。</p>
            ) : (
              <>
                <UsageFilters {...filters} />
                <p className="m-0 mb-5 text-xs text-muted wrap-anywhere">
                  当前显示时区：{filters.timeZone}
                  。筛选和分组按记录日期（UTC），不随显示时区变化。 Token 按 provider
                  返回值统计，实际费用以服务商账单为准。筛选结果 {summary.count} 条。
                </p>
                <UsageSummary {...summary} />
              </>
            )}
            <UsageSection title="按日期的 Token 用量（堆积柱状图）">
              <StackedBarChart days={days} />
            </UsageSection>
            <FeatureSummaryTable rows={featureSummary} />
            {!hasAggregateOnlyHistory && (
              <FeatureModelSummaryTable rows={featureModelSummary} />
            )}
            <DailyBucketTable rows={buckets} />
            {!hasAggregateOnlyHistory && <CallRecordsTable {...calls} />}
          </>
        )}
      </div>
    </main>
  );
}
