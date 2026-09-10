"use client";

import { usePersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import { PersonaWorkspaceView } from "./persona-workspace-view";

export function PersonaWorkspace() {
  const controller = usePersonaWorkspaceController();
  return <PersonaWorkspaceView controller={controller} />;
}
