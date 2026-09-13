import { isApiHttpError } from "./http-error";

export function humanizeSettingGenerationError(error: unknown, subject = "内容"): string {
  if (!isApiHttpError(error)) {
    const detail = error instanceof Error ? error.message.trim().slice(0, 160) : "";
    return detail
      ? `${subject}生成失败（${detail}），请稍后重试。`
      : `${subject}生成失败，请稍后重试。`;
  }
  const code = error.code || error.message;
  const messages: Record<string, string> = {
    setting_model_output_truncated: "模型输出达到上限且未形成完整结果。请减少输入长度后重试；系统会保留本次诊断记录。",
    setting_model_timeout: "模型生成超时。请缩短输入或稍后重试；本次请求未写入草稿。",
    setting_model_invalid_json: "模型返回的结构化内容不完整。请重试，系统会自动进行一次格式修复。",
    setting_model_invalid_payload: "模型结果未通过结构校验。请重试或减少生成范围。",
    setting_model_content_filter: "模型输出触发内容过滤。请改用更中性的描述后重试。",
    setting_model_unsupported_params: "当前模型不支持本次生成参数，请在设置中切换兼容模型。",
    setting_model_rate_limited: "模型服务当前限流，请稍后重试。",
    setting_model_network_error: "模型服务网络异常，请检查连接后重试。",
  };
  return messages[code] ?? `${subject}生成失败（${code}），请检查模型设置后重试。`;
}
