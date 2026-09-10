"use client";

import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { currentDiagnosticPage, subscribeDiagnosticPage } from "../lib/diagnostics";

interface Registration<T> {
  owner: symbol;
  pageViewId: string;
  pagePath: string | null;
  snapshot: T | null;
}

function createStore<T>() {
  let current: Registration<T> | null = null;
  const listeners = new Set<() => void>();
  const notify = () => { for (const listener of listeners) listener(); };
  return {
    getSnapshot: () => current,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    claim(pageViewId: string, pagePath: string | null) {
      const owner = Symbol("debug-snapshot-owner");
      current = { owner, pageViewId, pagePath, snapshot: null };
      notify();
      return {
        update(snapshot: T | null) {
          if (current?.owner !== owner || current.snapshot === snapshot) return;
          current = { ...current, snapshot };
          notify();
        },
        dispose() {
          if (current?.owner !== owner) return;
          current = null;
          notify();
        },
      };
    },
  };
}

const emptySnapshot = () => null;
const noSubscribe = () => () => {};

/** New page publishers supersede old owners; stale updates and cleanup are inert. */
export function createOwnedDebugSnapshot<T>() {
  const Context = createContext<ReturnType<typeof createStore<T>> | null>(null);
  function Provider({ children }: { children: ReactNode }) {
    const [store] = useState(createStore<T>);
    return <Context.Provider value={store}>{children}</Context.Provider>;
  }
  function usePublish(snapshot: T | null) {
    const store = useContext(Context);
    const pathname = usePathname();
    const page = useSyncExternalStore(subscribeDiagnosticPage, currentDiagnosticPage, emptySnapshot);
    const handle = useRef<ReturnType<ReturnType<typeof createStore<T>>["claim"]> | null>(null);
    useEffect(() => {
      if (!store || !page?.id || page.path !== pathname) return;
      const registration = store.claim(page.id, page.path);
      handle.current = registration;
      return () => { registration.dispose(); if (handle.current === registration) handle.current = null; };
    }, [store, page, pathname]);
    useEffect(() => { handle.current?.update(snapshot); }, [snapshot, store, page, pathname]);
  }
  function useRegistration() {
    const store = useContext(Context);
    const pathname = usePathname();
    const page = useSyncExternalStore(subscribeDiagnosticPage, currentDiagnosticPage, emptySnapshot);
    const current = useSyncExternalStore(store?.subscribe ?? noSubscribe, store?.getSnapshot ?? emptySnapshot, emptySnapshot);
    return current && current.pageViewId === page?.id && current.pagePath === pathname ? current : null;
  }
  return { Provider, usePublish, useRegistration, useSnapshot: () => useRegistration()?.snapshot ?? null };
}
