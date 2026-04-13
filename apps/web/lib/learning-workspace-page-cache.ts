"use client";

export type StudyDialogPreviewState =
  | {
      kind: "document";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
    }
  | {
      kind: "attachment_pdf";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
    }
  | {
      kind: "attachment_image";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
      imageUrl?: string;
    }
  | {
      kind: "generated_image";
      sourceId: string;
      title: string;
      page: number;
      pageCount: number;
      imageUrl: string;
    };

export interface PlanSetupPageCache {
  generationMode: "document" | "goal_only";
  objective: string;
  file: File | null;
}

export interface StudyDialogPageCache {
  pdfPage: number;
  isPdfPreviewOpen: boolean;
  previewState: StudyDialogPreviewState | null;
  selectedScheduleId: string;
  selectedScheduleChapterId: string;
}

export interface StudyConsolePageCache {
  message: string;
  attachments: File[];
  selectedChoices: Record<string, string>;
  blankAnswers: Record<string, string>;
  questionFeedback: Record<string, { ok: boolean; text: string }>;
  expandedExplanation: Record<string, boolean>;
}

export interface LearningWorkspacePageCache {
  planSetup?: PlanSetupPageCache;
  studyDialog?: StudyDialogPageCache;
  studyConsole?: StudyConsolePageCache;
}

const STORAGE_KEY = "vibe-learner:learning-workspace-page-cache:v1";

type SerializableLearningWorkspacePageCache = {
  planSetup?: Omit<PlanSetupPageCache, "file">;
  studyDialog?: StudyDialogPageCache & {
    selectedChapter?: string;
    selectedSubsectionId?: string;
  };
  studyConsole?: Omit<StudyConsolePageCache, "attachments">;
};

export function loadLearningWorkspacePageCache(): LearningWorkspacePageCache {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return {};
  }
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw) as SerializableLearningWorkspacePageCache | null;
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return {
      planSetup: parsed.planSetup
        ? {
            generationMode: parsed.planSetup.generationMode === "goal_only" ? "goal_only" : "document",
            objective: String(parsed.planSetup.objective ?? ""),
            file: null,
          }
        : undefined,
      studyDialog: parsed.studyDialog
        ? {
            pdfPage: Number(parsed.studyDialog.pdfPage ?? 1),
            isPdfPreviewOpen: Boolean(parsed.studyDialog.isPdfPreviewOpen),
            previewState: normalizePreviewState(parsed.studyDialog.previewState),
            selectedScheduleId: String(parsed.studyDialog.selectedScheduleId ?? parsed.studyDialog.selectedChapter ?? ""),
            selectedScheduleChapterId: String(
              parsed.studyDialog.selectedScheduleChapterId ?? parsed.studyDialog.selectedSubsectionId ?? ""
            ),
          }
        : undefined,
      studyConsole: parsed.studyConsole
        ? {
            message: String(parsed.studyConsole.message ?? ""),
            attachments: [],
            selectedChoices: normalizeStringRecord(parsed.studyConsole.selectedChoices),
            blankAnswers: normalizeStringRecord(parsed.studyConsole.blankAnswers),
            questionFeedback: normalizeQuestionFeedback(parsed.studyConsole.questionFeedback),
            expandedExplanation: normalizeBooleanRecord(parsed.studyConsole.expandedExplanation),
          }
        : undefined,
    };
  } catch {
    return {};
  }
}

export function persistLearningWorkspacePageCache(
  cache: LearningWorkspacePageCache
): void {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return;
  }
  const serializable: SerializableLearningWorkspacePageCache = {};
  if (cache.planSetup) {
    serializable.planSetup = {
      generationMode: cache.planSetup.generationMode,
      objective: cache.planSetup.objective,
    };
  }
  if (cache.studyDialog) {
    serializable.studyDialog = {
      pdfPage: cache.studyDialog.pdfPage,
      isPdfPreviewOpen: cache.studyDialog.isPdfPreviewOpen,
      previewState: cache.studyDialog.previewState,
      selectedScheduleId: cache.studyDialog.selectedScheduleId,
      selectedScheduleChapterId: cache.studyDialog.selectedScheduleChapterId,
    };
  }
  if (cache.studyConsole) {
    serializable.studyConsole = {
      message: cache.studyConsole.message,
      selectedChoices: cache.studyConsole.selectedChoices,
      blankAnswers: cache.studyConsole.blankAnswers,
      questionFeedback: cache.studyConsole.questionFeedback,
      expandedExplanation: cache.studyConsole.expandedExplanation,
    };
  }
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(serializable));
}

function normalizePreviewState(value: unknown): StudyDialogPreviewState | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const sourceId = String(raw.sourceId ?? "");
  const title = String(raw.title ?? "");
  const page = Number(raw.page ?? 1);
  const pageCount = Number(raw.pageCount ?? 0);

  if (raw.kind === "attachment_pdf") {
    return {
      kind: "attachment_pdf",
      sourceId,
      title,
      page,
      pageCount,
    };
  }
  if (raw.kind === "attachment_image") {
    return {
      kind: "attachment_image",
      sourceId,
      title,
      page,
      pageCount,
      imageUrl: String(raw.imageUrl ?? ""),
    };
  }
  if (raw.kind === "generated_image") {
    return {
      kind: "generated_image",
      sourceId,
      title,
      page,
      pageCount,
      imageUrl: String(raw.imageUrl ?? ""),
    };
  }
  return {
    kind: "document",
    sourceId,
    title,
    page,
    pageCount,
  };
}

function normalizeStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, String(entry ?? "")])
  );
}

function normalizeBooleanRecord(value: unknown): Record<string, boolean> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, Boolean(entry)])
  );
}

function normalizeQuestionFeedback(
  value: unknown
): Record<string, { ok: boolean; text: string }> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, entry]) => {
      const raw = entry && typeof entry === "object" ? (entry as Record<string, unknown>) : {};
      return [
        key,
        {
          ok: Boolean(raw.ok),
          text: String(raw.text ?? ""),
        },
      ];
    })
  );
}
