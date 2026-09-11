# UX-NAV-001 独立源码复核（2026-09-11）

范围：`TopNav`、`globals.css` 导航差异，以及 AppLink、DesktopViewMenuBridge、Vault 限制和现有页面调用点。执行者为独立子智能体；本轮只读检查产品代码，未修改实现。浏览器尺寸、实际键盘遍历和焦点结果由另一子智能体报告，本文件不将源码审查或源码正则单测描述为浏览器证据。

## 发现与修复确认

首次源码复核发现两处焦点遗漏，已交主智能体修复，并只读确认当前代码：

1. 桌面 Collapse/Expand 按钮位于 `nav` 之外。旧 breakpoint handler 仅判断焦点是否在 `nav` 内，桌面按钮聚焦后切到 ≤760px，按钮会被 CSS 隐藏却没有返焦处理。首次修复增加 `desktopToggle` ref 并纳入 media-query 判断，但随后真实浏览器证实仅此仍不够：CSS 可在 change callback 前隐藏元素并将 activeElement 置为 body，导致比较失败。当前补丁另记录 `lastNavigationFocus`，在 activeElement 为 body 且历史焦点元素无布局矩形时，才用该历史元素恢复判断并转移到 mobileToggle。
2. 移动端通过 `BROWSER_VIEW_TOGGLE_NAV_EVENT` 关闭导航时，旧 handler 仅反转菜单状态，可能隐藏仍拥有焦点的链接。当前 handler 在 mobileOpen 且焦点位于 nav 内时先聚焦 mobileToggle，再关闭菜单；effect 依赖 mobileOpen，并保留 listener cleanup。DesktopViewMenuBridge 仍使用相同事件名。

此前源码复核只能确认 ref 分支存在，不能证明 CSS/焦点事件时序；不再将首次两行 ref 修复描述为足够。当前追加补丁只读检查确认：`onFocusCapture` 更新历史焦点；`onBlur` 在焦点主动移至其他目标，或离开仍可见元素时清空历史；仅 CSS 隐藏造成 body + 历史元素不可见的情形保留回退。实际焦点已在导航外其他控件时不使用历史回退。这与避免主动移出后被抢焦点的目标一致；最终时序与不抢焦点证据仍以另一子智能体的限定浏览器重验为准。

## 其他边界检查

- `NAV_GROUPS` 覆盖当前 10 个 `AppRoutePath` 与全部 TopNav 调用者，包含 `/manual`；现有页面均提供受类型约束的有效 currentPath。
- 三个组提供命名 group 语义，当前组名称含“当前分组”；当前可用页面链接设置 `aria-current="page"`。装饰标题 aria-hidden，避免重复读取。
- AppLink 继续透传 aria 属性与 onClick，保留其已有客户端导航和 Vault 检查；未引入另一套导航方法。
- Vault 尚未配置时，除 Settings 外的入口以非聚焦 span/aria-disabled 呈现；Settings 保持链接。源码中没有放宽 Vault 入口限制。
- 保留折叠偏好 storage key、`--app-nav-width` 和桌面事件桥。窄屏展开状态与桌面 collapsed 状态分离；桌面折叠隐藏标签的规则仅应用于 ≥761px，避免移动菜单继承 icon-only 状态。
- ≤760px 从隐藏滚动条的水平入口改为显式“全部导航”披露按钮和纵向列表；列表受 `100dvh` 高度约束并可纵向滚动。Escape 与焦点离开已有关闭分支。
- `app-side-nav` CSS 没有其他组件共享使用者；其他导航宽度和移动 Header 高度消费者继续保留原变量接口。

除上述两处遗漏及浏览器进一步揭示的 CSS 先隐藏时序问题，本轮范围内未发现其他新增源码缺陷。当前补丁有明确的焦点回退条件和主动离开清理条件，源码审查不独立认证其浏览器行为。

## 单测

包含历史焦点回退的最新补丁复核后，再次运行：

```bash
node --experimental-strip-types --test \
  apps/web/tests/navigation-study-accessibility.test.ts \
  apps/web/tests/desktop-startup.test.ts
```

结果：**7 项通过**。其中 3 项检查桌面导航/Vault/provider 生命周期源码契约，4 项检查 Study、Tavern 与设置的既有可访问性结构。已删除的旧 mobile icon 横排 CSS 正则不再用于认证新导航。这些测试不执行浏览器布局，也不证明新分组菜单的实际焦点行为。

本文件不独立关闭 UX-NAV-001；需结合另一份 390/760/桌面宽度、键盘、当前组/页和 Vault 的真实浏览器验收。
