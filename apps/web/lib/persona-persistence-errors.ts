import { isApiHttpError } from "./http-error";

export function humanizePersonaDeleteError(error: unknown): string {
  const raw = String(error).replace(/^Error:\s*/, "");
  if (raw.includes("persona_readonly_builtin")) {
    return "内置人格不能删除。";
  }
  if (!raw.includes("persona_in_use")) {
    return raw;
  }

  const countSpecs = [
    { key: "plans", label: "学习计划" },
    { key: "sessions", label: "学习会话" },
    { key: "scene_instances", label: "场景实例" },
    { key: "tavern_rooms", label: "酒馆房间" },
  ];
  const parts = countSpecs.flatMap(({ key, label }) => {
    const match = raw.match(new RegExp(`${key}=(\\d+)`));
    const count = Number(match?.[1] ?? 0);
    if (!count) {
      return [];
    }
    return [`${label} ${count} 条`];
  });
  return parts.length
    ? `该人格仍被${parts.join("、")}引用，暂时不能删除。`
    : "该人格仍被现有数据引用，暂时不能删除。";
}

export function humanizePersonaSaveError(error: unknown): string {
  if (isApiHttpError(error) && error.code === "persona_revision_conflict") {
    return "人格已在其他窗口更新。当前草稿已保留，请重新载入最新人格后再合并保存。";
  }
  if (isApiHttpError(error) && error.status === 422) {
    return "人格内容未通过校验，请检查名称、插槽权重和排序。";
  }
  return String(error).replace(/^Error:\s*/, "");
}

