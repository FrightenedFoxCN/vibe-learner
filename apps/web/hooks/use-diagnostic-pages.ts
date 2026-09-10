"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export function useDiagnosticPages<T, C extends string | number, P extends { items: T[]; next_cursor: C }>(
  query: (after: C, signal: AbortSignal) => Promise<P>, initial: C, identity: (row: T) => string, capacity = 500,
) {
  const [state, setState] = useState<{ items: T[]; page: P | null; loading: boolean; error: boolean }>({ items: [], page: null, loading: true, error: false });
  const epoch = useRef(0);
  const active = useRef<AbortController | null>(null);
  const load = useCallback(async (after: C, append: boolean) => {
    const generation = ++epoch.current;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setState(old => ({ items: append ? old.items : [], page: append ? old.page : null, loading: true, error: false }));
    try {
      const page = await query(after, controller.signal);
      if (generation !== epoch.current || controller.signal.aborted) return;
      setState(old => {
        const previous = append ? old.items : [];
        const ids = new Set(previous.map(identity));
        if (page.items.some(item => ids.has(identity(item))) || previous.length + page.items.length > capacity) {
          return { ...old, loading: false, error: true };
        }
        return { items: [...previous, ...page.items], page, loading: false, error: false };
      });
    } catch {
      if (generation === epoch.current && !controller.signal.aborted) setState(old => ({ ...old, loading: false, error: true }));
    }
  }, [query, identity, capacity]);
  useEffect(() => {
    void load(initial, false);
    return () => { ++epoch.current; active.current?.abort(); };
  }, [load, initial]);
  return { ...state, refresh: () => void load(initial, false), more: () => { if (state.page && !state.loading) void load(state.page.next_cursor, true); }, atCapacity: state.items.length >= capacity };
}
