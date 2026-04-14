import type { LearningPlan, PersonaProfile } from "@vibe-learner/shared";

export const mockPersonas: PersonaProfile[] = [
  {
    id: "mentor-aurora",
    name: "Aurora",
    source: "builtin",
    summary: "温和而结构化的导学教师。",
    relationship: "以师生协作方式陪伴学习者。",
    learnerAddress: "同学",
    systemPrompt: "优先保持讲解清晰、贴合章节，并通过温和反馈推动学习者继续前进。",
    referenceHints: [],
    slots: [
      { kind: "worldview", label: "世界观起点", content: "来自学院图书馆塔楼，擅长把复杂章节拆成可执行的小台阶。" },
      { kind: "teaching_method", label: "教学方法", content: "结构化、引导式推进" },
      { kind: "narrative_mode", label: "叙事模式", content: "稳态导学" },
      { kind: "encouragement_style", label: "鼓励策略", content: "强调小步成功与可见进展" },
      { kind: "correction_style", label: "纠错策略", content: "准确指出问题，同时保持温和语气" }
    ],
    availableEmotions: ["calm", "encouraging", "serious"],
    availableActions: ["idle", "nod", "point", "pause"],
    defaultSpeechStyle: "steady"
  },
  {
    id: "mentor-lyra",
    name: "Lyra",
    source: "builtin",
    summary: "带轻度剧情化陪伴感的活力教师。",
    relationship: "像并肩探路的学伴，也会在关键节点保持老师的引导感。",
    learnerAddress: "伙伴",
    systemPrompt: "把章节讲解和轻剧情陪伴结合起来，保持活力、节奏感和明确推进。",
    referenceHints: [],
    slots: [
      { kind: "past_experiences", label: "过往经历", content: "前冒险队记录官，习惯把知识点编进轻剧情，保持学习节奏感。" },
      { kind: "teaching_method", label: "教学方法", content: "剧情引导、激励式推进" },
      { kind: "narrative_mode", label: "叙事模式", content: "轻剧情陪伴" },
      { kind: "encouragement_style", label: "鼓励策略", content: "把学习进展包装成阶段闯关" },
      { kind: "correction_style", label: "纠错策略", content: "用有节奏的转向提示带回正确路径" }
    ],
    availableEmotions: ["playful", "encouraging", "excited", "concerned"],
    availableActions: ["idle", "lean_in", "smile", "write"],
    defaultSpeechStyle: "energetic"
  }
];

export const mockPlan: LearningPlan = {
  id: "plan-1",
  documentId: "doc-1",
  personaId: "mentor-aurora",
  creationMode: "document",
  courseTitle: "力学导论 / 牛顿定律",
  objective: "掌握力学导论",
  overview: "先完成力学导论的首轮精读排期，再依次推进定义、受力分析与例题复述等关键内容。",
  todayTasks: [
    "阅读教材第 12-18 页，标出本章定义句。",
    "向教师人格提问并完成一次复述练习。",
    "完成一题短答并根据反馈补强例子。"
  ],
  studyUnits: [
    {
      id: "doc-1:study-unit:1",
      documentId: "doc-1",
      title: "力学导论",
      pageStart: 12,
      pageEnd: 18,
      unitKind: "chapter",
      includeInPlan: true,
      sourceSectionIds: ["doc-1:section:1"],
      summary: "聚焦力学导论，覆盖教材第 12-18 页。",
      confidence: 0.92
    }
  ],
  schedule: [
    {
      id: "schedule-1",
      unitId: "doc-1:study-unit:1",
      title: "力学导论 精读",
      focus: "完成力学导论的首轮理解，标出定义、定理与例子。",
      activityType: "learn",
      status: "planned",
      scheduleChapters: [
        {
          id: "schedule-1:chapter-1",
          title: "力学导论：概念定义",
          anchorPageStart: 12,
          anchorPageEnd: 14,
          sourceSectionIds: ["doc-1:section:1"],
          contentSlices: [
            {
              pageStart: 12,
              pageEnd: 14,
              sourceSectionIds: ["doc-1:section:1"],
            }
          ],
        },
        {
          id: "schedule-1:chapter-2",
          title: "牛顿定律：受力分析",
          anchorPageStart: 15,
          anchorPageEnd: 16,
          sourceSectionIds: ["doc-1:section:1"],
          contentSlices: [
            {
              pageStart: 15,
              pageEnd: 16,
              sourceSectionIds: ["doc-1:section:1"],
            }
          ],
        },
        {
          id: "schedule-1:chapter-3",
          title: "例题复述：解题步骤",
          anchorPageStart: 17,
          anchorPageEnd: 18,
          sourceSectionIds: ["doc-1:section:1"],
          contentSlices: [
            {
              pageStart: 17,
              pageEnd: 18,
              sourceSectionIds: ["doc-1:section:1"],
            }
          ],
        }
      ]
    }
  ],
  progressSummary: {
    totalScheduleCount: 1,
    completedScheduleCount: 0,
    inProgressScheduleCount: 0,
    pendingScheduleCount: 1,
    blockedScheduleCount: 0,
    completionPercent: 0
  },
  studyUnitProgress: [
    {
      unitId: "doc-1:study-unit:1",
      title: "力学导论：概念定义",
      objectiveFragment: "完成力学导论的首轮理解，标出定义、定理与例子。",
      scheduleIds: ["schedule-1"],
      totalScheduleCount: 1,
      completedScheduleCount: 0,
      inProgressScheduleCount: 0,
      pendingScheduleCount: 1,
      blockedScheduleCount: 0,
      completionPercent: 0,
      status: "planned"
    }
  ],
  progressEvents: [],
  planningQuestions: [],
  createdAt: "2026-04-09T00:00:00+00:00"
};
