# 顶级导航独立验收（2026-09-11）

最终结果：**23项生产Chromium通过，32.0秒**，包括10项新增独立导航验收与13项既有路由/草稿回归；`npm run check:web`通过。支持关闭`UX-NAV-001`当前导航分组、窄屏完整入口、键盘与当前页语义范围。本智能体只修改测试和证据，未修改产品导航实现。

## 独立发现与修复复验

初次只读审计发现系统组漏掉`/manual`，而该页把`currentPath="/manual"`传给TopNav，导致当前组非空假设不成立。主智能体将手册纳入系统组；最终所有10页面都访问并验证。

扩大焦点验收后发现desktop collapse按钮聚焦再缩窄到390px时，移动按钮未获得焦点。主智能体修复隐藏前最近焦点的追踪；独立复验同时覆盖主动把焦点移到页面输入后resize不抢焦点。前一轮21/22的失败没有被隐去或当作通过；最终在修复后的新build完整23项通过。

## 最终环境与证据

- 生产build：`7y_0OnsRd6SntazJHBzcM`；源码HEAD `547c1dc70190df355c98443bbee047b986feeeda` **加本次未提交导航修改**，不将HEAD本身描述为已包含实现。
- Next production `127.0.0.1:3417`；Playwright Chromium，业务API合成fixture，没有真实模型、数据库或Vault写入。
- 视口390×844、760×844、1440×844；断点专门跨越760/761。
- 命令：`npm exec --workspace @vibe-learner/web -- playwright test tests/browser/navigation-independent.spec.ts tests/browser/route-ownership.spec.ts`。
- [机器可读结果、布局尺寸与API请求清单](../acceptance/navigation-independent-2026-09-11.json)。
- [390px截图](../acceptance/navigation-390-2026-09-11.png)及[1440px截图](../acceptance/navigation-1440-2026-09-11.png)已由独立验收智能体实际查看：三组及10个文字入口完整可见，无文字裁切；移动展开呈纵向导航，无水平滑动找入口。

## 实际覆盖

| 范围 | 独立断言 |
| --- | --- |
| 10页面×3视口 | `/`、Plan、Study、Tavern、Persona、Scene、Sensory、Settings、Usage、Manual全部加载，无pageerror；3个可访问group名称，唯一`aria-current=page`精确对应URL，当前组名称明确标记 |
| 完整发现与键盘遍历 | 每个视口逐一正向Tab到全部10入口，再逐一Shift+Tab返回；每步确认实际focus且边界框在视口内。所有入口是有名称的真实link，不只验证隐藏集合 |
| 移动展开 | 当前组/页和“全部导航”可见；展开状态/controls明确；390与760全部入口≥44px、无导航横向overflow |
| Escape与离开 | Enter打开，Tab进入首项；Escape关闭并返回触发按钮；从末项Tab离开aside后关闭且不把焦点拉回 |
| desktop/mobile resize | desktop折叠仍保留名称；760移动完整文字不受持久折叠状态影响；被隐藏link/collapse控制的焦点转到mobile toggle，回761时toggle焦点转到当前link |
| 外部菜单事件 | `vibe:view:toggle-nav`关闭移动菜单，焦点从即将隐藏link返回可见按钮 |
| 不抢用户焦点 | 用户先主动聚焦学习目标输入，再从desktop缩窄；输入保持focus |
| 浏览器历史 | Plan→Scene点击后移动菜单关闭，back/forward同步URL、当前页和当前组 |
| Vault受限入口 | 模拟未配置desktop Vault事件后，TopNav仅Settings保持真实可点击link，其余9入口为aria-disabled；点击禁用项不导航 |
| 路由兼容性 | 11冷启动入口（10页+404）及focus请求白名单；Plan/Study共享owner、离页停止学习focus刷新；目标/PDF草稿经Settings往返保留 |

## 边界

Vault用例验证前端已有未配置状态下的导航限制，不等于实际创建/解锁Tauri Vault或系统密钥库验收。DOM语义与键盘焦点通过，不冒充VoiceOver/NVDA听觉播报认证。截图与overflow检查限定导航，不据此宣布全部业务页面移动布局通过。测试生产服务已由Playwright自动关闭。

主线最终校验：焦点追踪修复后的 `npm run build:web` 与完整 `npm run check` 均通过；共享契约、前端可靠性与所有 PR eval 门保留。
