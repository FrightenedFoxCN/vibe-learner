import type { ModelRecovery } from "@vibe-learner/shared";

export function ModelFallbackNotice({ recoveries }: { recoveries: ModelRecovery[] }) {
  if (!recoveries.some((item) => item.strategy === "local_fallback")) return null;
  return (
    <p role="status" style={{ color: "#885300", fontSize: 13 }}>
      模型润色未完成，已使用本地规则；部分内容可能保持原样。请检查结果后再保存，或稍后重新润色。
    </p>
  );
}
