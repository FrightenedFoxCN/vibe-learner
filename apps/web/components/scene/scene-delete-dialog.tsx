"use client";

import { useEffect, useId, useRef, type RefObject } from "react";
import styles from "./scene-delete-dialog.module.css";

export function SceneDeleteDialog({ layerName, onCancel, onConfirm, fallbackFocus }: {
  layerName: string;
  onCancel: () => void;
  onConfirm: () => void;
  fallbackFocus: RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    cancelRef.current?.focus();
    return () => {
      dialog.close();
      // Confirmation may remove the trigger along with its scene subtree.
      queueMicrotask(() => {
        if (dialog.isConnected && dialog.open) return;
        (trigger?.isConnected ? trigger : fallbackFocus.current)?.focus();
      });
    };
  }, [fallbackFocus]);

  return <dialog
    ref={dialogRef}
    className={styles.dialog}
    aria-labelledby={titleId}
    aria-describedby={descriptionId}
    onCancel={event => { event.preventDefault(); onCancel(); }}
    onKeyDown={event => {
      if (event.key !== "Tab") return;
      if (event.shiftKey && document.activeElement === cancelRef.current) {
        event.preventDefault(); confirmRef.current?.focus();
      } else if (!event.shiftKey && document.activeElement === confirmRef.current) {
        event.preventDefault(); cancelRef.current?.focus();
      }
    }}
  >
    <h2 id={titleId}>确认删除层级？</h2>
    <p id={descriptionId}>即将删除“{layerName}”及其所有子层级与物体。此操作不可自动恢复。</p>
    <div className={styles.actions}>
      <button ref={cancelRef} type="button" onClick={onCancel}>取消</button>
      <button ref={confirmRef} type="button" className={styles.danger} onClick={onConfirm}>确认删除</button>
    </div>
  </dialog>;
}
