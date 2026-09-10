import type { DocumentRecord, DocumentSection, LearningPlan, SceneProfile } from "@vibe-learner/shared";
import type { SceneLibraryItemPayload } from "./data/scenes";
import type { useRuntimeSettings } from "../components/runtime-settings-provider";
import type { getDesktopRuntimeConfig } from "./runtime-config";

export function resolvePlanGenerationBlockedReason(input: {
  runtimeSettings: ReturnType<typeof useRuntimeSettings>["settings"];
  runtimeSettingsLoading: boolean;
  desktopRuntimeConfig: ReturnType<typeof getDesktopRuntimeConfig>;
}) {
  if (input.runtimeSettingsLoading) {
    return "";
  }
  const settings = input.runtimeSettings;
  if (!settings || settings.planProvider !== "litellm") {
    return "";
  }
  if (settings.openaiPlanApiKeyConfigured || settings.openaiApiKeyConfigured) {
    return "";
  }
  if (input.desktopRuntimeConfig?.isDesktop) {
    return input.desktopRuntimeConfig.vaultState !== "unlocked"
      ? "当前计划提供器设为 LiteLLM，但桌面 Vault 尚未解锁；继续会静默回退到 mock。先去统一设置解锁 Vault。"
      : "当前计划提供器设为 LiteLLM，但还没有可用的计划模型密钥。先去统一设置补齐连接信息。";
  }
  return "当前计划提供器设为 LiteLLM，但还没有可用的计划模型密钥。先去统一设置补齐连接信息。";
}

export function resolveSceneProfileFromLibrary(
  items: SceneLibraryItemPayload[],
  selectedSceneLibraryId: string
): SceneProfile | undefined {
  if (!selectedSceneLibraryId) {
    return undefined;
  }
  const selectedItem = items.find((item) => item.sceneId === selectedSceneLibraryId);
  if (!selectedItem) {
    return undefined;
  }
  if (selectedItem.sceneProfile) {
    return selectedItem.sceneProfile;
  }
  return {
    sceneName: selectedItem.sceneName,
    sceneId: selectedItem.selectedLayerId || selectedItem.sceneId,
    title: selectedItem.sceneName || "未命名场景",
    summary: selectedItem.sceneSummary || "",
    tags: [],
    selectedPath: [],
    focusObjectNames: [],
    sceneTree: [],
  };
}

export function buildPlanDirectorySections(
  plan: LearningPlan | null,
  document: DocumentRecord | null
): DocumentSection[] {
  if (!plan) {
    return [];
  }

  const studyUnitById = new Map(
    (document?.studyUnits ?? plan.studyUnits).map((unit) => [unit.id, unit])
  );
  const sections: DocumentSection[] = [];

  for (const item of plan.schedule) {
    const unit = studyUnitById.get(item.unitId);
    if (!unit) {
      continue;
    }
    sections.push({
      id: unit.id,
      documentId: unit.documentId,
      title: item.title || unit.title,
      pageStart: unit.pageStart,
      pageEnd: unit.pageEnd,
      level: 1
    });
  }

  if (!sections.length) {
    const baseSections = document?.sections.length
      ? document.sections
      : plan.studyUnits
          .filter((unit) => unit.includeInPlan)
          .map((unit) => ({
            id: unit.id,
            documentId: unit.documentId,
            title: unit.title,
            pageStart: unit.pageStart,
            pageEnd: unit.pageEnd,
            level: 1 as const,
          }));
    return baseSections;
  }

  return sections.filter(
    (section, index) => sections.findIndex((candidate) => candidate.id === section.id) === index
  );
}

export function resolveStudyUnitTitle(studyUnitId: string, planSections: DocumentSection[], activeDocument: DocumentRecord | null) {
  const sectionFromPlan = planSections.find((section) => section.id === studyUnitId);
  if (sectionFromPlan?.title) {
    return sectionFromPlan.title;
  }
  const sectionFromDocument = activeDocument?.sections.find((section) => section.id === studyUnitId);
  if (sectionFromDocument?.title) {
    return sectionFromDocument.title;
  }
  return studyUnitId;
}

export function resolveThemeHintByStudyUnitId(studyUnitId: string, activePlan: LearningPlan | null, activeDocument: DocumentRecord | null) {
  if (!activePlan) {
    return "";
  }
  const studyUnitProgress = activePlan.studyUnitProgress.find((item) => item.unitId === studyUnitId);
  if (studyUnitProgress?.objectiveFragment?.trim()) {
    return studyUnitProgress.objectiveFragment.trim();
  }
  const scheduleItem = activePlan.schedule.find((item) => item.unitId === studyUnitId);
  if (scheduleItem?.focus) {
    return scheduleItem.focus;
  }
  const containingUnit = activePlan.studyUnits.find((unit) =>
    unit.id === studyUnitId ||
    unit.sourceSectionIds.includes(studyUnitId) ||
    (
      activeDocument?.sections.some((section) =>
        section.id === studyUnitId &&
        Math.max(unit.pageStart, section.pageStart) <= Math.min(unit.pageEnd, section.pageEnd)
      ) ?? false
    )
  );
  if (containingUnit) {
    const containingSchedule = activePlan.schedule.find((item) => item.unitId === containingUnit.id);
    if (containingSchedule?.focus) {
      return containingSchedule.focus;
    }
    const containingChapter = containingSchedule?.scheduleChapters.find((chapter) => chapter.title.trim());
    if (containingChapter?.title) {
      return containingChapter.title;
    }
  }
  return activePlan.schedule[0]?.scheduleChapters[0]?.title ?? activePlan.objective;
}
