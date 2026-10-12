# 下一步复用核对（2026-10-12）

本轮只读当前公开源码、官方文档与本项目源码；没有启动游戏、BetterGI、构建或 testhost，也没有修改执行器、配置或授权。公开文件不包含本机库存、运行记录或私人路径。结论是限定检索范围内的源码判断，不是对所有社区脚本的不存在证明，更不是实机验收。

## 直接结论与最小收益

**普通培养材料合成已有完整调用链，优先补它的证据，不另写操作脚本。** 本项目已经接入上游 `CraftMaterialTask`，有单次导航、材料名确认、数量调整、取消与恢复包装；JS 又独立验证材料链库存变化。当前缺的是实际配方成本和独立摩拉前后证据，`operator.js` 明确保留 `moraCostStatus=unverified`。不能把已有材料净变化扩大为摩拉成本已核验，不能仅打开 `craftingValidated` 就宣称本机完整验收。

**角色/武器/天赋升级与周本转换没有找到可直接接线且独立验收的公开执行器。** 官方角色养成 API 是读取；社区“角色养成一条龙”明确只刷材料，不升级、不合成。派遣最新版仍是领取/重派按钮点击，缺完整槽位和倒计时观察。此前派遣未知边界仍成立。

建议 root 按依赖推进：先验收现有严格天赋预览与具名库存/Mora读取；再为已有材料合成补实际成本与同run前后证据；升级消费桥保持关闭直到独立after证据与授权绑定成立。不要用新版上游整体替换固定引擎，也不要重复实现已存在的导航、计数、角色筛选、材料计算或3:1核验。

## 本次固定的公开版本

通过 GitHub 公共 commits/main 与完整 recursive tree 响应确定，两个树均 `truncated=false`：

| 来源 | 本次固定 SHA | 提交时间（UTC） | 范围 |
| --- | --- | --- | --- |
| babalae/better-genshin-impact | `d533eab0295b9668daa0316fe18ffbc1f978af19` | 2026-10-12 06:32:42 | 全树路径；候选任务与脚本桥源码 |
| babalae/bettergi-scripts-list | `3fc1ad12c4666482083bf37cf0e89d87604fbeef` | 2026-10-11 16:12:50 | 全树路径与JS插件目录；重点候选README/manifest/main |

本项目保持 `NOTICE.md` 指定的 `d8c0aa238a949d7d74bfe5087f3a48e39771575a` 加 `SOURCE_PATCH_SEQUENCE_2026-10-11.json` 完整1..25。新增两层修复进程身份查询与已知背包页导航，没有整体换用新版引擎。新版官方代码已使用 `InputHub.Foreground`，本机固定源码仍使用其既有输入结构。不能把最新文件直接覆盖进本机分支而忽略完整补丁与输入依赖。

## 已经存在的材料合成链

本项目具体调用：

```text
AutoGameCultivation/main.js::api.runCrafting(job)
  -> dispatcher.RunCultivationCraftTask(materialName, craftCount, craftingCountry, token)
  -> CultivationCraftTask.Start(name, quantity, country, callerToken, globalToken)
  -> GoToCraftingBenchTask.GoToCraftingBenchOnce(country, ct)
  -> new CraftMaterialTask(name, quantity).Start(ct)
  -> RestoreMainUi(ct)
AutoGameCultivation/core/operator.js -> before/after inventory scan
AutoGameCultivation/core/safe.js::verifiedCraft(before, after, task, result)
```

`CultivationCraftTask` 已拒绝所有树脂名称，只支持蒙德/璃月，数量1..999，使用同一个链接取消令牌；只调用 `GoToCraftingBenchOnce`，不使用带两次重试的普通导航包装。返回仅含任务结果、材料名、目标/实际设定量和世界恢复，不暴露上游推定 `Rewards` 为库存证据。

`candidateCrafting` 已在 `allowCrafting && craftingValidated` 时才允许候选执行；只取链中下一阶建议。`verifiedCraft` 已要求完整精确库存、原料 `-3*q`、产物增加 `q..2*q`、其他链项不变，且原生身份/数量及 `MainUiRestored` 全部匹配。返还原料导致不符合3:1时保持unknown，不能自动再试。此核验目前覆盖材料链和恢复，不证明摩拉实际余额或配方费用。

**最小改动落点**：复用现有 `ReadNamedCultivationInventory`、`ReadBoundMoraSnapshot` 以及 JS `core/named-inventory.js` 的原始证据校验给单次合成before/after服务；另补选中配方的具名原料/摩拉成本原始预览与提交前冻结，不改 `verifiedCraft` 的现有成功含义来掩盖缺项。材料成本、摩拉成本、库存实际变化和任务点击分别留证。先做只读配方预览，不能把 `CraftMaterialTask.Start` 当预览接口——它直接提交消费。

当前官方 [CraftMaterialTask.cs](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/Common/Job/CraftMaterialTask.cs) 可复用的方法：

- 构造 `CraftMaterialTask(string materialName, int targetQuantity, string? materialType=null)`，`Start(CancellationToken)` 返回 `CraftMaterialResult`。
- `TrySelectMaterialType` 使用 `BvPage.GetByText` 筛选；`TryFindAndSelectMaterial` 使用 `GridScreenName.Crafting` + `ItemIconRecognizerFactory` 找图标，再 `ConfirmSelectedMaterial` 检查详情名。
- `SetCraftQuantity` 读最大量、拖滑块、加减修正、最后再读实际数量；可复用为受限批量设定，不能独立证明实际产量。
- `SubmitCraftAndClaimResult` 点击合成/确认，再 `RecognizeCraftRewards`；后者识别空或异常会 `CreateDefaultCraftRewards(actualQuantity)`，`Start` 仍 `CreateSuccess`。该返回值**含推断回退**，不符合本项目“未知不升成功”要求。现有包装已避免把它当库存，本轮无需重新修同一个问题。

官方 [Dispatcher.cs](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/Core/Script/Dependence/Dispatcher.cs) 没有本项目的 `RunCultivationCraftTask`、具名库存、严格预览包装；它们是现有GPL扩展，不能误写为官方现成JS API。官方 [GoToCraftingBenchTask.cs](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/Common/Job/GoToCraftingBenchTask.cs) 的导航与浓缩合成入口不同，普通材料只应复用导航，不调用 `GoCraftResin`。

## 升级：已有读取与计算，缺实际执行验收

官方 [CharacterDevelopmentTask.cs](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/CharacterDevelopment/CharacterDevelopmentTask.cs) 提供 `GetCharacter(characterName, categories)` 和 `GetMultiCharacters(characterNames, categories)`；分类是 `属性;武器;天赋`。状态机读取等级、装备和天赋，最终解析要求连续三帧一致。它没有实际角色经验投入、突破提交、武器强化提交或天赋确认入口。复用角色定位与识别可以减少工作，但不能把读取成功当升级成功。

社区 [角色养成一条龙 README](https://github.com/babalae/bettergi-scripts-list/blob/3fc1ad12c4666482083bf37cf0e89d87604fbeef/repo/js/角色养成一条龙/README.md) 明确只刷角色突破、天赋书、技能和武器材料，不升级、不合成；且提示未刷完不要使用材料。这与本项目需要动态重读已消费库存的协议不同，不能接其持久completed_tasks作为目标完成证明。

[RoleExperienceCalculation manifest](https://github.com/babalae/bettergi-scripts-list/blob/3fc1ad12c4666482083bf37cf0e89d87604fbeef/repo/js/RoleExperienceCalculation/manifest.json) 是经验计算，main包含识别和计算，没有实际角色升级执行；[HolyRelicsUp manifest](https://github.com/babalae/bettergi-scripts-list/blob/3fc1ad12c4666482083bf37cf0e89d87604fbeef/repo/js/HolyRelicsUp/manifest.json) 是圣遗物批量强化，不是角色/武器/天赋升级。较宽泛的 FullyAutoAndSemiAutoTools main也没有找到所需升级、周本转换或派遣倒计时协议。

本项目已有GPL培养计算与静态材料数据、角色读取、严格单天赋预览和隔离开发的after核验；先复用这些。目标应逐项核验真实角色等级、基础天赋（排除+3加成）、当前装备武器身份/等级。材料够或预计够、脚本名“一键养成”、点击完成、返回世界均不能独立使 `targetReached=true`。

## 周本转换与派遣：复用导航，不继承成功语义

本次完整官方树没有独立周本材料转换任务，社区候选目录也没有找到具名配方、异梦溶媒与输入/产物/Mora前后证据齐全的转换接口。已有 `ReadWeeklyConversionInventory` 只读四个固定库存，不做配方、消耗或转换；普通3:1 `CraftMaterialTask` 没有选择转换标签和同Boss输入变体的协议，不能传一个周本材料名就当支持转换。

派遣仍可复用 [GoToAdventurersGuildTask](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/Common/Job/GoToAdventurersGuildTask.cs) 的凯瑟琳导航及 [OneKeyExpeditionTask.Run](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/AutoSkip/OneKeyExpeditionTask.cs) 的按钮定位素材。后者重试找领取按钮，点击领取后重试找再次派遣，按ESC记完成，异常被吞；没有槽位读取、人物身份、倒计时、领取产物或重派后证明。

[ExpeditionTask](https://github.com/babalae/better-genshin-impact/blob/d533eab0295b9668daa0316fe18ffbc1f978af19/BetterGenshinImpact/GameTask/AutoSkip/ExpeditionTask.cs) 标记Obsolete；`GetCharacterCards` 是角色选择列表的OCR解析，不是派遣五槽读数。源码仍有利用探索限制计数的TODO，没有倒计时解析。[archive/js/Expedition/main.js](https://github.com/babalae/bettergi-scripts-list/blob/3fc1ad12c4666482083bf37cf0e89d87604fbeef/archive/js/Expedition/main.js) 是固定点击与sleep，最后只写委托领取日志，也不能补派遣验收。

最小派遣推进仍是新建**纯只读**槽位观测：当前页布局定位、完整可见槽位/人物/进行中或完成状态/倒计时、独立两帧和原始截图证据。不启动旧自动派遣作为“读槽位”的办法；若需要切地区/卡片才完整读取，导航与资源按钮严格分开。无法完整读取则保持unknown。之后再围绕同run初始/后状态包裹现有交互，不能先把“完成”日志接入父流程成功字段。

## 不应新增的执行范围

现有 `safe.js::createBossParam` 已设置单次、禁止脆弱/须臾与复苏重试；boss材料已经够时应保留缺口判断而跳过，不因社区批量脚本支持更多boss就扩刷。圣遗物已有目标套装与秘境映射、独立scope/预算与真实奖励统计；新目标的材料合成/升级研究不扩大其消费授权。任何只读成本预览也不允许补树脂、原石补充或消费转换材料。

## 官方文档与许可边界

官方 [任务调用](https://www.bettergi.com/dev/js/dispatcher.html) 说明通用计数未找到为-1、数字失败为-2，多物品缺键；缺键/失败不能补零。文档也列出 `AutoBossParam`/`AutoDomainParam` 资源设置，新对象会读本体默认值，须继续复用本项目实际参数回读与单种树脂列表保护。官方 [自动剧情](https://www.bettergi.com/feats/timer/skip.html) 描述橙色派遣/委托选项触发自动化，不承诺完整槽位或独立领取核验。网页是本次查阅版本，没有声称其内容具有Git提交固定性。

官方BetterGI是GPL v3；复用任务/识别源代码应保持作者、GPL与修改声明，并依 `NOTICE.md` 维护精确对应源码。脚本列表的GitHub公开repo元数据本轮 `license=null`，并非证明每个子脚本都无许可；有些其他子目录单列LICENSE，但上述候选没有确认适用许可。未明确许可前只保留来源链接、研究函数与行为，不复制或再发布JS/路线/图片。用户本机订阅与第三方文件再分发是不同操作。

本文件没有更改任何 `executionEnabled`、资源额度、unknown账本、旧证据或目标完成状态。
