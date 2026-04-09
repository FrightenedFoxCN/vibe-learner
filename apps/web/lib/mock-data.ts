import type { LearningPlan, PersonaProfile } from "@gal-learner/shared";

export const mockPersonas: PersonaProfile[] = [
  {
    id: "mentor-aurora",
    name: "Aurora",
    source: "builtin",
    summary: "温和而结构化的导学教师。",
    systemPrompt: "Prioritize clarity, chapter grounding, and encouragement.",
    teachingStyle: ["structured", "guided"],
    narrativeMode: "grounded",
    encouragementStyle: "small wins",
    correctionStyle: "precise but warm",
    availableEmotions: ["calm", "encouraging", "serious"],
    availableActions: ["idle", "explain", "point", "reflect"],
    defaultSpeechStyle: "steady"
  },
  {
    id: "mentor-lyra",
    name: "Lyra",
    source: "builtin",
    summary: "带轻度剧情化陪伴感的活力教师。",
    systemPrompt: "Blend chapter teaching with playful narrative energy.",
    teachingStyle: ["story-led", "motivational"],
    narrativeMode: "light_story",
    encouragementStyle: "hero journey",
    correctionStyle: "redirect with energy",
    availableEmotions: ["playful", "encouraging", "excited", "concerned"],
    availableActions: ["idle", "explain", "celebrate", "prompt"],
    defaultSpeechStyle: "energetic"
  }
];

export const mockPlan: LearningPlan = {
  id: "plan-1",
  documentId: "doc-1",
  personaId: "mentor-aurora",
  overview: "本周完成力学导论与牛顿定律，保留一次错题回看。",
  weeklyFocus: ["力学定义", "惯性与受力分析", "教材例题复述"],
  todayTasks: [
    "阅读教材第 12-18 页，标出本章定义句。",
    "向教师人格提问并完成一次复述练习。",
    "完成一题短答并根据反馈补强例子。"
  ]
};
