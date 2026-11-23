import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { outputLanguageError } from "../../lib/output-language";
import { hasStudyLearnerInput } from "../../lib/study-chat-input";
import { MaterialIcon } from "../ui/material-icon";
import type { StudyConsoleProps } from "./study-console-types";
import { StudyAttachmentPicker, StudyAttachmentDrafts } from "./study-attachments";

type StudyComposerProps = Pick<
  StudyConsoleProps,
  | "disabled"
  | "isPending"
  | "chatImageUploadEnabled"
  | "onInterruptDialogue"
  | "isDialogueInterrupted"
  | "pendingComposerInsert"
  | "onConsumeComposerInsert"
  | "onAsk"
> & {
  personaName: string;
  message: string;
  setMessage: Dispatch<SetStateAction<string>>;
  attachments: File[];
  setAttachments: Dispatch<SetStateAction<File[]>>;
  languagePreference: string;
  recoveryLocked: boolean;
  refreshRequired: boolean;
};

export function StudyComposer({
  disabled,
  isPending,
  chatImageUploadEnabled,
  onInterruptDialogue,
  isDialogueInterrupted,
  pendingComposerInsert,
  onConsumeComposerInsert,
  onAsk,
  personaName,
  message,
  setMessage,
  attachments,
  setAttachments,
  languagePreference,
  recoveryLocked,
  refreshRequired,
}: StudyComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const languageError = outputLanguageError(languagePreference);
  const hasInput = hasStudyLearnerInput(message, attachments);

  useEffect(() => {
    if (!pendingComposerInsert?.id || !pendingComposerInsert.text) {
      return;
    }
    setMessage((current) => {
      const trimmed = current.trimEnd();
      const prefix = trimmed ? `${trimmed}\n\n` : "";
      return `${prefix}${pendingComposerInsert.text}`;
    });
    textareaRef.current?.focus();
    onConsumeComposerInsert?.();
  }, [onConsumeComposerInsert, pendingComposerInsert, setMessage]);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
  }, [message]);

  return (
    <div className="study-console-input-area">
      <div className="study-console-input-stack">
        <textarea
          ref={textareaRef}
          className="study-console-textarea"
          aria-label={`向${personaName}提问`}
          placeholder="输入本节学习问题…"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          disabled={disabled || isPending || recoveryLocked}
        />
        <details className="study-console-memory-help">
          <summary>如何保存原文记忆</summary>
          <p>
            输入以下指令，将中间的原文保存到当前会话的指定记忆键。键名使用字母、数字、下划线或短横线；原文最多
            4000 字，首尾不能留空白。请等待保存结果后再继续。
          </p>
          <pre className="study-console-memory-help-code">
            {"/remember-verbatim my_note\n需要逐字保留的原文\n/end-remember"}
          </pre>
        </details>
        <div className="study-console-attachment-toolbar">
          <StudyAttachmentPicker
            setAttachments={setAttachments}
            disabled={disabled}
            isPending={isPending}
            recoveryLocked={recoveryLocked}
            chatImageUploadEnabled={chatImageUploadEnabled}
          />
          {onInterruptDialogue ? (
            <button
              type="button"
              className="study-console-icon-tool-button study-console-btn-disabled"
              disabled={disabled || isPending || isDialogueInterrupted}
              onClick={() => {
                void onInterruptDialogue();
              }}
              aria-label={isDialogueInterrupted ? "已举手打断" : "举手打断"}
              title={isDialogueInterrupted ? "已举手打断" : "举手打断"}
            >
              <MaterialIcon name="front_hand" size={16} />
            </button>
          ) : null}
          <button
            className="study-console-icon-send-button study-console-btn-disabled"
            disabled={
              isPending ||
              disabled ||
              recoveryLocked ||
              refreshRequired ||
              !hasInput ||
              Boolean(languageError)
            }
            onClick={async () => {
              if (languageError || !hasInput) return;
              const didSend = await onAsk(message, attachments, languagePreference);
              if (!didSend) {
                return;
              }
              setMessage("");
              setAttachments([]);
            }}
            aria-label={
              recoveryLocked
                ? "请先查询本次请求结果"
                : refreshRequired
                  ? "请先刷新会话状态"
                  : isPending
                    ? "发送中"
                    : "发送"
            }
            title={
              recoveryLocked
                ? "请先查询本次请求结果"
                : refreshRequired
                  ? "请先刷新会话状态"
                  : isPending
                    ? "发送中"
                    : "发送"
            }
          >
            <MaterialIcon name="send" size={16} />
          </button>
        </div>
        <StudyAttachmentDrafts
          attachments={attachments}
          setAttachments={setAttachments}
          disabled={disabled}
          isPending={isPending}
        />
      </div>
    </div>
  );
}
