"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import type { AnchorHTMLAttributes, MouseEvent } from "react";

import { getDesktopRuntimeConfig } from "./runtime-config";

export type AppRoutePath =
  | "/"
  | "/plan"
  | "/study"
  | "/persona-spectrum"
  | "/scene-setup"
  | "/sensory-tools"
  | "/settings"
  | "/model-usage";

type AppRouteQueryValue = string | number | boolean | null | undefined;

export type AppRouteQuery = Record<string, AppRouteQueryValue>;

export function buildAppHref(
  path: AppRoutePath,
  query?: AppRouteQuery,
  options?: { desktopSafe?: boolean }
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
    options?: { replace?: boolean }
  ) => {
    const desktopSafe = isDesktopNavigationMode();
    const href = buildAppHref(path, query, { desktopSafe });
    if (desktopSafe) {
      if (typeof window !== "undefined") {
        if (options?.replace) {
          window.location.replace(href);
        } else {
          window.location.assign(href);
        }
      }
      return;
    }

    const browserHref = buildAppHref(path, query);
    if (options?.replace) {
      router.replace(browserHref as Route);
    } else {
      router.push(browserHref as Route);
    }
  };

  return {
    href: (path: AppRoutePath, query?: AppRouteQuery) =>
      buildAppHref(path, query, { desktopSafe: isDesktopNavigationMode() }),
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
  const desktopSafe = isDesktopNavigationMode();
  const href = buildAppHref(path, query, { desktopSafe });
  const browserHref = buildAppHref(path, query);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented || desktopSafe) {
      return;
    }
    if (!shouldHandleClientNavigation(event, target, download)) {
      return;
    }
    event.preventDefault();
    if (replace) {
      router.replace(browserHref as Route);
    } else {
      router.push(browserHref as Route);
    }
  };

  return (
    <a
      {...props}
      href={href}
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

function shouldHandleClientNavigation(
  event: MouseEvent<HTMLAnchorElement>,
  target?: string,
  download?: AnchorHTMLAttributes<HTMLAnchorElement>["download"]
): boolean {
  if (download) {
    return false;
  }
  if (target && target !== "_self") {
    return false;
  }
  if (event.button !== 0) {
    return false;
  }
  return !(event.metaKey || event.altKey || event.ctrlKey || event.shiftKey);
}
