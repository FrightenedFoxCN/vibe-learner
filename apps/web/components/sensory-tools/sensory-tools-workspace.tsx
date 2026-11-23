"use client";

import { SensoryToolsView } from "./sensory-tools-view";
import { useSensoryToolsController } from "./use-sensory-tools-controller";

export function SensoryToolsWorkspace() {
  const controller = useSensoryToolsController();
  return <SensoryToolsView controller={controller} />;
}
