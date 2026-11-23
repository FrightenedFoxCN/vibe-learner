const shortTimestampOptions = {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
} satisfies Intl.DateTimeFormatOptions;

const debugTimestampOptions = {
  ...shortTimestampOptions,
  second: "2-digit",
  hour12: false,
} satisfies Intl.DateTimeFormatOptions;

type TimestampOptions =
  | { style: "short" }
  | { style: "debug"; empty?: string }
  | { style: "full"; timeZone?: string };

export function formatTimestamp(
  value: string | undefined,
  options: TimestampOptions,
): string {
  if (!value) {
    if (options.style === "short") return "未知时间";
    if (options.style === "full") return "-";
    return options.empty ?? "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  if (options.style === "full") {
    return new Intl.DateTimeFormat("zh-CN", {
      ...debugTimestampOptions,
      year: "numeric",
      ...(options.timeZone ? { timeZone: options.timeZone } : {}),
    }).format(date);
  }

  return date.toLocaleString(
    "zh-CN",
    options.style === "short" ? shortTimestampOptions : debugTimestampOptions,
  );
}

export function formatElapsedMs(value: number): string {
  if (!value) return "进行中";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}
