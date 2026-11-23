"use client";

import { useEffect, useRef } from "react";
import type { SceneWorkspaceController } from "../../hooks/use-scene-workspace-controller";
import { TopNav } from "../layout/top-nav";
import { AsyncFeedback } from "../ui/async-feedback";
import { ProviderTruth } from "../ui/provider-truth";
import { SceneSidebar } from "./scene-sidebar";
import { SceneTreePanel } from "./scene-tree-panel";
import css from "./scene-workspace.module.css";

export function SceneWorkspaceView({
  controller,
}: {
  controller: SceneWorkspaceController;
}) {
  const {
    libraryError,
    reusableActionPendingId,
    reusableError,
    pageHeadingRef,
    sceneGeneratePending,
    sceneGenerateError,
    rewritePendingKey,
    rewriteError,
    isCompactLayout,
    pageNotice,
    sceneIoPending,
    sceneIoError,
  } = controller;
  const feedbackRef = useRef<HTMLDivElement>(null);
  const actionTriggerRef = useRef<Element | null>(null);
  const actionPending = Boolean(
    sceneIoPending ||
    sceneGeneratePending ||
    rewritePendingKey ||
    reusableActionPendingId,
  );
  const userError = [sceneIoError, sceneGenerateError, rewriteError, reusableError]
    .filter(Boolean)
    .join("；");
  const previousUserError = useRef(userError);
  useEffect(() => {
    // Synchronous validation may be batched without rendering a pending state.
    // Background library failures are deliberately excluded from this focus path.
    if (
      userError &&
      userError !== previousUserError.current &&
      document.activeElement === actionTriggerRef.current &&
      document.activeElement !== document.body
    ) {
      feedbackRef.current
        ?.querySelector<HTMLElement>('[role="alert"]')
        ?.focus({ preventScroll: true });
    }
    previousUserError.current = userError;
  }, [userError]);
  return (
    <main
      className="with-app-nav mx-auto flex h-screen w-full max-w-[1600px] flex-col overflow-hidden bg-bg px-7 pb-7"
      onClickCapture={(event) => {
        if (!actionPending && (event.target as HTMLElement).closest("button"))
          actionTriggerRef.current = document.activeElement;
      }}
    >
      <TopNav currentPath="/scene-setup" />

      <div className={`${css.heading} sticky top-0 z-15 mb-4 border-b pt-5 pb-4`}>
        <div className="flex flex-wrap items-center gap-3">
          <h1
            ref={pageHeadingRef}
            tabIndex={-1}
            className="m-0 text-xl/[1.2] font-bold text-ink"
          >
            场景搭建
          </h1>
          <ProviderTruth scope="scene" />
          <div
            ref={feedbackRef}
            role="region"
            aria-label="场景操作反馈"
            tabIndex={0}
            className={`${css.notice} grid h-[104px] w-full min-w-0 shrink-0 content-start gap-1 overflow-y-auto px-2 py-1.5 text-xs/[1.4] text-ink-2`}
          >
            <AsyncFeedback
              actionRef={actionTriggerRef}
              pending={actionPending}
              error={userError}
              message={pageNotice}
            />
            {libraryError ? (
              <p role="alert" className="text-xs/[1.5] text-danger">
                部分场景库数据未能读取，请刷新页面重试。
              </p>
            ) : null}
          </div>
        </div>
      </div>
      <div
        className={`flex min-h-0 flex-1 gap-3.5 ${isCompactLayout ? "flex-col overflow-x-hidden overflow-y-auto" : "overflow-hidden"}`}
      >
        <SceneTreePanel controller={controller} />
        <SceneSidebar controller={controller} />
      </div>
    </main>
  );
}
