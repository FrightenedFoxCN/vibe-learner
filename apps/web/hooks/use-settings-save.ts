"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { SettingsWriteHandoff } from "../lib/settings-write-handoff";
import {
  SettingsSaveCoordinator,
  type SaveCoordinatorPort,
  type SaveScheduler,
} from "../lib/settings-save-coordinator";

export function useSettingsSave<T>(
  port: SaveCoordinatorPort<T>,
  delay: number,
  handoff: SettingsWriteHandoff,
  scheduler?: SaveScheduler,
) {
  const portRef = useRef(port);
  const mounted = useRef(true);
  useLayoutEffect(() => {
    portRef.current = port;
  });
  const [coordinator] = useState(
    () =>
      new SettingsSaveCoordinator<T>(
        {
          serialize: (value) => portRef.current.serialize(value),
          persist: (value, context) => portRef.current.persist(value, context),
          saved: (value, key) => portRef.current.saved(value, key),
          status: (phase, error) => {
            if (mounted.current) portRef.current.status(phase, error);
          },
        },
        delay,
        scheduler,
      ),
  );
  // Register the drain in layout cleanup so a replacement editor cannot
  // initialize before the outgoing route hands off its write.
  useLayoutEffect(() => {
    mounted.current = true;
    const flush = () => {
      void coordinator.flush();
    };
    window.addEventListener("pagehide", flush);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", flush);
      const completion = coordinator.flush();
      if (completion) handoff.track(completion);
    };
  }, [coordinator, handoff]);
  return coordinator;
}
