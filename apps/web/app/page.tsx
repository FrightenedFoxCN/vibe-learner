import { AppLink } from "../lib/app-navigation";
import { MaterialIcon, type MaterialIconName } from "../components/ui/material-icon";
import { TopNav } from "../components/layout/top-nav";

const PAGES = [
  {
    num: "01",
    href: "/plan" as const,
    icon: "event_note" as MaterialIconName,
    title: "计划生成",
    desc: "上传教材或输入目标，生成学习计划。",
  },
  {
    num: "02",
    href: "/study" as const,
    icon: "forum" as MaterialIconName,
    title: "章节对话",
    desc: "按章节提问，联动查看教材。",
  },
  {
    num: "03",
    href: "/tavern" as const,
    icon: "chat" as MaterialIconName,
    title: "角色酒馆",
    desc: "与人格自由互动，或引导角色之间展开讨论。",
  },
  {
    num: "04",
    href: "/persona-spectrum" as const,
    icon: "psychology_alt" as MaterialIconName,
    title: "人格色谱",
    desc: "管理教师人格与风格。",
  },
  {
    num: "05",
    href: "/scene-setup" as const,
    icon: "account_tree" as MaterialIconName,
    title: "场景搭建",
    desc: "搭建学习场景与物体。",
  },
  {
    num: "06",
    href: "/sensory-tools" as const,
    icon: "tune" as MaterialIconName,
    title: "感官工具",
    desc: "管理对话可用工具。",
  },
  {
    num: "07",
    href: "/settings" as const,
    icon: "settings" as MaterialIconName,
    title: "统一设置",
    desc: "管理运行参数与连接。",
  },
  {
    num: "08",
    href: "/model-usage" as const,
    icon: "bar_chart" as MaterialIconName,
    title: "用量审计",
    desc: "查看模型调用与 Token 用量。",
  },
  {
    num: "09",
    href: "/manual" as const,
    icon: "menu_book" as MaterialIconName,
    title: "用户手册",
    desc: "快速上手，查阅操作与常见问题。",
  },
];

export default function HomePage() {
  return (
    <main className="with-app-nav mx-auto grid min-h-screen max-w-[1280px] content-start gap-10 px-8 pt-12 pb-16">
      <TopNav currentPath="/" />

      <header className="grid gap-2">
        <h1 className="m-0 text-[28px] leading-[1.2] font-extrabold tracking-[-0.02em] text-ink">
          学习工作台
        </h1>
        <p className="m-0 text-sm tracking-[0.01em] text-muted">计划 · 对话 · 人格</p>
        <div className="mt-2 h-px bg-border" />
      </header>

      <nav className="grid grid-cols-3 gap-px border border-border bg-border max-[800px]:grid-cols-1">
        {PAGES.map((page) => (
          <AppLink
            key={page.href}
            path={page.href}
            className="grid gap-2 bg-bg px-7 pt-7 pb-6 no-underline transition-colors hover:bg-panel"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-bold tracking-[0.12em] text-accent">
                {page.num}
              </span>
              <span className="inline-flex size-7 items-center justify-center rounded-full border border-accent/25 bg-accent-soft/25 text-accent">
                <MaterialIcon name={page.icon} size={18} />
              </span>
            </div>
            <span className="text-lg leading-[1.2] font-bold text-ink">
              {page.title}
            </span>
            <span className="text-[13px] leading-[1.65] text-muted">{page.desc}</span>
            <span className="mt-1 inline-flex items-center text-border-strong">
              <MaterialIcon name="arrow_forward" size={18} />
            </span>
          </AppLink>
        ))}
      </nav>
    </main>
  );
}
