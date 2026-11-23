"use client";

import { useId, useLayoutEffect, useRef } from "react";
import { Button } from "./button";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  trigger?: HTMLElement | null;
  fallbackFocus?: () => HTMLElement | null;
}

export function ConfirmDialog({
  title = "请确认",
  message,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger,
  trigger,
  fallbackFocus,
  onDecision,
}: ConfirmOptions & { onDecision: (confirmed: boolean) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const accept = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const messageId = useId();

  useLayoutEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const previouslyFocused = document.activeElement;
    const invoker =
      trigger ?? (previouslyFocused instanceof HTMLElement ? previouslyFocused : null);
    element.showModal();
    cancel.current?.focus({ preventScroll: true });
    return () => {
      if (element.open) element.close();
      if (!focusIfAvailable(invoker)) focusIfAvailable(fallbackFocus?.());
    };
  }, [trigger, fallbackFocus]);

  function decide(confirmed: boolean) {
    dialog.current?.close();
    onDecision(confirmed);
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      aria-describedby={messageId}
      aria-modal="true"
      className="m-auto max-h-[85dvh] w-[calc(100%_-_32px)] max-w-[480px] overflow-auto border border-border bg-bg p-[22px] text-ink backdrop:bg-ink/25"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        if (event.shiftKey && document.activeElement === cancel.current) {
          event.preventDefault();
          accept.current?.focus();
        } else if (!event.shiftKey && document.activeElement === accept.current) {
          event.preventDefault();
          cancel.current?.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        decide(false);
      }}
      onClose={(event) => {
        if (!event.currentTarget.open) onDecision(false);
      }}
    >
      <h2 id={titleId} className="m-0 text-lg font-bold">
        {title}
      </h2>
      <p
        id={messageId}
        className="my-[14px] whitespace-pre-wrap wrap-anywhere text-sm text-ink-2"
      >
        {message}
      </p>
      <div className="flex flex-wrap justify-end gap-2">
        <Button ref={cancel} onClick={() => decide(false)}>
          {cancelLabel}
        </Button>
        <Button
          ref={accept}
          variant={danger ? "danger" : "primary"}
          onClick={() => decide(true)}
        >
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}

function focusIfAvailable(element: HTMLElement | null | undefined) {
  if (
    !element?.isConnected ||
    element.matches(":disabled") ||
    !element.getClientRects().length
  ) {
    return false;
  }
  element.focus({ preventScroll: true });
  return document.activeElement === element;
}
