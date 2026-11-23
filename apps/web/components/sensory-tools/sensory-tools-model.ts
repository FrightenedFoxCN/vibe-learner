import type {
  ModelToolConfig,
  ModelToolConfigItem,
  ModelToolStageConfig,
  ModelToolToggle,
} from "@vibe-learner/shared";

export function toolKey(stageName: string, toolName: string) {
  return `${stageName}:${toolName}`;
}

export function countEnabledAvailable(tools: ModelToolConfigItem[]) {
  return tools.filter((tool) => tool.enabled && tool.available).length;
}

export function buildBatchToggles(
  stageName: string,
  tools: ModelToolConfigItem[],
  enabled: boolean,
): ModelToolToggle[] {
  return tools
    .filter((tool) => tool.available && tool.enabled !== enabled)
    .map((tool) => ({ stageName, toolName: tool.name, enabled }));
}

export function applyToggles(
  config: ModelToolConfig,
  toggles: ModelToolToggle[],
): ModelToolConfig {
  const table = new Map(
    toggles.map(
      (toggle) => [toolKey(toggle.stageName, toggle.toolName), toggle.enabled] as const,
    ),
  );
  return {
    ...config,
    stages: config.stages.map((stage) => ({
      ...stage,
      tools: stage.tools.map((tool) => {
        const enabled = table.get(toolKey(stage.name, tool.name));
        if (enabled === undefined) return tool;
        return {
          ...tool,
          enabled,
          effectiveEnabled: enabled && tool.available && stage.stageEnabled,
        };
      }),
    })),
  };
}

export function selectSensoryTools(
  stages: ModelToolStageConfig[],
  query: string,
  stageFilter: string,
  availability: string,
) {
  const needle = query.trim().toLocaleLowerCase();
  let visibleCount = 0;
  const stageRows = stages
    .filter((stage) => !stageFilter || stage.name === stageFilter)
    .map((stage) => {
      const groups = new Map<
        string,
        {
          key: string;
          label: string;
          tools: Array<{ tool: ModelToolConfigItem; matches: boolean }>;
          matchingTools: ModelToolConfigItem[];
        }
      >();
      let hasMatches = false;
      for (const tool of stage.tools) {
        const key = `${tool.category}:${tool.categoryLabel}`;
        const group = groups.get(key) ?? {
          key,
          label: tool.categoryLabel,
          tools: [],
          matchingTools: [],
        };
        const matches =
          [tool.label, tool.name, tool.description, tool.categoryLabel]
            .join(" ")
            .toLocaleLowerCase()
            .includes(needle) &&
          (!availability ||
            (availability === "available" ? tool.available : !tool.available));
        group.tools.push({ tool, matches });
        if (matches) {
          group.matchingTools.push(tool);
          hasMatches = true;
          visibleCount += 1;
        }
        groups.set(key, group);
      }
      return { stage, hasMatches, groups: Array.from(groups.values()) };
    });
  return { stageRows, visibleCount };
}
