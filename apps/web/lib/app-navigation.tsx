"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useLayoutEffect, type AnchorHTMLAttributes, type MouseEvent } from "react";
import { useConfirm, type ConfirmFn } from "../components/ui/confirm-provider";
import { classifyAppLink } from "./navigation-intent";

import { isDesktopVaultCreationRequired } from "./desktop-vault";
import { getDesktopRuntimeConfig } from "./runtime-config";

const appRoutes = [
  "/",
  "/manual",
  "/plan",
  "/study",
  "/tavern",
  "/persona-spectrum",
  "/scene-setup",
  "/sensory-tools",
  "/settings",
  "/model-usage",
] as const;
export type AppRoutePath = (typeof appRoutes)[number];

export const ACTIVE_PLAN_GENERATION_KEY = "vibe-learner:active-plan-generation:v1";

type NavigationWarning = { message: string; isCurrent: () => boolean };
type ReadDraftWarning = () => NavigationWarning;
const draftWarnings = new Set<ReadDraftWarning>();
let navigationPending = false;

function readGenerationMarker() {
  try {
    return window.localStorage.getItem(ACTIVE_PLAN_GENERATION_KEY);
  } catch {
    return null;
  }
}

async function resumeGuardedLink(
  path: AppRoutePath,
  trigger: HTMLAnchorElement,
  confirm: ConfirmFn,
  resume: () => void,
) {
  if (navigationPending) return;
  const source = window.location.href;
  const warnings = [...draftWarnings].map((read) => ({ read, warning: read() }));
  const generation = readGenerationMarker();
  const messages = warnings.map(({ warning }) => warning.message);
  if (generation)
    messages.push(
      "当前计划仍在生成。离开此页会中断任务；已发生的 Token/费用不会撤销，实际费用以服务商账单为准。",
    );
  if (!messages.length) {
    resume();
    return;
  }
  navigationPending = true;
  try {
    const priorFocus = document.activeElement;
    const approved = await confirm({
      title: "离开当前页面？",
      message: messages.join(" "),
      confirmLabel: "离开",
      danger: true,
      trigger,
      fallbackFocus: () => (priorFocus instanceof HTMLElement ? priorFocus : null),
    });
    if (
      !approved ||
      window.location.href !== source ||
      resolveDesktopVaultNavigation(path) !== path
    )
      return;
    const latestGeneration = readGenerationMarker();
    if (
      (latestGeneration && latestGeneration !== generation) ||
      draftWarnings.size !== warnings.length ||
      warnings.some(
        ({ read, warning }) => !draftWarnings.has(read) || !warning.isCurrent(),
      )
    )
      return;
    resume();
  } finally {
    navigationPending = false;
  }
}

/** AppLink owns its React handler; capture any plain links to known app routes. */
export function useDraftNavigationGuard(
  warning: ReadDraftWarning | null,
  confirm: ConfirmFn,
) {
  const router = useRouter();
  useLayoutEffect(() => {
    if (!warning) return;
    draftWarnings.add(warning);
    const handleClick = (event: globalThis.MouseEvent) => {
      const anchor =
        event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (
        !(anchor instanceof HTMLAnchorElement) ||
        anchor.hasAttribute("data-app-link")
      )
        return;
      const intent = classifyAppLink(event, anchor, window.location.href);
      if (!intent || intent.samePage || !appRoutes.some((path) => path === intent.path))
        return;
      event.preventDefault();
      const path = intent.path as AppRoutePath;
      if (resolveDesktopVaultNavigation(path) !== path) return;
      const href = normalizeAppPath(path, isDesktopNavigationMode()) + intent.suffix;
      void resumeGuardedLink(path, anchor, confirm, () => router.push(href as Route));
    };
    document.addEventListener("click", handleClick, true);
    return () => {
      document.removeEventListener("click", handleClick, true);
      draftWarnings.delete(warning);
    };
  }, [warning, confirm, router]);
}

type AppRouteQueryValue = string | number | boolean | null | undefined;

export type AppRouteQuery = Record<string, AppRouteQueryValue>;

export function buildAppHref(
  path: AppRoutePath,
  query?: AppRouteQuery,
  options?: { desktopSafe?: boolean },
): string {
  const normalizedPath = normalizeAppPath(path, Boolean(options?.desktopSafe));
  const params = new URLSearchParams();

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    params.set(key, String(value));
  });

  const queryText = params.toString();
  if (!queryText) {
    return normalizedPath;
  }
  return `${normalizedPath}?${queryText}`;
}

export function useAppNavigator() {
  const router = useRouter();

  const navigate = (
    path: AppRoutePath,
    query?: AppRouteQuery,
    options?: { replace?: boolean },
  ) => {
    const allowedPath = resolveDesktopVaultNavigation(path);
    const desktopSafe = isDesktopNavigationMode();
    const href = buildAppHref(allowedPath, allowedPath === path ? query : undefined, {
      desktopSafe,
    });
    if (options?.replace) {
      router.replace(href as Route);
    } else {
      router.push(href as Route);
    }
  };

  return {
    href: (path: AppRoutePath, query?: AppRouteQuery) => {
      const allowedPath = resolveDesktopVaultNavigation(path);
      return buildAppHref(allowedPath, allowedPath === path ? query : undefined, {
        desktopSafe: isDesktopNavigationMode(),
      });
    },
    push: (path: AppRoutePath, query?: AppRouteQuery) => navigate(path, query),
    replace: (path: AppRoutePath, query?: AppRouteQuery) =>
      navigate(path, query, { replace: true }),
  };
}

interface AppLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  path: AppRoutePath;
  query?: AppRouteQuery;
  replace?: boolean;
}

export function AppLink({
  path,
  query,
  replace = false,
  onClick,
  target,
  download,
  ...props
}: AppLinkProps) {
  const router = useRouter();
  const confirm = useConfirm();
  const desktopSafe = isDesktopNavigationMode();
  const vaultCreationRequired = isDesktopVaultCreationRequired();
  const href = buildAppHref(path, query, { desktopSafe });

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (vaultCreationRequired && path !== "/settings") {
      event.preventDefault();
      return;
    }
    const trigger = event.currentTarget;
    const intent = classifyAppLink(event, trigger, window.location.href);
    if (!intent) return;
    event.preventDefault();
    if (intent.samePage) return;
    void resumeGuardedLink(path, trigger, confirm, () => {
      if (replace) router.replace(href as Route);
      else router.push(href as Route);
    });
  };

  return (
    <a
      {...props}
      href={href}
      data-app-link=""
      target={target}
      download={download}
      onClick={handleClick}
    />
  );
}

function normalizeAppPath(path: AppRoutePath, desktopSafe: boolean): string {
  if (path === "/") {
    return "/";
  }
  const trimmed = path.replace(/\/+$/, "");
  return desktopSafe ? `${trimmed}/` : trimmed;
}

function isDesktopNavigationMode(): boolean {
  return Boolean(getDesktopRuntimeConfig()?.isDesktop);
}

function resolveDesktopVaultNavigation(path: AppRoutePath): AppRoutePath {
  if (path !== "/settings" && isDesktopVaultCreationRequired()) {
    return "/settings";
  }
  return path;
}
