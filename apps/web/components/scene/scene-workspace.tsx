"use client";

import { useSceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { SceneWorkspaceView } from "./scene-workspace-view";

export function SceneWorkspace() {
  const controller = useSceneWorkspaceController();
  return <SceneWorkspaceView controller={controller} />;
}
