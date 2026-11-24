import type { LearningPlan, StudyScheduleItem, StudyUnit } from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import type { PlanOverviewProps } from "./plan-overview";
import styles from "./plan-overview.module.css";

interface PlanScheduleProps extends Pick<
  PlanOverviewProps,
  "onStartStudyFromPlan" | "onUpdatePlanProgress" | "isBusy"
> {
  plan: LearningPlan;
  showScheduleDetails: boolean;
  onToggleScheduleDetails: () => void;
  expandedScheduleItems: Record<string, boolean>;
  onToggleScheduleItem: (scheduleId: string) => void;
  reviewDrafts: Record<string, string>;
  onChangeReview: (scheduleId: string, note: string) => void;
}

export function PlanSchedule({
  plan,
  showScheduleDetails,
  onToggleScheduleDetails,
  expandedScheduleItems,
  onToggleScheduleItem,
  reviewDrafts,
  onChangeReview,
  isBusy,
  onUpdatePlanProgress,
  onStartStudyFromPlan,
}: PlanScheduleProps) {
  const visibleScheduleItems = showScheduleDetails
    ? plan.schedule
    : plan.schedule.slice(0, 4);
  const hasCollapsedScheduleItems = plan.schedule.length > visibleScheduleItems.length;
  return (
    <div className={styles.progressCard}>
      <PlanProgressSummary progress={plan.progressSummary} />
      {plan.schedule.length ? (
        <div className={styles.scheduleList}>
          <p className={styles.startNotice}>
            点击“开始”会创建或打开对应学习会话，并调用模型准备该 Study
            Unit；这会产生模型用量。
          </p>
          {visibleScheduleItems.map((item, index) => (
            <PlanScheduleItem
              key={item.id}
              plan={plan}
              item={item}
              index={index}
              isBusy={isBusy}
              expanded={Boolean(expandedScheduleItems[item.id])}
              onToggle={() => onToggleScheduleItem(item.id)}
              reviewDraft={reviewDrafts[item.id] ?? ""}
              onChangeReview={(note) => onChangeReview(item.id, note)}
              onUpdatePlanProgress={onUpdatePlanProgress}
              onStartStudyFromPlan={onStartStudyFromPlan}
            />
          ))}
          {hasCollapsedScheduleItems ? (
            <button
              type="button"
              className={styles.scheduleToggle}
              onClick={onToggleScheduleDetails}
            >
              {showScheduleDetails
                ? "收起额外排期"
                : `展开后面 ${plan.schedule.length - visibleScheduleItems.length} 项`}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PlanProgressSummary({
  progress,
}: {
  progress: LearningPlan["progressSummary"];
}) {
  return (
    <>
      <div className={styles.progressHead}>
        <div className={styles.sectionHeadMeta}>
          <span className={styles.sectionLabel}>推进</span>
          <span className={styles.count}>
            {progress.completedScheduleCount}/{progress.totalScheduleCount}
          </span>
        </div>
        <span className={styles.progressPercent}>{progress.completionPercent}%</span>
      </div>
      <div className={styles.progressBarTrack}>
        <div
          className={styles.progressBarFill}
          style={{
            width: `${Math.max(0, Math.min(100, progress.completionPercent))}%`,
          }}
        />
      </div>
      <div className={styles.progressStats}>
        <span className={styles.progressStat}>
          进行中 {progress.inProgressScheduleCount}
        </span>
        <span className={styles.progressStat}>
          待处理 {progress.pendingScheduleCount}
        </span>
        <span className={styles.progressStat}>
          阻塞 {progress.blockedScheduleCount}
        </span>
      </div>
    </>
  );
}

interface PlanScheduleItemProps extends Pick<
  PlanOverviewProps,
  "onStartStudyFromPlan" | "onUpdatePlanProgress" | "isBusy"
> {
  plan: LearningPlan;
  item: StudyScheduleItem;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  reviewDraft: string;
  onChangeReview: (note: string) => void;
}

function PlanScheduleItem({
  plan,
  item,
  index,
  isBusy,
  expanded,
  onToggle,
  reviewDraft,
  onChangeReview,
  onUpdatePlanProgress,
  onStartStudyFromPlan,
}: PlanScheduleItemProps) {
  const studyAction =
    item.status === "completed"
      ? "复习"
      : item.status === "in_progress"
        ? "继续学习"
        : item.status === "planned"
          ? "开始"
          : "打开";
  return (
    <div className={styles.scheduleItem} data-plan-schedule={item.id}>
      <div className={styles.scheduleHeader}>
        <div className={styles.scheduleTitleBlock}>
          <span className={styles.scheduleIndex}>第 {index + 1} 课</span>
          <span className={styles.scheduleTitle}>{item.title}</span>
        </div>
        <div className={styles.scheduleHeaderActions}>
          <span className={styles.statusBadge} data-status={item.status}>
            {formatScheduleStatus(item.status)}
          </span>
          {item.scheduleChapters.length ? (
            <button
              type="button"
              className={styles.inlineButton}
              disabled={isBusy}
              aria-expanded={expanded ? "true" : "false"}
              aria-label={`${expanded ? "收起" : "展开"}第 ${index + 1} 课章节`}
              onClick={onToggle}
            >
              {expanded
                ? `收起章节 · ${item.scheduleChapters.length}`
                : `展开章节 · ${item.scheduleChapters.length}`}
            </button>
          ) : null}
          <button
            type="button"
            className={styles.primaryButton}
            disabled={isBusy}
            aria-label={`${studyAction}第 ${index + 1} 课：${item.title}`}
            onClick={() => {
              const studyUnit = resolveStudyUnitById(plan, item.unitId);
              if (!studyUnit) {
                return;
              }
              const firstScheduleChapter = item.scheduleChapters[0];
              void onStartStudyFromPlan({
                studyUnitId: item.unitId,
                scheduleId: item.id,
                scheduleChapterId: firstScheduleChapter?.id,
                chapter: firstScheduleChapter?.title || item.title,
                page: firstScheduleChapter?.anchorPageStart || studyUnit.pageStart,
                scheduleIds: [item.id],
              });
            }}
          >
            {studyAction}
          </button>
          <button
            type="button"
            className={styles.ghostButton}
            disabled={isBusy || item.status === "completed"}
            aria-label={`完成第 ${index + 1} 课：${item.title}`}
            onClick={() => {
              void onUpdatePlanProgress({
                planId: plan.id,
                scheduleIds: [item.id],
                status: "completed",
              });
            }}
          >
            完成
          </button>
          <button
            type="button"
            className={styles.ghostButton}
            disabled={isBusy || item.status === "planned"}
            aria-label={`重置第 ${index + 1} 课：${item.title}`}
            onClick={() => {
              void onUpdatePlanProgress({
                planId: plan.id,
                scheduleIds: [item.id],
                status: "planned",
              });
            }}
          >
            重置
          </button>
        </div>
      </div>
      <div className={styles.scheduleMeta}>
        <span className={styles.scheduleMetaItem}>
          时长 {item.durationMinutes ? `${item.durationMinutes} 分钟` : "未记录"}
        </span>
        <span className={styles.scheduleMetaItem}>
          范围 {formatScheduleScope(item)}
        </span>
        <span className={styles.scheduleMetaItem}>
          方式 {formatActivityType(item.activityType)}
        </span>
      </div>
      <div className={styles.scheduleTaskBlock}>
        <span className={styles.scheduleTaskLabel}>本次任务</span>
        <p className={styles.scheduleFocus}>{item.focus}</p>
      </div>
      {item.coverageMode &&
      item.coverageMode !== "complete" &&
      item.workloadRationale ? (
        <p className={styles.scheduleFocus}>
          {item.coverageMode === "overview" ? "导览说明" : "选读说明"}：
          {item.workloadRationale}
        </p>
      ) : null}
      {item.scheduleChapters.length && expanded ? (
        <div className={styles.subsectionList}>
          {item.scheduleChapters.map((chapter) => (
            <div key={chapter.id} className={styles.subsectionTag}>
              <span className={styles.subsectionName}>{chapter.title}</span>
              <span className={styles.subsectionPage}>
                p.{chapter.anchorPageStart}-{chapter.anchorPageEnd}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <PlanScheduleReview
        plan={plan}
        item={item}
        index={index}
        isBusy={isBusy}
        reviewDraft={reviewDraft}
        onChangeReview={onChangeReview}
        onUpdatePlanProgress={onUpdatePlanProgress}
      />
    </div>
  );
}

function PlanScheduleReview({
  plan,
  item,
  index,
  isBusy,
  reviewDraft,
  onChangeReview,
  onUpdatePlanProgress,
}: Omit<PlanScheduleItemProps, "expanded" | "onToggle" | "onStartStudyFromPlan">) {
  const reviewEvents = reviewEventsForSchedule(plan, item.id);
  return (
    <details className={styles.reviewDetails}>
      <summary className={styles.reviewSummary}>
        复盘与进度记录 · {reviewEvents.length}
      </summary>
      <div className={styles.reviewBody}>
        <label className={styles.reviewLabel}>
          <span>第 {index + 1} 课复盘</span>
          <textarea
            value={reviewDraft}
            onChange={(event) => onChangeReview(event.target.value)}
            className={styles.reviewTextarea}
            placeholder="记录掌握情况、疑问或下次要补回的内容"
            disabled={isBusy}
          />
        </label>
        <button
          type="button"
          className={styles.ghostButton}
          disabled={isBusy || !reviewDraft.trim()}
          onClick={async () => {
            const didSave = await onUpdatePlanProgress({
              planId: plan.id,
              scheduleIds: [item.id],
              status: item.status,
              note: reviewDraft,
            });
            if (didSave) {
              onChangeReview("");
            }
          }}
        >
          保存本课复盘
        </button>
        {reviewEvents.length ? (
          <ol className={styles.reviewList}>
            {reviewEvents.map((event) => (
              <li key={event.id} className={styles.reviewEntry}>
                <span>{event.note}</span>
                <span className={styles.reviewMeta}>
                  {formatTimestamp(event.createdAt, { style: "short" })} ·{" "}
                  {formatScheduleStatus(event.status)}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className={styles.reviewEmpty}>尚无复盘记录。</p>
        )}
      </div>
    </details>
  );
}

function formatScheduleStatus(status: string) {
  switch (status) {
    case "completed":
      return "已完成";
    case "in_progress":
      return "进行中";
    case "blocked":
      return "阻塞";
    case "skipped":
      return "已跳过";
    default:
      return "待开始";
  }
}

function formatActivityType(activityType: string) {
  if (activityType === "review") return "复习";
  if (activityType === "learn") return "学习";
  return activityType || "未记录";
}

function formatScheduleScope(item: StudyScheduleItem) {
  const ranges = item.scheduleChapters.flatMap((chapter) =>
    chapter.contentSlices.length
      ? chapter.contentSlices.map((slice) => [slice.pageStart, slice.pageEnd] as const)
      : [[chapter.anchorPageStart, chapter.anchorPageEnd] as const],
  );
  if (!ranges.length) return "未记录";
  const ordered = ranges
    .filter(([start, end]) => start > 0 && end >= start)
    .sort(([left], [right]) => left - right);
  const merged: Array<[number, number]> = [];
  ordered.forEach(([start, end]) => {
    const previous = merged.at(-1);
    if (previous && start <= previous[1] + 1) {
      previous[1] = Math.max(previous[1], end);
    } else {
      merged.push([start, end]);
    }
  });
  return merged.length
    ? merged
        .map(([start, end]) => (start === end ? `p.${start}` : `p.${start}–${end}`))
        .join("、")
    : "未记录";
}

function reviewEventsForSchedule(plan: LearningPlan, scheduleId: string) {
  return plan.progressEvents
    .filter((event) => event.scheduleIds.includes(scheduleId) && event.note.trim())
    .slice(-3)
    .reverse();
}

function resolveStudyUnitById(plan: LearningPlan, unitId: string): StudyUnit | null {
  return plan.studyUnits.find((unit) => unit.id === unitId) ?? null;
}
