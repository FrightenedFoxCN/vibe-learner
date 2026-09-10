"use client";

import { createOwnedDebugSnapshot } from "./owned-debug-snapshot";

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

const page = createOwnedDebugSnapshot<PageDebugSnapshot>();
export const PageDebugProvider = page.Provider;
export const usePageDebugSnapshot = page.usePublish;
export const useCurrentPageDebugSnapshot = page.useSnapshot;
export const useCurrentPageDebugRegistration = page.useRegistration;
