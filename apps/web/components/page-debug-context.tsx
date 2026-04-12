"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export interface PageDebugSummaryItem {
  label: string;
  value: string;
}

export interface PageDebugDetailItem {
  title: string;
  value: unknown;
}

export interface PageDebugSnapshot {
  title: string;
  subtitle?: string;
  error?: string;
  summary?: PageDebugSummaryItem[];
  details?: PageDebugDetailItem[];
}

interface PageDebugContextValue {
  snapshot: PageDebugSnapshot | null;
  setSnapshot: (snapshot: PageDebugSnapshot | null) => void;
}

const PageDebugContext = createContext<PageDebugContextValue | null>(null);

export function PageDebugProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<PageDebugSnapshot | null>(null);
  const value = useMemo(
    () => ({ snapshot, setSnapshot }),
    [snapshot]
  );

  return <PageDebugContext.Provider value={value}>{children}</PageDebugContext.Provider>;
}

export function usePageDebugSnapshot(snapshot: PageDebugSnapshot | null) {
  const context = useContext(PageDebugContext);
  useEffect(() => {
    if (!context) {
      return;
    }
    context.setSnapshot(snapshot);
    return () => {
      context.setSnapshot(null);
    };
  }, [context, snapshot]);
}

export function useCurrentPageDebugSnapshot() {
  const context = useContext(PageDebugContext);
  return context?.snapshot ?? null;
}