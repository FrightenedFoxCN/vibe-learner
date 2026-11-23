import { useRef, type Dispatch, type SetStateAction } from "react";
import type { StudySessionRecord } from "@vibe-learner/shared";
import { MaterialIcon } from "../ui/material-icon";
import type { StudyConsoleProps } from "./study-console-types";
import { formatAttachmentLabel, formatFileSize } from "./study-console-format";

type StudyAttachmentPickerProps = Pick<
  StudyConsoleProps,
  "disabled" | "isPending" | "chatImageUploadEnabled"
> & {
  setAttachments: Dispatch<SetStateAction<File[]>>;
  recoveryLocked: boolean;
};

export function StudyAttachmentPicker({
  disabled,
  isPending,
  chatImageUploadEnabled,
  setAttachments,
  recoveryLocked,
}: StudyAttachmentPickerProps) {
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <>
      <input
        ref={attachmentInputRef}
        type="file"
        multiple
        accept={
          chatImageUploadEnabled
            ? "image/*,.pdf,.txt,.md,.markdown,.json,.csv,.log,.yaml,.yml,.xml"
            : ".pdf,.txt,.md,.markdown,.json,.csv,.log,.yaml,.yml,.xml"
        }
        className="study-console-hidden-file-input"
        onChange={(event) => {
          const nextFiles = Array.from(event.target.files ?? []);
          if (!nextFiles.length) {
            return;
          }
          setAttachments((current) => {
            const deduped = [...current];
            nextFiles.forEach((file) => {
              if (
                deduped.some(
                  (item) =>
                    item.name === file.name &&
                    item.size === file.size &&
                    item.type === file.type,
                )
              ) {
                return;
              }
              deduped.push(file);
            });
            return deduped.slice(0, 4);
          });
          event.currentTarget.value = "";
        }}
      />
      <button
        type="button"
        className="study-console-icon-tool-button study-console-btn-disabled"
        disabled={disabled || isPending || recoveryLocked}
        onClick={() => attachmentInputRef.current?.click()}
        aria-label="添加附件"
        title="添加附件"
      >
        <MaterialIcon name="attach_file" size={16} />
      </button>
    </>
  );
}

type StudyAttachmentDraftsProps = Pick<
  StudyAttachmentPickerProps,
  "setAttachments" | "disabled" | "isPending"
> & { attachments: File[] };

export function StudyAttachmentDrafts({
  attachments,
  setAttachments,
  disabled,
  isPending,
}: StudyAttachmentDraftsProps) {
  if (!attachments.length) return null;

  return (
    <div className="study-console-attachment-draft-list">
      {attachments.map((file) => (
        <div
          key={`${file.name}:${file.size}:${file.type}`}
          className="study-console-attachment-draft-item"
        >
          <span className="study-console-attachment-draft-text">
            {file.name} · {formatFileSize(file.size)}
            {file.type.startsWith("image/") ? " · 图片" : ""}
          </span>
          <button
            type="button"
            className="study-console-attachment-remove-btn study-console-btn-disabled"
            disabled={disabled || isPending}
            onClick={() => {
              setAttachments((current) =>
                current.filter(
                  (item) =>
                    !(
                      item.name === file.name &&
                      item.size === file.size &&
                      item.type === file.type
                    ),
                ),
              );
            }}
          >
            移除
          </button>
        </div>
      ))}
    </div>
  );
}

export function StudyTurnAttachments({
  attachments,
}: {
  attachments: StudySessionRecord["turns"][number]["learnerAttachments"];
}) {
  if (!attachments?.length) return null;

  return (
    <div className="study-console-attachment-chip-row">
      {attachments.map((attachment) => (
        <span key={attachment.attachmentId} className="study-console-attachment-chip">
          {formatAttachmentLabel(attachment)}
        </span>
      ))}
    </div>
  );
}
