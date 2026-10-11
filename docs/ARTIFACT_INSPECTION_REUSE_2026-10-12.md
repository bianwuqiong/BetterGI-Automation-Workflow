# 圣遗物明细识别与装备复用核对（2026-10-12）

本说明只读核对工作流固定 BetterGI 源码、相关补丁、当前官方源码和 BetterGI 官方文档。没有启动游戏/testhost、没有调用自动分解或强化，也没有修改共享源码。本页不含账号、库存、实机掉落明细、run ID、截图或凭据。

固定工作流源码基于 BetterGI `d8c0aa238a949d7d74bfe5087f3a48e39771575a` 加本仓库有序补丁；下文官方 `main` 源码链接作为接口参考，主机执行仍须对照固定后的本机源码。

## 结论

现有引擎已经有可复用的圣遗物属性卡片 OCR、图标质量候选和网格扫描骨架。它们分散在自动分解、奖励识别和图标导出中，没有组成一个只读背包明细 API。

当前秘境奖励路径最终返回 `Dictionary<string,int>`，按名称累计数量。扫描途中 `RewardResultRecognizer` 确实暂时保存了每张卡片的图标匹配质量，但在 `CreateSummary()` 聚合时只按名称分组；主词条、强化等级、槽位和装备角色都没有进入这份结果。因此，只凭已完成刷取和该字典中的圣遗物名称/数量，不能确认每件是四星还是五星、是否有目标主词条或已装在目标角色上。也不能仅凭模型 CSV 中某行标有 quality 5，就把那行当作本次掉落证明。

**最小复用顺序**：先保留真实奖励卡片已有的 `ItemRecognizer.Match` 输出（名称、`quality_level` 候选和分数），不要再造一套图标 OCR；再以当前背包 `GridScreenName.Artifacts` 为只读枚举骨架，把已存在的 `GetArtifactStat()` 复用于被选中卡片，补回已经 OCR、但当前未放入模型的槽位文字。给输出补充有界身份、观测帧和证据路径。套装与装备角色的可信映射仍须补齐，未补齐时输出 `unknown`。

## 已存在且可以复用的能力

| 代码 | 当前能力 | 对只读盘点的限制 |
| --- | --- | --- |
| `AutoArtifactSalvageTask.GetArtifactStat(Mat, IOcrService, out allText)`；`ArtifactStat` / `ArtifactAffix` | OCR 详情卡片的 `Name`、主词条/数值、副词条/数值、未激活副词条标记、`Level`。它还读了卡片的套装/部位 (`type`) 文本，并把识别文本放在 `allText`，但 `ArtifactStat` 没有暴露该文本字段。 | 类的 `Start()` 是自动分解流程，包含快速选择、分解确认等输入。将来只能复用详情解析方法或抽出纯解析器；绝不调用完整 `Start()`。现有模型没有星级、位置/slot、set ID 或装备角色字段。 |
| `Common.Reward.RewardResultRecognizer` → `ItemRecognizer.Match` → `RewardItem` | 对秘境奖励页的真实图标运行视觉匹配；中间结果含 `Name`、`QualityLevel`、`Quantity`、`PositionIndex`。图标分数低于 0.75 会跳过该奖励。翻页去重也比较名称、质量和数量。 | `RecognizedReward` 是私有类型；公开的 `RecognizeMultiPage()` 返回 `Dictionary<string,int>`，`CreateSummary()` 只按名称分组，质量和卡片序号被丢弃。主词条/等级从奖励条带本身并未识别。当前工作流事件沿用名称/数量摘要，不能事后补回逐卡详情。 |
| `Common.Job.ItemIconRecognizer.ItemRecognizer.Match(Mat)` / `ItemIconCandidate` | 候选携带名称、视觉分数和 `QualityLevel`；圣遗物候选按 `(Name, QualityLevel)` 分开比较。原型从运行时 `Assets/Model/ItemV2/item.csv` 读取 `item_name`、`item_class_id`、`quality_level`、`embedding`。 | `Recognize()` 只返回名称；`IItemIconRecognizer` 也只公开字符串。CSV 的 `quality_level` 是某个静态图标原型的标签，不是单次掉落事实。解析器只检查 `item_class_id` 是否以 `relic:` 开头来判定“是圣遗物”，没有将原始 `item_class_id` 返回到候选或工作流。必须记录**本次实际图标匹配**的质量候选、得分/阈值及对应截图观测，不能仅扫描 CSV 就宣称掉落星级。 |
| `GridScreen` / `GridParams.Templates[GridScreenName.Artifacts]` | 扫描背包圣遗物网格，按页枚举实际图标矩形；`GridScreenExtensions.GetGridIcon()` 提供图标裁切。`AutoArtifactSalvageTask.OpenInventory(GridScreenName.Artifacts, ...)` 负责导航到背包页。 | `GridScreen` 文档明确末页可能重复，要按实际项目身份去重。`OpenInventory` 只是导航 helper；调用任何自动分解任务都超出只读范围。需要选中一项查看属性时，只能点背包普通物品详情，不能进入“分解”页。 |
| `GetGridIconsTask.GetStars(Mat)` | 已有单独的简易星星颜色/连通域计数；`GetGridIconsTask` 可在当前背包逐项点击详情并把星数后缀附到导出的图标名。 | 这是诊断/导出任务，会遍历点击并写 `log/gridIcons` PNG；星数使用颜色轮廓计数，没有独立置信度和两帧稳定证明。可复用纯星星解析器思想，不能把任务本身当作可直接用于正式只读盘点的结构化 API，也不应留下未经审阅的私人图片。 |
| `ArtifactSetFilterScreen` / 分解的 `artifactSetFilter` | 操作游戏内套装筛选网格；用套装图标识别取得对应花名并选择所含套装。 | 它适合把库存限定到一个已知游戏内筛选项，不会给每件物品返回 set ID。名称/图标过滤不能单独证明完整装备集合或该件实际归属。 |
| `QuickEnhanceArtifactMacro.Done()` | 快速强化宏，固定坐标在当前界面依次点按钮。 | 它没有读目标、星级、主词条、消耗、强化结果或前后等级；不能作为自动培养升级接口。当前没有发现专用的圣遗物装备/替换数据接口。 |

`CountInventoryItem` / `dispatcher.RunCountInventoryItemTask()` 扫描图标并把数量按字符串名称合并。它适合可堆叠消耗品计数，不是带星级、词条与持有者身份的圣遗物清单：接口结果无法区分同名不同稀有度或多件独立圣遗物。

## `item_class_id` 与质量：什么能证明什么

官方代码的 `ItemRecognizer.ParseIconPrototype` 从 `item.csv` 独立读取 `item_class_id` 与 `quality_level`；仅 `classId.StartsWith("relic:")` 表示原型属于圣遗物，再把 `quality_level` 作为候选质量。比较时，圣遗物候选按名称和质量分组，每组留最高分原型，然后将全部候选按分数排序。当前候选对象没有原始 `item_class_id` 字段。

因此，这条代码路径确实能从**本次截图匹配**产生一个带分数的质量候选；CSV 中静态行的质量标签本身不证明本次卡片是什么星级。需要把实际图片匹配结果与截图观测关联，低于现有 0.75 匹配阈值的结果留作 unknown；最好在背包选中详情后，再用独立星级视觉读数复核。若候选模型、CSV 或模型版本无法绑定/解释，则不能把候选质量提升为 verified。

固定源码目录不包含运行时 `ItemV2/item.csv` 数据文件，所以本次没有核查目标物品的真实 CSV 行，也不能断言特定 `item_class_id` 是否跨稀有度复用或唯一；能确认的只有解析规则和字段边界。

## 可提交给 root 的最小只读 API 方案

不建议从零重写 OCR。建议新增独立 `ReadOnlyArtifactInventoryTask`，复用固定引擎的网格识别、物品图标模型、详情卡片 OCR 和套装筛选视图。不要构造后调用 `AutoArtifactSalvageTask.Start()`；也不要调用自动强化宏。

1. **逐件枚举**：从 `GridScreenName.Artifacts` 遍历稳定页面。每件记页号/矩形/顺序和所见头像角标状态；末页重复、分页动画、识别失败都保留原因为 unknown，不合并成数量。相邻重复帧应绑定同一网格项目或可见名称/部位/等级等指纹。
2. **星级候选**：将图标裁切送给 `ItemRecognizer.Match`，内部结果至少保留 `Name`、`QualityLevel`、`Score`、模型与 CSV 版本摘要。不要沿用只返回名称的 `Recognize()` 后丢掉质量。将 `GetGridIconsTask.GetStars()` 的颜色计数作为独立交叉证据，但先抽成无 UI/无文件写入的纯图像方法，再加入分辨率、阈值与两帧一致核验。
3. **详情读取**：在普通背包页中选择当前格，复用 `GetArtifactStat()` 的已测 OCR 区域解析名称、主/副词条、等级，并把它已读到的 `typeRoi` 文本解析为受限 slot enum。对同一选择采新帧核对名称、slot、level、main affix 与上一帧一致，结束后确认仍在背包详情页。任何输入点击仅用于选择/取消选择，不执行装备、锁定、强化或分解。
4. **套装和持有者**：套装由经过来源固定的名称→套装映射或游戏自带套装过滤独立确认；过滤视图没命中、项名映射不唯一时保持 unknown。装备角色可先复用网格右上角的角色头像区域（官方文档确认武器/圣遗物格会显示已装备角色头像），但需独立角色图标模型/双帧确认；没有头像/无法映射角色时不要报“未装备”。还可在目标角色的圣遗物栏逐槽重读，独立核实实际持有者。
5. **结构化只读证据**：返回每个观察项的 `name`、`slot`、`setName`、`starCandidate`、`starScore`、`level`、`mainAffix`、`minorAffixes`、`equippedCharacter`、`observedAt`、`observationCount`、`model/csv id`、`confidence/status` 和有界证据文件引用。没有原始图像/原生候选/两帧详情就不允许上层提升状态。单次页面的 `RewardItem` 只作独立对照，不替代背包扫描。

### 之后若允许装备/强化

把读背包与状态变化拆成不同原生任务：第一个只读取；第二个一次只装备一个明确候选。装备前后都读四/五星、套装、槽位和角色当前持有物，只有目标件所有关键信息精确、现槽物品身份和当前主词条同样精确、规则确认目标允许替换时才提交。装备后在两个新帧确认目标件位于对应槽并归属目标角色；未知/矛盾状态立即停止，不能继续替换其它槽。

强化比装备更不容易逆转。只保留当前 Quick Enhance 热键的输入顺序作为 UI 参考，不把它当安全服务。正式强化另需明确消耗上限、目标级别、每一次可见材料/摩拉成本、提交次数以及提交后新等级和词条核验；任何结果未知就不重复点击。此文档没有实施这些调用。

## 来源（均为 BetterGI 官方源码或官方文档）

- [圣遗物分解与 `ArtifactStat` 文档](https://www.bettergi.com/feats/task/artifactSalvage.html)：确认详情 OCR 的公开模型只有名称、主/副词条和等级，筛选后要手动复查/分解。
- [奖励卡片识别器源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Common/Reward/RewardResultRecognizer.cs)：已有单张 `QualityLevel` 中间结果、实际图标匹配分数门槛和名称/质量/数量翻页去重，汇总后仍只按名称计数。
- [图标识别器源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Common/Job/ItemIconRecognizer.cs)、[详情 OCR 与自动分解源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/AutoArtifactSalvage/AutoArtifactSalvageTask.cs)、[`ArtifactStat` 模型](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/AutoArtifactSalvage/ArtifactStat.cs)：分别支持匹配质量候选、解析属性卡片及明确标出当前模型未携带的字段。
- [网格图标导出任务源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/GetGridIcons/GetGridIconsTask.cs) 与 [Grid 图标裁切源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Model/GameUI/GridScreenExtensions.cs)：显示已有读星与图标裁切方法，但前者逐项点击并写截图。
- [物品计数任务源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Common/Job/CountInventoryItem.cs) 与 [JS Dispatcher 调用文档](https://www.bettergi.com/dev/js/dispatcher.html)：当前计数返回按名字合并的数量。
- [截取 Grid 图标官方文档](https://www.bettergi.com/dev/getGridIcons.html)：说明物品格右上角会显示已装备角色头像，并列出传统图像分格可能受连接图标和背景影响的限制。
- [快速强化宏源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Macro/QuickEnhanceArtifactMacro.cs) 与 [套装过滤 UI 源码](https://github.com/babalae/better-genshin-impact/blob/main/BetterGenshinImpact/GameTask/Model/GameUI/ArtifactSetFilterScreen.cs)：分别仅是固定坐标强化动作和套装选择器，不是结构化装备/强化接口。

本页是源码复用研究，不表示当前库存、掉落星级、词条、套装归属或角色装备已验证。
