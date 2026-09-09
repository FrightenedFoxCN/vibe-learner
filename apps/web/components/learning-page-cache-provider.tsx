"use client";

import { createContext, useCallback, useContext, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { loadLearningWorkspacePageCache, persistLearningWorkspacePageCache } from "../lib/learning-workspace-page-cache";
import type { LearningWorkspacePageCache } from "../lib/learning-workspace-page-cache";

type PageCacheAccess = {
  getPageCache: <K extends keyof LearningWorkspacePageCache>(key: K) => LearningWorkspacePageCache[K] | undefined;
  setPageCache: <K extends keyof LearningWorkspacePageCache>(key: K, value: LearningWorkspacePageCache[K]) => void;
};
const PageCacheContext = createContext<PageCacheAccess | null>(null);

// Root-owned drafts survive route changes, including File objects that cannot be
// serialized. This provider never starts learning requests, timers, or operations.
export function LearningPageCacheProvider({ children }: { children: ReactNode }) {
  const cache = useRef<LearningWorkspacePageCache | null>(null);
  if (cache.current === null) cache.current = loadLearningWorkspacePageCache();
  const getPageCache = useCallback(<K extends keyof LearningWorkspacePageCache>(key: K) => cache.current?.[key], []);
  const setPageCache = useCallback(<K extends keyof LearningWorkspacePageCache>(key: K, value: LearningWorkspacePageCache[K]) => {
    cache.current = { ...cache.current, [key]: value };
    persistLearningWorkspacePageCache(cache.current);
  }, []);
  const value = useMemo(() => ({ getPageCache, setPageCache }), [getPageCache, setPageCache]);
  return <PageCacheContext.Provider value={value}>{children}</PageCacheContext.Provider>;
}

export function useLearningPageCache() {
  const value = useContext(PageCacheContext);
  if (!value) throw new Error("useLearningPageCache must be used within LearningPageCacheProvider");
  return value;
}
