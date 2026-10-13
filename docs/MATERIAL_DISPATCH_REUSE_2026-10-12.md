# 刀镡路线与派遣复用核对（2026-10-12）

本说明基于仓库 `AGENTS.md`、README、2026-10-11 迁移交接、路线/派遣核验文档，以及固定 BetterGI 源码加当前完整补丁。本轮只读源码与公开社区来源，没有启动游戏或 testhost，没有修改共享脚本、C# 或 JS。没有把账号、库存、运行标识、授权、截图或私人日志写入此文件。

## 先给执行结论

- 刀镡路线已有可复用的独立执行器：`AutoGameMaterialRoute/operator.js::runMaterialRoute` → `pathingScript.RunMaterialRoute(requestJson, token)`。它把订阅路线的本地路径和 SHA-256 固定到白名单、要求四人队伍/钟离护盾保护，并在执行前后各做两次精确库存读取。现有本机记录只支持**单段首验**（5 个 fight 点、实际材料净增、护盾与画质恢复）；两个段连续运行的完整验收仍未知。
- `AutoGameMaterialRoute/session.js::runMaterialRouteSession` 已是“一次登录内两段”的编排器，但只能接收两段；每段需 60–480 秒，路线点距不超过 80 地图单位视为重叠；启动与每段后都必须通过固定蒙德城恢复证明。它是代码可复用项，不能当作今天这条路线或所有战斗状态已实机跑通。
- 派遣可复用 BetterGI 的 `GoToAdventurersGuildTask` 与 `OneKeyExpeditionTask.Run()` 完成页面导航和“全部领取/再次派遣”点击；不能复用为成功证明。现有原生代码没有领取回执、新派遣槽位状态或独立机器事件。工作流解析器对此保留 `dispatchVerification=unknown`，是正确边界。
- 公开社区路线可由用户自己的 BetterGI 脚本订阅提供给白名单；仓库不应打包路线 JSON。`bettergi-scripts-list` 没有可确认的仓库级开源许可证元数据，路线文件也未确认单独许可。引用和使用不等于允许再分发。
- 04:00（UTC+8）是用户指定的**工作流游戏日/授权/预算切分线**。它不自动证明一处野伏众刷新。社区资料把“精英敌人每日服务器重置”和“普通敌人常见 12 小时”分开描述；野伏众在游戏图鉴归在普通/易类的说法意味着 12 小时值得实测，但路线内可能混有特殊/任务/精英组点位，不能统一推断。刷新判定必须以当前画面观测为准。

## 已有接口与能直接复用的代码

| 用途 | 现有接口/代码 | 已有边界 |
| --- | --- | --- |
| 取刀镡库存 | `AutoGameMaterialRoute/main.js` 的 `api.countItems(names)`；构造 `CountInventoryItemParam`，设 `IconRecognitionMode=Item`、`GridScreenName=CharacterDevelopmentItems`、追加 `ItemNames`，调用 `dispatcher.RunCountInventoryItemTask(param)` | BetterGI 的通用计数任务已存在；路线包装器只接受三种刀镡名称。JS 在路线前后各读两次，间隔 180ms；有缺项、非整数、读数不一致或负增量时不宣称精确收益。零增量可以是成功执行结果，但不是获得材料。 |
| 执行一段路线 | `AutoPathingScript.RunMaterialRoute(string requestJson, CancellationToken? customCt)`；JS 侧 `api.runRoute(request)` 为请求设置取消令牌并解析 JSON 返回值 | 请求包含 `runId`、`routePath`、`sha256`、`partyName`、`strategyName`、`requireZhongliShield`、`timeoutSeconds`、可选 `expectedTeam`。超时最多 480 秒。C# 解析 `MaterialRouteRequest`，检查路径白名单与磁盘哈希、fight 点、自动拾取、战斗结束/清理、返回主界面；条件不全返回 failed/cancelled/timeout，不把通用 `pathingScript.run()` 的正常返回算成功。 |
| 一个登录内连续两段 | `parseSessionSettings` / `runMaterialRouteSession` | 恰好两段；每段 60–480 秒；两个路线身份和哈希不能相同，fight 点不能在 80 单位内重叠；每段独立库存前后读数、状态和报告；仅前一段成功且安全恢复通过时才进入下一段。遇到 unknown/失败即停止后续段，不能重放该段。 |
| 开始前免费队伍准备 | `preparation.js::runPartyPreparation` → `RunPartyPreparation` | 这是免费七天神像恢复/复苏和队伍状态核验的单独节点，不做路线或库存读取。JS 限制零资源、禁止道具/食物/合成/升级；C# 对四人、生命状态和结束主界面作有界验证。现存实现不能替代路线节点自身对真实队伍和战斗状态的检查。 |
| 路段后恢复 | `recovery.js::runMaterialRecovery` → `RunMaterialRecovery` | 固定安全点、传送/加载/落地/坐标/队伍/主界面的核验；不攻击、不读库存、不复苏或使用物品。会话进入后续段需要恢复证据为 true。 |
| 04:00 游戏日 | 路线脚本 `gameDate(now) = new Date(now + 4h).toISOString().slice(0,10)`；工作流 `material_route.py` 有日预算、点位覆盖和未知结果门控 | 当地日期从 UTC+8 04:00 切换。当前路线单段 native 上限 8 分钟、整轮上限 16 分钟、日累计 native 上限 30 分钟。不能把旧日期的 checkpoint 当成今天有效的敌人存活证明，也不能因 04:00 到点而清掉仍 unresolved 的 unknown/failed 点位。 |

已有 `scripts/route_selection.py::preview_route_selection(inventory, requirements, candidates, *, now, day_records=None)` 是只读排序预览，不连接路线执行器。它要求三阶库存和候选证据可验证，按目标缺口有效材料量优先，同收益再看效率/稳定性；路线文件数、标注敌人数、`fight` 动作数都不能代替掉落证据。选择结果目前不是一张能自动连续执行的路线计划。

## 哪些已跑通，哪些只是实现/计划

**本机既有记录称已完成的窄范围**：独立 `material-route` 首段的有限实机执行；前后库存读取和净增、钟离护盾守卫及画质恢复都各自有记录。公开路线文档标注这次首段有 5 个战斗点。不能把该证据扩展到后续路段、候选文件变体、今天的订阅文件或整条路线。

**当前实现但尚不足以宣称完整实机通过**：两段 `material-route-session`、固定安全区域恢复、战斗切人落地/冷却保护、候选排序、跨文件点位去重、派遣领取和重派验证。路线文档还列出需要完整队伍匹配时跳过不必要编队、安全传送、战斗场景/网络延迟等未验收点。今天应先读订阅路线的当前本机清单和哈希，不能盲用历史 XS 的七个 fight 动作或旧五点首段记录。

**派遣现况**：固定 BetterGI 中 `GoToAdventurersGuildTask.Start(...)` 打开派遣页后调用同步 `OneKeyExpeditionTask.Run()`。后者最多重试两次找“全部领取”，点击后睡眠 1.1 秒，再以 1 秒间隔重试最多三次找“再次派遣”，点击后等待 0.5 秒、按 ESC 并写“完成”。异常只记日志并吞掉。没找到领取按钮时不会检查是无待领取、未完成、未开放还是 OCR/UI 问题。旧 `ExpeditionTask` 有卡片 OCR 和角色选择逻辑，但已标记废弃；其中还留有派遣人数识别 TODO，`重新派遣完成` 也只是循环结束文本。

所以每日领奖解析里“今日奖励已领取”只属于委托奖励。`scripts/analyze_run.py` 将派遣的领取、重派、后状态独立保留为 unknown；`cultivation_full.py` 要求三个派遣字段和布尔证据齐全才会通过完整日常范围。点击日志、ESC、冒险家协会对话选项状态都不能补成成功。

## 可直接复用的社区素材和许可结论

BetterGI 官方文档允许 JS 以 `pathingScript.run(json)`、`runFile(path)`、`runFileFromUser(path)` 运行路径文件；`runFileFromUser` 限定在 `User/AutoPathing`。官方地图追踪文档说明路线依赖小地图定位，支持地表采集/战斗，也明示截图模式、分辨率、地图环境、角色队伍和战斗策略等条件会影响稳定性。因此最小复用应是用户本机订阅路线 + 本仓库已有的受限 `RunMaterialRoute` 入口；不要退回只有 `runFileFromUser` 的无哈希、无单次结果包装路径。

此前的社区只读核对固定 `bettergi-scripts-list` commit `af12cfab667f85b857e1fe69f4ca5f52aa542ca8`，两组候选子树包括 48 个多岛路线和 9 个 XS 路线；这些数是来源目录完整性，不是实际击杀数或收益。旧记录说明 XS 刃连岛文件有 7 个 fight 动作，而早期实机证据是不同的 5 点首段，二者不得混淆。源文件只应由用户在本机订阅和核验哈希。

许可证方面，BetterGI 源码仓库采用 GPL v3；本项目扩展模块注明 GPL-3.0-only。社区路线列表的公开 GitHub 仓库页面未给出可确认的仓库级 license，单个路径文件也没有独立许可声明的证据。保守复用方式是：保留作者/来源链接，在本机 BetterGI 订阅/白名单外部使用，仓库只保存去标识路线元信息或本机忽略目录数据；不要复制/再发布第三方 JSON，除非确认对应作者的许可。不能只因为 BetterGI 本体 GPL，就推定脚本列表里每份用户路线都采用 GPL。

## 派遣最小补齐建议（待 root 协调后实现）

保留现有任务的凯瑟琳导航和领取/重派交互，补一层独立原生结果接口，不从旧文本拼成功。建议新增一个聚焦的验证入口，接收 `runId`、期望范围/超时，返回并落盘：

1. 操作前读取五个槽位的状态（进行中/完成/空闲）、可见角色及倒计时；连续两帧一致才接受初始状态。读不出完整五槽时停止在 unknown，不点击。
2. 对已完成的槽位执行领取；对空闲槽位是否重派按用户既定策略操作。每次点击后等待 UI 稳定，禁止超时后自动再点同一领取/重派动作。
3. 重新读取五槽两帧：角色/槽位、派遣进行中状态及新的倒计时均应匹配预期。通过时将 `collectionStatus`、`reassignmentStatus`、`postStateStatus`、采集时间及原始机器证据写入独立报告，并发对应的 `[AUTO_GAME_EVENT]`。明确没有到期派遣或没有空槽，须用观测状态返回 `skipped`/`not-needed`；这些值不能伪装成 `completed`。
4. 在 JS/Python 验证层仅接受本 run 的一致原生事件、报告身份、双帧记录和三项 `completed`。部分领取、部分重派、异常和不完整截图维持 partial/unknown；只有确认未发生任何点击的 no-attempt 审计才可安全重试。

最低改动范围应集中在 BetterGI 的派遣任务/暴露给 JS 的 `AutoPathingScript` 包装、`AutoGameMaterialRoute`（或一个新命名 dispatch 脚本模块）、`analyze_run.py` 证据映射与 `cultivation_full.py` 现有门槛。不应改普通每日奖励“已领取”的含义，也不应让工作流把失败后的原操作自动重放。需要新增 C#/JS 文件或改补丁前，先把该提案交 root 汇总协调；本轮没有实施。

## 刷新语义与当日选路

路线调度统一使用 UTC+8 的 04:00 边界，以它计算 `gameDate`、用户授权和 30 分钟日预算，满足“当日有效总产出优先”。但点位资格另存并带 `lastObservedAt`、`lastAttemptOutcome`、路线实际坐标范围/候选 ID；04:00 到点只进入新调度日，不清除失败或 unknown，也不声明敌人已刷新。

公开社区资料的说法并不完全统一：HoYoLAB 用户文章称图鉴“Elite Enemies”的精英每日在服务器 04:00 重置，其他怪通常约 12 小时；社区百科还提醒普通怪群若与精英同组会跟随精英日重置，且 12 小时机制仍有假说性质。野伏众常被图鉴放在 Easy/common 类，但这不足以证明候选路线的每个群都按同一时钟刷新。因此：

- 不能把“普通精英 12 小时”当既定规则；名词上它还混淆了普通敌人与图鉴精英。
- 根流程继续遵守统一 04:00 调度边界，不根据旧 checkpoint 自动认定当前可打。
- 选路时优先使用当前新帧/地图实观确认仍存活且未被尝试的点位；已成功点位是否可再次计入本游戏日，需要 12 小时生效证据或直接观察新敌人。所有未解决的 `unknown` 保留排除，即使日期变了也不盲目重放。
- 若以后支持 12 小时二次刷取，应在独立证据中按点位类别记录击杀时间和刷新观察，并单独核算 04:00 游戏日预算；没有点位级证据就维持保守的一日一次策略。

## 本轮公开资料

- [BetterGI 脚本调用文档](https://www.bettergi.com/dev/js/otherscript.html)：路径 JSON、普通文件和用户 `AutoPathing` 文件入口。
- [BetterGI 地图追踪说明](https://www.bettergi.com/feats/autos/pathing.html)：小地图定位、设置、队伍/战斗和环境限制。
- [BetterGI 官方源码：OneKeyExpeditionTask.cs](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/AutoSkip/OneKeyExpeditionTask.cs) 与 [GoToAdventurersGuildTask.cs](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Common/Job/GoToAdventurersGuildTask.cs)：导航与点击流程。
- [bettergi-scripts-list 公共路线仓库](https://github.com/babalae/bettergi-scripts-list/tree/main/repo/pathing)：社区路线来源；路径文件许可需逐作者确认。
- [HoYoLAB 社区文章：精英与普通敌人刷新说明](https://www.hoyolab.com/article/8441222) 和 [Common Enemy 社区百科](https://genshin-impact.fandom.com/wiki/Common_Enemy)：都是社区资料，足以提醒分类差异，不构成对本机具体路线刷新时间的实证。

本文件是技术复用建议，不是今天路线/派遣已通过实机验收的声明。已知或未知材料结果、实际耗材、网络与派遣槽位均须从本次授权的独立观测中读取。
