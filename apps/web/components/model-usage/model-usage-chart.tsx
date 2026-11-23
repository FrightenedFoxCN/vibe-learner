import { featureLabel, formatNumber, type DayData } from "./model-usage-data";
// Data-series colors are distinct from semantic action/status colors.
function featurePalette(feature: string) {
  switch (feature) {
    case "plan":
      return "bg-indigo-500 fill-indigo-500";
    case "chat":
      return "bg-green-500 fill-green-500";
    case "setting":
      return "bg-amber-500 fill-amber-500";
    case "embedding":
      return "bg-cyan-500 fill-cyan-500";
    default:
      return "bg-slate-400 fill-slate-400";
  }
}

export function UsageFeatureDot({
  feature,
  legend = false,
}: {
  feature: string;
  legend?: boolean;
}) {
  const size = legend ? "size-2.5" : "mr-1.5 inline-block size-2 align-middle";
  return (
    <span
      aria-hidden="true"
      className={`${featurePalette(feature)} shrink-0 rounded-[2px] ${size}`}
    />
  );
}

export function StackedBarChart({ days }: { days: DayData[] }) {
  if (days.length === 0) {
    return <div className="py-10 text-center text-[13px] text-muted">暂无数据</div>;
  }

  const maxTotal = Math.max(...days.map((d) => d.total), 1);
  const chartHeight = 200;
  const barWidth = Math.max(20, Math.min(48, Math.floor(600 / days.length) - 4));
  const gutter = Math.max(4, Math.min(12, Math.floor(200 / days.length)));
  const chartWidth = days.length * (barWidth + gutter) + gutter;

  const uniqueFeatures = Array.from(
    new Set(days.flatMap((d) => d.segments.map((s) => s.feature))),
  ).sort();

  return (
    <div className="min-w-0 border border-solid border-border px-4 pt-4 pb-2">
      <div className="mb-3 flex flex-wrap gap-4">
        {uniqueFeatures.map((f) => (
          <span key={f} className="flex items-center gap-1.5 text-xs text-muted">
            <UsageFeatureDot feature={f} legend />
            {featureLabel(f)}
          </span>
        ))}
      </div>
      <div className="overflow-x-auto">
        <svg
          width={chartWidth}
          height={chartHeight + 40}
          role="img"
          aria-label="模型用量堆积柱状图"
        >
          {/* Y-axis gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = chartHeight - ratio * chartHeight;
            return (
              <line
                key={ratio}
                x1={0}
                y1={y}
                x2={chartWidth}
                y2={y}
                stroke="var(--border)"
                strokeWidth={1}
              />
            );
          })}

          {days.map((day, i) => {
            const x = gutter + i * (barWidth + gutter);
            let stackY = chartHeight;
            const totalBarHeight = (day.total / maxTotal) * chartHeight;

            const rects = day.segments
              .slice()
              .sort((a, b) => a.feature.localeCompare(b.feature))
              .map((seg) => {
                const segHeight = (seg.tokens / maxTotal) * chartHeight;
                stackY -= segHeight;
                return (
                  <rect
                    key={`${seg.feature}-${seg.model}`}
                    x={x}
                    y={stackY}
                    width={barWidth}
                    height={segHeight}
                    className={featurePalette(seg.feature)}
                    opacity={0.85}
                  >
                    <title>
                      {day.date} · {featureLabel(seg.feature)} ({seg.model}){"\n"}
                      {formatNumber(seg.tokens)} tokens
                    </title>
                  </rect>
                );
              });

            return (
              <g key={day.date}>
                {rects}
                {/* Total label above bar */}
                {totalBarHeight > 12 && (
                  <text
                    x={x + barWidth / 2}
                    y={chartHeight - totalBarHeight - 3}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--muted)"
                  >
                    {formatNumber(day.total)}
                  </text>
                )}
                {/* Date label below */}
                <text
                  x={x + barWidth / 2}
                  y={chartHeight + 14}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--muted)"
                  transform={`rotate(-30, ${x + barWidth / 2}, ${chartHeight + 14})`}
                >
                  {day.date.slice(5)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
