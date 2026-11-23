"use client";

import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ConfirmDialog, type ConfirmOptions } from "./confirm-dialog";

export type { ConfirmOptions } from "./confirm-dialog";
export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

type ConfirmationRequest = {
  id: number;
  owner: symbol;
  options: ConfirmOptions;
  resolve: (confirmed: boolean) => void;
};

type ConfirmationService = {
  request: (owner: symbol, options: ConfirmOptions) => Promise<boolean>;
  cancel: (owner: symbol) => void;
};

const ConfirmationContext = createContext<ConfirmationService | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const sequence = useRef(0);
  const active = useRef<ConfirmationRequest | null>(null);
  const [shown, setShown] = useState<ConfirmationRequest | null>(null);

  const settle = useCallback((id: number, confirmed: boolean) => {
    const request = active.current;
    if (!request || request.id !== id) return;
    active.current = null;
    setShown(null);
    request.resolve(confirmed);
  }, []);

  const service = useMemo<ConfirmationService>(
    () => ({
      request(owner, options) {
        // Do not queue stale destructive intents behind an open modal.
        if (active.current) return Promise.resolve(false);
        return new Promise((resolve) => {
          const request = { id: ++sequence.current, owner, options, resolve };
          active.current = request;
          setShown(request);
        });
      },
      cancel(owner) {
        const request = active.current;
        if (request?.owner === owner) settle(request.id, false);
      },
    }),
    [settle],
  );

  useLayoutEffect(
    () => () => {
      const request = active.current;
      active.current = null;
      request?.resolve(false);
    },
    [],
  );

  return (
    <ConfirmationContext.Provider value={service}>
      {children}
      {shown && (
        <ConfirmDialog
          key={shown.id}
          {...shown.options}
          onDecision={(confirmed) => settle(shown.id, confirmed)}
        />
      )}
    </ConfirmationContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const service = useContext(ConfirmationContext);
  if (!service) throw new Error("useConfirm requires ConfirmProvider");
  const owner = useRef(Symbol("confirmation owner"));
  const mounted = useRef(false);

  useLayoutEffect(() => {
    const id = owner.current;
    mounted.current = true;
    return () => {
      mounted.current = false;
      service.cancel(id);
    };
  }, [service]);

  return useCallback(
    async (options) => {
      if (!mounted.current) return false;
      const confirmed = await service.request(owner.current, options);
      return confirmed && mounted.current;
    },
    [service],
  );
}
