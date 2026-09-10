export function buildInteractiveCallbackMessage(input: {
  questionType: "multiple_choice" | "fill_blank";
  prompt: string;
  topic: string;
  submittedAnswer: string;
  isCorrect: boolean;
  explanation: string;
}) {
  const verdict = input.isCorrect ? "正确" : "不正确";
  return [
    `学习者刚完成了一道${input.questionType === "multiple_choice" ? "选择题" : "填空题"}。`,
    `题目：${input.prompt}`,
    `主题：${input.topic || "章节练习"}`,
    `学习者答案：${input.submittedAnswer || "（空）"}`,
    `判定：${verdict}`,
    input.explanation ? `解析：${input.explanation}` : "",
    input.isCorrect
      ? "请基于这次正确作答继续推进下一步讲解或追问。"
      : "请先针对错误点做纠正，再继续推进下一步讲解或追问。"
  ].filter(Boolean).join("\n");
}

export function buildSessionPreludeMessage(input: {
  sectionTitle: string;
  themeHint: string;
}) {
  return [
    "正式对话开始前，请先完成一轮隐藏的学习单元预处理和自然引入。",
    `当前学习单元：${input.sectionTitle || "未命名学习单元"}`,
    `当前主题：${input.themeHint || "未额外指定"}`,
    "要求：",
    "1. 如果需要，可先调用计划、场景、教材或时间相关工具，确认当前上下文。",
    "2. 用 2 到 4 句自然地把学习者带入这一学习单元，说明你准备如何陪他学。",
    "3. 如果场景、物体、教材页码或公式焦点有帮助，可以顺手把它们纳入引入。",
    "4. 不要提到这是隐藏消息、预处理消息或内部流程。"
  ].join("\n");
}
