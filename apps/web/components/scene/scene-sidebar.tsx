import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { SceneGenerator } from "./scene-generator";
import { ReusableNodeLibrary, SavedSceneLibrary } from "./scene-libraries";
import css from "./scene-workspace.module.css";

export function SceneSidebar({ controller }: { controller: SceneWorkspaceController }) {
  return (
    <aside
      className={`flex min-h-0 shrink-0 flex-col gap-2.5 ${controller.isCompactLayout ? "w-full overflow-visible" : "w-[360px] overflow-y-auto"}`}
    >
      <SceneMetadata controller={controller} />
      <SceneGenerator controller={controller} />
      <ReusableNodeLibrary controller={controller} />
      <SavedSceneLibrary controller={controller} />
    </aside>
  );
}

function SceneMetadata({ controller }: { controller: SceneWorkspaceController }) {
  const {
    sceneName,
    setSceneName,
    sceneSummary,
    setSceneSummary,
    updateSceneGenerationInput,
    sceneNodeCount,
    sceneObjectCount,
  } = controller;
  return (
    <div
      className={`${css.panelSurface} shrink-0 overflow-hidden border border-border`}
    >
      <div
        className={`${css.sectionDivider} flex items-center justify-between gap-3 border-b px-3 py-2.5`}
      >
        <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
          当前场景
        </span>
        <span className="text-[11px] whitespace-nowrap text-muted">
          {sceneNodeCount} 节点 · {sceneObjectCount} 物体
        </span>
      </div>
      <div className="grid content-start gap-2 px-3 pt-4 pb-3">
        <label className="grid gap-1.5">
          <span className={css.fieldLabel}>场景名称</span>
          <input
            className="min-h-11 w-full border border-border bg-bg px-2.5 py-[7px] text-[13px] text-ink outline-offset-2"
            value={sceneName}
            onChange={(event) =>
              updateSceneGenerationInput(() => setSceneName(event.target.value))
            }
            placeholder="例如：高一物理-力学基础"
          />
        </label>
        <label className="grid gap-1.5">
          <span className={css.fieldLabel}>场景摘要</span>
          <textarea
            className="min-h-20 w-full resize-y border border-border bg-bg px-2.5 py-[7px] text-[13px]/[1.6] text-ink outline-offset-2"
            value={sceneSummary}
            onChange={(event) =>
              updateSceneGenerationInput(() => setSceneSummary(event.target.value))
            }
            placeholder="用自己的话描述这个场景。"
          />
        </label>
      </div>
    </div>
  );
}
