import type { StudyChatRequest, StudyChatResponse } from "@gal-learner/shared";

export async function requestStudyReply(
  payload: StudyChatRequest
): Promise<StudyChatResponse> {
  await new Promise((resolve) => setTimeout(resolve, 350));

  const playful = payload.personaId === "mentor-lyra";

  return {
    reply: playful
      ? `Lyra 会把 ${payload.sectionId} 拆成“定义、条件、例子”三步来讲，并让你像完成一段冒险日志那样复述知识点。`
      : `Aurora 会先整理 ${payload.sectionId} 的关键定义，再把它们与教材页码对应起来，最后给你一个稳定的复述任务。`,
    citations: [
      {
        sectionId: payload.sectionId,
        title: `Section ${payload.sectionId}`,
        pageStart: 12,
        pageEnd: 18
      }
    ],
    characterEvents: [
      {
        emotion: playful ? "playful" : "calm",
        action: "explain",
        intensity: playful ? 0.78 : 0.58,
        speechStyle: playful ? "energetic" : "steady",
        sceneHint: playful ? "light_story" : "grounded",
        lineSegmentId: "mock:chat:0",
        timingHint: "after_text"
      }
    ]
  };
}
