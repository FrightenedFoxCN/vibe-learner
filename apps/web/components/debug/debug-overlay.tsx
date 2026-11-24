"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { useRuntimeSettings } from "../layout/runtime-settings-provider";
import {
  BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT,
  DEBUG_OVERLAY_OPEN_STORAGE_KEY,
  readStoredBoolean,
  writeStoredBoolean,
} from "../../lib/view-preferences";
import styles from "./debug-overlay.module.css";

const DebugOverlayBody = dynamic(
  () => import("./debug-overlay-body").then((module) => module.DebugOverlayBody),
  { ssr: false, loading: () => <p role="status">正在加载调试面板…</p> },
);

export function DebugOverlay() {
  const pathname = usePathname();
  const { showDebugInfo, settings } = useRuntimeSettings();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"page" | "global">("page");
  const [pageEvents, setPageEvents] = useState(false);
  const [openPreferenceLoaded, setOpenPreferenceLoaded] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);
  const collapseButtonRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  const [bodyReady, setBodyReady] = useState(false);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const visible = showDebugInfo && open;
  const togglePageEvents = () => setPageEvents((value) => !value);

  const closeOverlay = useCallback(() => {
    setOpen(false);
  }, []);

  const openOverlay = useCallback((trigger: HTMLElement | null = null) => {
    const activeElement = document.activeElement;
    restoreFocusRef.current =
      trigger ?? (activeElement instanceof HTMLElement ? activeElement : null);
    setOpen(true);
  }, []);

  useEffect(() => {
    if (readStoredBoolean(DEBUG_OVERLAY_OPEN_STORAGE_KEY)) {
      openOverlay();
    }
    setOpenPreferenceLoaded(true);
  }, [openOverlay]);

  useEffect(() => {
    if (!openPreferenceLoaded) {
      return;
    }
    writeStoredBoolean(DEBUG_OVERLAY_OPEN_STORAGE_KEY, open);
  }, [open, openPreferenceLoaded]);

  useEffect(() => {
    if (settings && !showDebugInfo) {
      closeOverlay();
    }
  }, [closeOverlay, showDebugInfo, settings]);

  useEffect(() => {
    const handleToggle = () => {
      if (!showDebugInfo) {
        return;
      }
      if (open) {
        closeOverlay();
        return;
      }
      openOverlay();
    };
    window.addEventListener(BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT, handleToggle);
    return () => {
      window.removeEventListener(BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT, handleToggle);
    };
  }, [closeOverlay, open, openOverlay, showDebugInfo]);

  useEffect(() => {
    if (!visible) {
      return;
    }

    const mainElements = Array.from(document.querySelectorAll<HTMLElement>("main"));
    const mainStates = mainElements.map((element) => ({
      element,
      ariaHidden: element.getAttribute("aria-hidden"),
      inertAttribute: element.getAttribute("inert"),
      inertProperty: element.inert,
    }));
    const previousBodyOverflow = document.body.style.overflow;

    for (const mainElement of mainElements) {
      mainElement.inert = true;
      mainElement.setAttribute("inert", "");
      mainElement.setAttribute("aria-hidden", "true");
    }
    document.body.style.overflow = "hidden";
    collapseButtonRef.current?.focus({ preventScroll: true });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeOverlay();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusableElements = getFocusableElements(dialog);
      const firstFocusable = focusableElements[0] ?? dialog;
      const lastFocusable = focusableElements[focusableElements.length - 1] ?? dialog;
      const activeElement = document.activeElement;

      if (!dialog.contains(activeElement)) {
        event.preventDefault();
        (event.shiftKey ? lastFocusable : firstFocusable).focus({
          preventScroll: true,
        });
        return;
      }
      if (event.shiftKey && activeElement === firstFocusable) {
        event.preventDefault();
        lastFocusable.focus({ preventScroll: true });
        return;
      }
      if (!event.shiftKey && activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus({ preventScroll: true });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousBodyOverflow;
      for (const { element, ariaHidden, inertAttribute, inertProperty } of mainStates) {
        restoreAttribute(element, "aria-hidden", ariaHidden);
        element.inert = inertProperty;
        restoreAttribute(element, "inert", inertAttribute);
      }

      const restoreTarget = restoreFocusRef.current;
      if (restoreTarget?.isConnected) {
        restoreTarget.focus({ preventScroll: true });
      }
    };
  }, [closeOverlay, visible]);

  const title = useMemo(
    () => (view === "global" ? "全局诊断浮窗" : getDebugTitle(pathname)),
    [pathname, view],
  );

  return (
    <>
      {visible ? (
        <button
          type="button"
          className={styles.scrim}
          onClick={closeOverlay}
          aria-label="关闭调试浮窗背景遮罩"
          tabIndex={-1}
        />
      ) : null}

      <div
        className={styles.root}
        data-open={visible ? "true" : "false"}
        hidden={!showDebugInfo}
      >
        <button
          type="button"
          className={styles.fab}
          onClick={(event) => openOverlay(event.currentTarget)}
          aria-hidden={open ? "true" : undefined}
          tabIndex={open ? -1 : undefined}
        >
          <span className={styles.fabLabel}>Debug</span>
          <span className={styles.fabMeta}>{getFabMeta(pathname)}</span>
        </button>

        {visible || bodyReady ? (
          <section
            ref={dialogRef}
            hidden={!visible}
            className={styles.overlay}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
          >
            <header className={styles.overlayHeader}>
              <div className={styles.headerCopy}>
                <span id={titleId} className={styles.title}>
                  {title}
                </span>
              </div>
              <div className={styles.headerActions}>
                {pathname === "/plan" ? (
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    disabled={!bodyReady}
                    onClick={() => setRefreshRevision((value) => value + 1)}
                  >
                    刷新
                  </button>
                ) : null}
                <button
                  ref={collapseButtonRef}
                  type="button"
                  className={styles.primaryButton}
                  onClick={closeOverlay}
                >
                  收起
                </button>
              </div>
            </header>

            <nav aria-label="Debug 视图" className={styles.viewSelector}>
              <button
                className={styles.viewButton}
                aria-pressed={view === "page"}
                onClick={() => setView("page")}
              >
                当前页面
              </button>
              <button
                className={styles.viewButton}
                aria-pressed={view === "global"}
                onClick={() => setView("global")}
              >
                全局诊断
              </button>
            </nav>
            <div className={styles.overlayBody}>
              <DebugOverlayBody
                open={visible}
                pathname={pathname}
                view={view}
                pageEvents={pageEvents}
                onTogglePageEvents={togglePageEvents}
                refreshRevision={refreshRevision}
                onReady={setBodyReady}
              />
            </div>
          </section>
        ) : null}
      </div>
    </>
  );
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
  "audio[controls]",
  "video[controls]",
  "summary",
].join(",");

function getFocusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.tabIndex >= 0 &&
      element.getAttribute("aria-hidden") !== "true" &&
      !element.closest('[hidden], [inert], [aria-hidden="true"]') &&
      element.getClientRects().length > 0,
  );
}

function restoreAttribute(element: HTMLElement, name: string, value: string | null) {
  if (value === null) {
    element.removeAttribute(name);
    return;
  }
  element.setAttribute(name, value);
}

function getDebugTitle(pathname: string) {
  if (pathname === "/plan") {
    return "计划调试浮窗";
  }
  if (pathname === "/study") {
    return "章节对话调试浮窗";
  }
  if (pathname === "/settings") {
    return "设置调试浮窗";
  }
  if (pathname === "/model-usage") {
    return "用量审计调试浮窗";
  }
  if (pathname === "/persona-spectrum") {
    return "人格页调试浮窗";
  }
  if (pathname === "/scene-setup") {
    return "场景页调试浮窗";
  }
  if (pathname === "/sensory-tools") {
    return "感官工具调试浮窗";
  }
  return "调试浮窗";
}

function getFabMeta(pathname: string) {
  if (pathname === "/plan") {
    return "计划页";
  }
  if (pathname === "/study") {
    return "对话页";
  }
  if (pathname === "/settings") {
    return "设置页";
  }
  if (pathname === "/model-usage") {
    return "审计页";
  }
  if (pathname === "/persona-spectrum") {
    return "人格页";
  }
  if (pathname === "/scene-setup") {
    return "场景页";
  }
  if (pathname === "/sensory-tools") {
    return "工具页";
  }
  return "页面";
}
