# Tavern Room React Profiler 独立验收（2026-09-11）

结果：**三个位置各30次有效React追加commit全部满足P95 ≤ 50ms；DOM保留上限100及窗口外当前房间保留通过。** 本智能体未修改产品Profiler埋点或列表实现，独立审计测量边界并编写、执行浏览器采样脚本。结合单独真实HTTP服务端验收，支持关闭`PERF-TAV-ROOMS-001`。

## 测量结果

| 区域（0基排序位置） | 初始30项 | 实际追加30项 | 有效样本 | P50 ms | P95 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 开始 | 0–29 | 30–59 | 30 | 1.80 | 2.30 | 2.30 |
| 中间 | 450–479 | 480–509 | 30 | 1.90 | 2.20 | 2.40 |
| 末尾 | 940–969 | 970–999 | 30 | 1.90 | 2.30 | 2.80 |

每区另有5次完整UI加载/追加预热，共15次预热和90次有效样本；预热原始记录一并保留。P95使用nearest-rank（30项排序后的第29项）。没有删除慢样本；各次有效追加恰好对应1个符合边界的React commit。

结构验收预先选择排序最后一间Room，令其在初始30项窗口之外。实际Room button DOM数量依次 **31 → 61 → 91 → 100**，当前房间仍`aria-pressed=true`且包含于Profiler的roomIds；100项后“载入更多房间”按钮确实不存在。独立附加控件断言用例653ms通过，不重复90次计时。

## 为什么这是真实React测量

产品仅在`NEXT_PUBLIC_TAVERN_ROOM_PROFILING=1`时以React `Profiler`包裹实际`TavernSessionPanel`；未用纯函数计时、浏览器点击墙钟时间或接口延迟代替React门。构建使用`next build --profile`。独立检查`onRender`记录原始`id/phase/actualDuration/baseDuration/startTime/commitTime`、`roomIds`及`loadingMore`；正常production编译不包Profiler。

测试等待真实Room detail初始化完成，再点击实际“载入更多房间”。采样仅选择点击后`phase != mount`且roomIds精确等于初始30项+新增30项的callback。mount、loading-only等回调不冒充追加样本，**所有回调都存档**。若一次追加有多个匹配commit，协议取其中最大actualDuration；本次每次恰好1个。全部时长为React onRender的`actualDuration`，没有额外修正或扣除。

UI超过100项即停止分页，所以不能自然走到1000项夹具的中间/尾部。本测试仅将**首次**list请求转发到同一个真实后端夹具的指定cursor，响应正文和`next_cursor`不改；之后“载入更多”走原产品请求与合并路径。起始窗口由实际HTTP遍历取得，不伪造cursor。这个窗口设置是基准初始化，不宣称用户目前可连续翻遍1000个房间。

## 环境与来源绑定

- 1000 Room真实临时SQLite夹具：contract `tavern-room-list-fixture-v1`，seed `vibe-learner-tavern-1000-v1`；后端`127.0.0.1:8897`，合法Persona快照，detail/runs/recovery可正常HTTP读取。测试期间没有修改业务数据或调用provider。
- Profiler生产构建：`ZfnwP5lK6iKQz54x_yQKS`，Next运行于`127.0.0.1:3417`。
- 源码HEAD `26f59d49ecadb5033aae248afea0a0295bf46abe` **加未提交的本次Profiler埋点**；该SHA自身不包含埋点。原始记录另含实测组件、state、CSS、Next config和采样脚本SHA256及build ID。
- Apple M4，10 logical CPUs，Darwin 25.6.0 arm64，Node v26.8.1，Chromium 153.0.8010.12，1440×1000，无CPU限速；浏览器每次新context。
- `npm run check:web`通过。测量完成后两个Playwright Next进程均已自动停止，后端智能体已确认专属夹具服务关闭、临时目录清理；主智能体随后恢复普通production build。计时完成后主智能体还在Next config中把未设置的profiling开关默认值显式设为"0"，让普通构建彻底裁剪分支；显式"1"的profiling行为不变。本报告保留实际测量时的build ID与源码hash，不把这项后续普通构建裁剪改动倒填进测量来源。

可重放命令（先构建profiling版本并启动专属1000-Room backend）：

```bash
NEXT_PUBLIC_TAVERN_ROOM_PROFILING=1 npm exec --workspace @vibe-learner/web -- next build --profile
TAVERN_PROFILE_API_URL=http://127.0.0.1:8897 TAVERN_PROFILE_OUTPUT=/tmp/tavern-room-react-profile.json npm exec --workspace @vibe-learner/web -- playwright test tests/browser/tavern-room-profile.spec.ts
```

未设置`TAVERN_PROFILE_API_URL`时用例明确跳过，不算性能门通过。运行整个spec先生成timing raw，再运行附加cap控件用例；单独运行后者需要已有同夹具的raw文件。

## 原始证据与失败审计

- [完整105轮回调与90有效样本](../acceptance/tavern-room-react-profile-2026-09-11.json)：含全部原始React回调、真实list URL、选样规则、环境及三个聚合结果。
- [独立100项控件断言](../acceptance/tavern-room-react-cap-2026-09-11.json)。
- [后端提供的真实cursor窗口及预期ID](../acceptance/tavern-room-profile-windows-2026-09-11.json)。
- [前置环境/脚本失败记录](../acceptance/tavern-room-react-profile-initial-failure-2026-09-11.json)。

首轮测试后端仅允许3000源，list转发可用但直连detail/cap受CORS阻挡，因此整轮作废，未拿该轮时长认证。首次脚本只在末尾落raw，后置结构失败时尚未保存；已改为每区checkpoint。修复只在fixture增加3417允许源，没有修改产品CORS。随后新加入的就绪locator误要求文本不含原有revision后缀，在第一个预热前失败；修正locator后才进行本报告完整有效重跑。两次是明确基准环境/脚本失败，没有以此删除任何有效慢样本。

React `actualDuration`衡量该组件树的render工作，不包含全部浏览器layout/paint或网络等待。本报告只认证文档规定的React门与DOM结构门；真实设备、全部浏览器平台以及整体交互延迟不由此扩大认证。

主线收尾：`npm run check`、4项后端分页回归及最终普通`npm run build:web`通过；最终`npm run check:web`通过。普通构建后检查`.next/static`不存在`__tavernRoomProfileSamples`，确认测试埋点已被编译裁剪。
