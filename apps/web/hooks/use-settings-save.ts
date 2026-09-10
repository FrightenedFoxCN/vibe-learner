"use client";

import { useEffect, useRef, useState } from "react";
import { SettingsSaveCoordinator, type SaveCoordinatorPort, type SaveScheduler } from "../lib/settings-save-coordinator";

export function useSettingsSave<T>(
  snapshot: T | null,
  enabled: boolean,
  port: SaveCoordinatorPort<T>,
  delay: number,
  scheduler?: SaveScheduler,
) {
  const portRef = useRef(port);
  const mounted = useRef(true);
  useEffect(() => { portRef.current = port; });
  const [coordinator] = useState(() => new SettingsSaveCoordinator<T>({
    serialize: value => portRef.current.serialize(value),
    persist: (value, context) => portRef.current.persist(value, context),
    saved: (value, key) => portRef.current.saved(value, key),
    status: (phase, error) => { if (mounted.current) portRef.current.status(phase, error); },
  }, delay, scheduler));
  useEffect(() => {
    mounted.current = true;
    const flush = () => coordinator.flush();
    window.addEventListener("pagehide", flush);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", flush);
      coordinator.flush();
    };
  }, [coordinator]);
  useEffect(() => {
    if (enabled && snapshot) coordinator.edit(snapshot);
  }, [coordinator, enabled, snapshot]);
  return coordinator;
}
