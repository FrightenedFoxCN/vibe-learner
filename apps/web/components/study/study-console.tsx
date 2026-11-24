"use client";

import { useEffect, useState } from "react";
import type { StudyConsoleProps } from "./study-console-types";
import { StudyMessageFlow } from "./study-message-flow";
import { StudyChatRecovery, StudyStatusStrip } from "./study-status";
import { StudyPlanConfirmations } from "./study-plan-confirmations";
import { StudyComposer } from "./study-composer";
import { StudyConsoleSidebar } from "./study-console-sidebar";
import "./study-console.css";

export function StudyConsole({
  workspaceTools,
  isPending,
  selectedPlanId,
  planOptions,
  onSelectPlan,
  onCreateSession,
  showCreateSession = false,
  onAsk,
  outputLanguage = "auto",
  outputLanguageScope = "",
  onSubmitQuestionAttempt,
  onContinueAfterQuestion,
  onChangeSchedule,
  onOpenCitation,
  onOpenNoteReference,
  onJumpToScheduleStart,
  canJumpToScheduleStart,
  onCompleteCurrentSchedule,
  canCompleteCurrentSchedule,
  chatErrorMessage,
  chatOperationStatus,
  canQueryLastAsk,
  canResendLastAsk,
  canRefreshSessionAfterAsk,
  onQueryLastAsk,
  onRetryLastAsk,
  onRefreshSessionAfterAsk,
  selectedScheduleId,
  scheduleOptions,
  turns,
  session,
  persona,
  sceneProfile,
  pendingFollowUps = [],
  isDialogueInterrupted = false,
  onInterruptDialogue,
  affinityState,
  planConfirmations = [],
  onResolvePlanConfirmation,
  chatImageUploadEnabled,
  pendingComposerInsert,
  onConsumeComposerInsert,
  disabled,
  cachedState,
  onCachedStateChange,
}: StudyConsoleProps) {
  const [languagePreference, setLanguagePreference] = useState(outputLanguage);
  useEffect(() => {
    setLanguagePreference(outputLanguage);
  }, [outputLanguage, outputLanguageScope]);
  const recoveryLocked = Boolean(chatErrorMessage && canQueryLastAsk);
  const refreshRequired = Boolean(chatErrorMessage && canRefreshSessionAfterAsk);
  const [message, setMessage] = useState(
    () => cachedState?.message ?? "请解释这一章的核心概念，并给我一个复述练习。",
  );
  const [attachments, setAttachments] = useState<File[]>(
    () => cachedState?.attachments ?? [],
  );
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>(
    () => cachedState?.selectedChoices ?? {},
  );
  const [blankAnswers, setBlankAnswers] = useState<Record<string, string>>(
    () => cachedState?.blankAnswers ?? {},
  );
  const [expandedExplanation, setExpandedExplanation] = useState<
    Record<string, boolean>
  >(() => cachedState?.expandedExplanation ?? {});

  useEffect(() => {
    onCachedStateChange?.({
      message,
      attachments,
      selectedChoices,
      blankAnswers,
      expandedExplanation,
    });
  }, [
    attachments,
    blankAnswers,
    expandedExplanation,
    message,
    onCachedStateChange,
    selectedChoices,
  ]);

  return (
    <div className="study-console-card">
      <section className="study-console-chat-panel" aria-label="学习对话">
        <StudyStatusStrip
          isPending={isPending}
          disabled={disabled}
          chatErrorMessage={chatErrorMessage}
        />
        <StudyMessageFlow
          turns={turns}
          session={session}
          onOpenCitation={onOpenCitation}
          onOpenNoteReference={onOpenNoteReference}
          onAsk={onAsk}
          onSubmitQuestionAttempt={onSubmitQuestionAttempt}
          onContinueAfterQuestion={onContinueAfterQuestion}
          disabled={disabled}
          isPending={isPending}
          chatErrorMessage={chatErrorMessage}
          selectedChoices={selectedChoices}
          blankAnswers={blankAnswers}
          expandedExplanation={expandedExplanation}
          setSelectedChoices={setSelectedChoices}
          setBlankAnswers={setBlankAnswers}
          setExpandedExplanation={setExpandedExplanation}
          personaName={persona.name}
        />
        <StudyChatRecovery
          isPending={isPending}
          disabled={disabled}
          chatErrorMessage={chatErrorMessage}
          chatOperationStatus={chatOperationStatus}
          canQueryLastAsk={canQueryLastAsk}
          canResendLastAsk={canResendLastAsk}
          canRefreshSessionAfterAsk={canRefreshSessionAfterAsk}
          onQueryLastAsk={onQueryLastAsk}
          onRetryLastAsk={onRetryLastAsk}
          onRefreshSessionAfterAsk={onRefreshSessionAfterAsk}
        />
        <StudyPlanConfirmations
          planConfirmations={planConfirmations}
          onResolvePlanConfirmation={onResolvePlanConfirmation}
          disabled={disabled}
          isPending={isPending}
        />
        <StudyComposer
          disabled={disabled}
          isPending={isPending}
          chatImageUploadEnabled={chatImageUploadEnabled}
          onInterruptDialogue={onInterruptDialogue}
          isDialogueInterrupted={isDialogueInterrupted}
          pendingComposerInsert={pendingComposerInsert}
          onConsumeComposerInsert={onConsumeComposerInsert}
          onAsk={onAsk}
          draftScope={JSON.stringify([
            selectedPlanId,
            selectedScheduleId,
            outputLanguageScope,
          ])}
          personaName={persona.name}
          message={message}
          setMessage={setMessage}
          attachments={attachments}
          setAttachments={setAttachments}
          languagePreference={languagePreference}
          recoveryLocked={recoveryLocked}
          refreshRequired={refreshRequired}
        />
      </section>
      <div className="study-console-rail">
        {workspaceTools}
        <StudyConsoleSidebar
          selectedPlanId={selectedPlanId}
          planOptions={planOptions}
          onSelectPlan={onSelectPlan}
          onCreateSession={onCreateSession}
          showCreateSession={showCreateSession}
          selectedScheduleId={selectedScheduleId}
          scheduleOptions={scheduleOptions}
          onChangeSchedule={onChangeSchedule}
          onJumpToScheduleStart={onJumpToScheduleStart}
          canJumpToScheduleStart={canJumpToScheduleStart}
          onCompleteCurrentSchedule={onCompleteCurrentSchedule}
          canCompleteCurrentSchedule={canCompleteCurrentSchedule}
          persona={persona}
          sceneProfile={sceneProfile}
          session={session}
          affinityState={affinityState}
          isPending={isPending}
          disabled={disabled}
          pendingFollowUps={pendingFollowUps}
          turnCount={turns.length}
          languagePreference={languagePreference}
          setLanguagePreference={setLanguagePreference}
          languageInputLocked={Boolean(
            isPending || disabled || recoveryLocked || refreshRequired,
          )}
        />
      </div>
    </div>
  );
}
