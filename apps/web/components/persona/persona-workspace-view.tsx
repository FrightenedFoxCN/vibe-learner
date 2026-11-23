"use client";

import { useRef, type RefObject } from "react";
import { AsyncFeedback } from "../ui/async-feedback";
import { TopNav } from "../layout/top-nav";
import { ProviderTruth } from "../ui/provider-truth";
import type { PersonaWorkspaceController } from "../../hooks/use-persona-workspace-controller";
import { PersonaBasicsPane } from "./persona-basics-pane";
import { PersonaSlotsPane } from "./persona-slots-pane";
import { PersonaCardGeneration } from "./persona-card-generation";
import { PersonaCardLibrary, PersonaProfileLibrary } from "./persona-library-panes";
import styles from "./persona-workspace.module.css";

export function PersonaWorkspaceView({
  controller,
}: {
  controller: PersonaWorkspaceController;
}) {
  const feedbackAction = useRef<Element | null>(null);
  const { isCompactLayout, loadError } = controller;
  return (
    <main
      onClickCapture={(event) => {
        feedbackAction.current = (event.target as Element).closest(
          "button, input, select",
        );
      }}
      className={`with-app-nav persona-workspace-page ${styles.workspace}`}
      data-compact={isCompactLayout}
    >
      <TopNav currentPath="/persona-spectrum" />

      <PersonaWorkspaceHeading
        controller={controller}
        feedbackAction={feedbackAction}
      />

      {loadError ? (
        <div role="alert" className={styles.errorBanner}>
          加载失败: {loadError}
        </div>
      ) : null}

      <div className={styles.workspaceShell}>
        <div className={styles.mainColumn}>
          <div className={styles.editorArea}>
            <PersonaBasicsPane controller={controller} />
            <PersonaSlotsPane controller={controller} />
          </div>
        </div>
        <aside className={styles.sidebarPane}>
          <PersonaCardGeneration controller={controller} />
          <PersonaCardLibrary controller={controller} />
          <PersonaProfileLibrary controller={controller} />
        </aside>
      </div>
    </main>
  );
}

function PersonaWorkspaceHeading({
  controller,
  feedbackAction,
}: {
  controller: PersonaWorkspaceController;
  feedbackAction: RefObject<Element | null>;
}) {
  const {
    assistPending,
    slotAssistIndex,
    assistError,
    configMessage,
    configError,
    cardActionPending,
    cardMessage,
    cardError,
    cardDeletePendingId,
    savingPersona,
    saveError,
    personaDeletePendingId,
    personaLibraryMessage,
    personaLibraryError,
    pageNotice,
  } = controller;
  return (
    <div className={styles.heading}>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="m-0 text-[20px] leading-[1.2] font-bold text-ink">人格色谱</h1>
        <ProviderTruth scope="persona" />
        <AsyncFeedback
          actionRef={feedbackAction}
          synchronousError={saveError}
          pending={
            savingPersona ||
            assistPending ||
            slotAssistIndex !== null ||
            Boolean(cardActionPending) ||
            Boolean(personaDeletePendingId) ||
            Boolean(cardDeletePendingId)
          }
          error={[saveError, assistError, configError, cardError, personaLibraryError]
            .filter(Boolean)
            .join("；")}
          message={
            savingPersona
              ? "正在保存人格…"
              : assistPending
                ? "正在生成建议…"
                : slotAssistIndex !== null || cardActionPending
                  ? pageNotice
                  : personaLibraryMessage || cardMessage || configMessage || pageNotice
          }
        />
      </div>
    </div>
  );
}
