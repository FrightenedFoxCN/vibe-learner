import type { ReactNode } from "react";
import type { TokenUsageDailyBucket } from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import { Button } from "../ui/button";
import { UsageFeatureDot } from "./model-usage-chart";
import {
  featureLabel,
  formatNumber,
  workflowLabel,
  type FeatureSummary,
  type FeatureModelSummary,
} from "./model-usage-data";
import type { ModelUsageController } from "./use-model-usage-controller";

export function UsageSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mb-9 min-w-0">
      <h2 className="m-0 mb-3.5 text-sm font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}

const cell = "border-b border-solid border-border px-3 py-2 align-middle";
const tokenHeaders = ["输入", "输出", "合计"];
const summaryTokenHeaders = ["输入 Token", "输出 Token", "合计"];

function UsageTable({
  left,
  right,
  children,
}: {
  left: string[];
  right: string[];
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            {left.map((label) => (
              <th
                className={`${cell} text-left text-[11px] font-semibold whitespace-nowrap text-muted`}
                scope="col"
                key={label}
              >
                {label}
              </th>
            ))}
            {right.map((label) => (
              <th
                className={`${cell} text-right text-[11px] font-semibold whitespace-nowrap text-muted`}
                scope="col"
                key={label}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function FeatureCell({ feature, children }: { feature: string; children?: ReactNode }) {
  return (
    <td className={`${cell} wrap-anywhere`}>
      <UsageFeatureDot feature={feature} />
      {featureLabel(feature)}
      {children}
    </td>
  );
}

function ModelCell({ model }: { model: string }) {
  return <td className={`${cell} font-mono text-[11px] wrap-anywhere`}>{model}</td>;
}

function TokenCells({
  row,
}: {
  row: Pick<FeatureSummary, "promptTokens" | "completionTokens" | "totalTokens">;
}) {
  return (
    <>
      <td className={`${cell} text-right tabular-nums`}>
        {formatNumber(row.promptTokens)}
      </td>
      <td className={`${cell} text-right tabular-nums`}>
        {formatNumber(row.completionTokens)}
      </td>
      <td className={`${cell} text-right font-semibold tabular-nums`}>
        {formatNumber(row.totalTokens)}
      </td>
    </>
  );
}

function EmptySummary() {
  return <p className="py-3 text-[13px] text-muted">暂无数据</p>;
}

export function FeatureSummaryTable({ rows }: { rows: FeatureSummary[] }) {
  return (
    <UsageSection title="按功能汇总">
      {rows.length === 0 ? (
        <EmptySummary />
      ) : (
        <UsageTable left={["功能"]} right={summaryTokenHeaders}>
          {rows.map((row) => (
            <tr key={row.feature}>
              <FeatureCell feature={row.feature} />
              <TokenCells row={row} />
            </tr>
          ))}
        </UsageTable>
      )}
    </UsageSection>
  );
}

export function FeatureModelSummaryTable({ rows }: { rows: FeatureModelSummary[] }) {
  return (
    <UsageSection title="按功能 × 模型汇总">
      {rows.length === 0 ? (
        <EmptySummary />
      ) : (
        <UsageTable
          left={["功能", "模型"]}
          right={["调用次数", ...summaryTokenHeaders]}
        >
          {rows.map((row) => (
            <tr key={`${row.feature}-${row.model}`}>
              <FeatureCell feature={row.feature} />
              <ModelCell model={row.model} />
              <td className={`${cell} text-right tabular-nums`}>
                {formatNumber(row.callCount)}
              </td>
              <TokenCells row={row} />
            </tr>
          ))}
        </UsageTable>
      )}
    </UsageSection>
  );
}

export function DailyBucketTable({ rows }: { rows: TokenUsageDailyBucket[] }) {
  if (rows.length === 0) return null;
  return (
    <UsageSection title="明细记录（按日期 × 功能 × 模型）">
      <UsageTable left={["日期", "功能", "模型"]} right={tokenHeaders}>
        {rows.map((row, index) => (
          <tr key={`${row.date}-${row.feature}-${row.model}-${index}`}>
            <td className={cell}>{row.date}</td>
            <FeatureCell feature={row.feature} />
            <ModelCell model={row.model} />
            <TokenCells row={row} />
          </tr>
        ))}
      </UsageTable>
    </UsageSection>
  );
}

export function CallRecordsTable({
  hasRecords,
  visibleRecords,
  timeZone,
  recordPage,
  pageCount,
  onPrevious,
  onNext,
}: ModelUsageController["calls"]) {
  if (!hasRecords) return null;
  return (
    <UsageSection title="逐次调用明细">
      <UsageTable left={["时间", "功能", "模型"]} right={tokenHeaders}>
        {visibleRecords.map((record) => (
          <tr key={record.id}>
            <td className={cell}>
              {formatTimestamp(record.createdAt, { style: "full", timeZone })}
            </td>
            <FeatureCell feature={record.feature}>
              <br />
              <small>
                {workflowLabel(record.workflow)} ·{" "}
                {record.operationId || "无 operation"}
              </small>
            </FeatureCell>
            <ModelCell model={record.model} />
            <TokenCells row={record} />
          </tr>
        ))}
      </UsageTable>
      <nav
        className="mt-2.5 flex flex-wrap items-center justify-end gap-2 text-xs text-muted"
        aria-label="用量分页"
      >
        <span>
          第 {recordPage} / {pageCount} 页
        </span>
        <Button disabled={recordPage <= 1} onClick={onPrevious}>
          上一页
        </Button>
        <Button disabled={recordPage >= pageCount} onClick={onNext}>
          下一页
        </Button>
      </nav>
    </UsageSection>
  );
}
