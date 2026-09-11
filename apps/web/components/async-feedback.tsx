"use client";

import { useEffect, useRef, type RefObject } from "react";

/** Announce operation feedback; move to a failure only if its initiating control still owns focus. */
export function AsyncFeedback({ pending, error, message, actionRef, synchronousError }: { pending: boolean; error: string; message: string; actionRef?: RefObject<Element | null>; synchronousError?: string }) {
  const errorRef = useRef<HTMLParagraphElement>(null);
  const trigger = useRef<Element | null>(null);
  const wasPending = useRef(false);
  const focusMoved = useRef(false);
  const previousError = useRef("");
  const initialError = useRef("");
  useEffect(() => {
    if (pending && !wasPending.current) {
      trigger.current = actionRef?.current ?? document.activeElement;
      focusMoved.current = false;
      initialError.current = error;
    }
    const newActionError = wasPending.current
      ? error !== initialError.current
      : error === synchronousError && error !== previousError.current;
    if (!pending && error && newActionError) {
      const active = document.activeElement;
      const origin = wasPending.current ? trigger.current : actionRef?.current;
      if (origin && origin !== document.body && (active === origin || (active === document.body && wasPending.current && !focusMoved.current))) {
        errorRef.current?.focus();
      }
    }
    previousError.current = error;
    wasPending.current = pending;
    if (pending) {
      const recordFocus = (event: FocusEvent) => {
        if (event.target !== trigger.current && event.target !== document.body) focusMoved.current = true;
      };
      document.addEventListener("focusin", recordFocus);
      return () => document.removeEventListener("focusin", recordFocus);
    }
  }, [pending, error, actionRef, synchronousError]);
  return <>
    <p role="status" aria-atomic="true" className="async-feedback-status">{message}</p>
    {error ? <p ref={errorRef} role="alert" tabIndex={-1} className="async-feedback-error">{error}</p> : null}
  </>;
}
