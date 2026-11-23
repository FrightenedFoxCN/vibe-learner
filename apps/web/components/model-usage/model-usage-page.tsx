"use client";

import { ModelUsageView } from "./model-usage-view";
import { useModelUsageController } from "./use-model-usage-controller";

export function ModelUsagePage() {
  const controller = useModelUsageController();
  return <ModelUsageView {...controller} />;
}
