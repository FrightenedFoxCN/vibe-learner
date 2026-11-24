"use client";

import { useSyncExternalStore } from "react";
import {
  getDesktopVaultState,
  getServerDesktopVaultState,
  subscribeDesktopVaultState,
} from "../lib/desktop-vault";

export function useDesktopVaultState() {
  return useSyncExternalStore(
    subscribeDesktopVaultState,
    getDesktopVaultState,
    getServerDesktopVaultState,
  );
}
