/** A browser wait limit is not evidence that server execution stopped. */
export const STUDY_SEND_WAIT_MS = 60_000;
export const STUDY_QUERY_WAIT_MS = 15_000;

export class StudyRequestWaitExpired extends Error {
  constructor() {
    super("等待本次请求结果超时；服务端可能仍在处理，请查询原请求，勿重新发送。");
    this.name = "StudyRequestWaitExpired";
  }
}

export async function withStudyRequestDeadline<T>(
  waitMs: number,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const expired = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      reject(new StudyRequestWaitExpired());
      controller.abort();
    }, waitMs);
  });
  try {
    // Race also bounds adapters that fail to honor abort. A late response has no
    // consumer and cannot restore the expired UI operation or trigger a retry.
    return await Promise.race([run(controller.signal), expired]);
  } finally {
    clearTimeout(timer!);
  }
}
