import { OutputLanguageField } from "../ui/output-language-field";
import { CharacterShell } from "./character-shell";
import type { StudyConsoleProps } from "./study-console-types";

type StudyConsoleSidebarProps = Pick<
  StudyConsoleProps,
  | "selectedPlanId"
  | "planOptions"
  | "onSelectPlan"
  | "onCreateSession"
  | "showCreateSession"
  | "selectedScheduleId"
  | "scheduleOptions"
  | "onChangeSchedule"
  | "onJumpToScheduleStart"
  | "canJumpToScheduleStart"
  | "onCompleteCurrentSchedule"
  | "canCompleteCurrentSchedule"
  | "persona"
  | "sceneProfile"
  | "session"
  | "affinityState"
  | "isPending"
  | "disabled"
  | "pendingFollowUps"
> & {
  turnCount: number;
  languagePreference: string;
  setLanguagePreference: (value: string) => void;
  languageInputLocked: boolean;
};

export function StudyConsoleSidebar({
  selectedPlanId,
  planOptions,
  onSelectPlan,
  onCreateSession,
  showCreateSession,
  selectedScheduleId,
  scheduleOptions,
  onChangeSchedule,
  onJumpToScheduleStart,
  canJumpToScheduleStart,
  onCompleteCurrentSchedule,
  canCompleteCurrentSchedule,
  persona,
  sceneProfile,
  session,
  turnCount,
  affinityState,
  isPending,
  disabled,
  pendingFollowUps,
  languagePreference,
  setLanguagePreference,
  languageInputLocked,
}: StudyConsoleSidebarProps) {
  const activeFollowUp =
    pendingFollowUps?.find((item) => item.status === "pending") ?? null;

  return (
    <aside className="study-console-sidebar" aria-label="学习会话设置">
      <div className="study-console-sidebar-stack">
        <div className="study-console-control-card">
          <div className="study-console-control-stack">
            <div className="study-console-theme-row">
              <label className="study-console-theme-label study-console-primary-select-label">
                <span className="study-console-caption">学习计划</span>
                <select
                  className="study-console-select"
                  value={selectedPlanId}
                  onChange={(event) => onSelectPlan(event.target.value)}
                  disabled={!planOptions.length}
                  title={
                    planOptions.find((item) => item.id === selectedPlanId)?.title ||
                    "暂无学习计划"
                  }
                >
                  {planOptions.length ? (
                    planOptions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.title}
                      </option>
                    ))
                  ) : (
                    <option value="">暂无学习计划</option>
                  )}
                </select>
              </label>
              {showCreateSession ? (
                <button
                  type="button"
                  className="study-console-primary-btn study-console-btn-disabled"
                  disabled={isPending || !onCreateSession}
                  onClick={() => {
                    if (onCreateSession) onCreateSession();
                  }}
                >
                  {isPending ? "创建中…" : "创建会话"}
                </button>
              ) : null}
            </div>

            <div className="study-console-theme-row">
              <label className="study-console-theme-label">
                <span className="study-console-caption">排期项</span>
                <select
                  className="study-console-select"
                  value={selectedScheduleId}
                  onChange={(event) => onChangeSchedule(event.target.value)}
                  disabled={isPending || disabled}
                  title={
                    scheduleOptions.find((item) => item.id === selectedScheduleId)
                      ?.title || "暂无排期项"
                  }
                >
                  {scheduleOptions.length ? (
                    scheduleOptions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.title}
                      </option>
                    ))
                  ) : (
                    <option value="">暂无排期项</option>
                  )}
                </select>
              </label>
            </div>

            <div className="study-console-theme-row">
              <button
                type="button"
                className="study-console-ghost-btn study-console-btn-disabled"
                disabled={
                  isPending ||
                  disabled ||
                  !onJumpToScheduleStart ||
                  !canJumpToScheduleStart
                }
                onClick={() => {
                  if (onJumpToScheduleStart) onJumpToScheduleStart();
                }}
              >
                定位排期首页
              </button>
              <button
                type="button"
                className="study-console-primary-btn study-console-btn-disabled"
                disabled={
                  isPending ||
                  disabled ||
                  !onCompleteCurrentSchedule ||
                  !canCompleteCurrentSchedule
                }
                onClick={() => {
                  if (onCompleteCurrentSchedule) void onCompleteCurrentSchedule();
                }}
              >
                完成当前排期
              </button>
            </div>
            <OutputLanguageField
              value={languagePreference}
              onChange={setLanguagePreference}
              study
              disabled={languageInputLocked}
            />
          </div>
        </div>

        <div className="study-console-companion-card">
          <div className="study-console-companion-meta">
            <div className="study-console-companion-header">
              <span className="study-console-caption">教师人格</span>
            </div>
            <div className="study-console-companion-row">
              <span className="study-console-companion-chip">
                人格 · {persona.name}
              </span>
              <span className="study-console-companion-chip">
                场景 · {sceneProfile?.title || "未设置"}
              </span>
            </div>
            <p className="study-console-companion-summary">
              {sceneProfile?.summary || persona.summary || "尚未配置场景摘要。"}
            </p>
          </div>
          <div className="study-console-shell-card">
            <CharacterShell
              persona={persona}
              response={session}
              pending={isPending}
              turnCount={turnCount}
              affinityState={affinityState}
              nextFollowUp={activeFollowUp}
              variant="embedded"
            />
          </div>
        </div>
      </div>
    </aside>
  );
}
