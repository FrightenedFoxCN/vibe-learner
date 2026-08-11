export type HarnessStatus = "passed" | "repaired" | "failed" | "skipped";
export type HarnessCheckStatus = "passed" | "failed" | "warning" | "skipped";

export interface HarnessCheck {
  name: string;
  status: HarnessCheckStatus;
  code?: string;
  message?: string;
}

export interface HarnessTrace {
  version: string;
  workflow: string;
  stage: string;
  status: HarnessStatus;
  schemaName: string;
  inputDigest?: string;
  contextDigest?: string;
  checks: HarnessCheck[];
  attempts: number;
  recoveryStrategy: string;
  durationMs: number;
}
