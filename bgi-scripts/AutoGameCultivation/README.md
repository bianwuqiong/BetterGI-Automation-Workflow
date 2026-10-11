# 培养材料插件

本插件供工作流在已授权范围内调度。默认 `scan` 只操作角色/背包界面并保存报告，不领奖、不合成、不升级、不发通知。离线测试不会打开游戏。

本机 BGI 0.64.2-alpha.2 已具有所需接口；插件本身尚未实机验收。保持固定DLL，先执行扫描验证，再逐个验收目标秘境和普通boss。普通boss默认关闭，需要显式允许和本机验收标记；材料路线、周本、地脉和升级保持不可执行，会在报告中明确标出。

## 输入

由工作流传入 `settings.runId`，没有自动生成runId。仅允许1-80位字母、数字、下划线、连字符。`settings.mode` 为 `scan` 或 `execute`，默认scan。`settings.targetConfigJson` 示例：

```json
{"characterName":"梦见月瑞希","targetLevel":90,"talentTargets":{"normal":9,"skill":9,"burst":9},"includeEquippedWeapon":true,"weaponTargetLevel":90}
```

通过角色档案读取当前进度和装备武器。要求三项天赋的命座标记完整，将固定+3还原为基础等级。装备武器缺失、没有静态规则或档案不一致时停止，不猜测。

`settings.policyJson` 默认 `{}`，可包含：

```json
{"maxSteps":1,"maxMinutes":15,"allowDomain":false,"domainValidated":false,"domainSingleAttemptVerified":false,"domainResin":"original","originalResinBudget":null,"condensedResinBudget":null,"reserveOriginalResin":40,"actualOriginalResin":null,"resinObservedAt":null,"domainPartyName":"","strategyName":"","allowBoss":false,"bossValidated":false,"bossPartyName":"","bossTimeoutSeconds":180,"allowRoutes":false,"allowWeekly":false}
```

`maxSteps` 为1-20，`maxMinutes` 为1-15。所有允许项默认false。秘境执行必须同时允许、完成目标机器/队伍/关卡实机验收，并由runner确认 **全局 AutoDomainConfig.ReviveRetryCount=1**：BGI把该值作为尝试次数，0意味着不运行。插件不修改生产全局配置。

原粹预算单位是树脂点数，浓缩预算单位是颗；它们只是消费上限，不能证明账户实际持有量。预留原粹大于0时，执行每一步前都要求120秒内的 `actualOriginalResin` / `resinObservedAt` 观测，且实际余量扣除已确认调用预算与本轮20（boss40）后仍达到预留值。观测过期或缺失就阻止原粹任务；不会将预算当成实际库存。请在外部runner保留资源观测来源证据。

普通boss只有 `allowBoss=true && bossValidated=true`、`bossPartyName`明确、相关材料fresh exact、原粹剩余预算至少40才可执行；`bossTeamName`可作为队伍别名，但不能与bossPartyName冲突。首领名来自固定材料定义，同时必须位于固定BGI支持白名单，不能由策略输入任意首领名。默认不自动将未验收状态改为true。每次最多一领奖，死亡重试0，须臾/脆弱关闭，战斗Timeout120-180秒；总调用取消上限也不超过该时长与流程剩余时间。boss使用原粹，不能用浓缩替代。

## 输出与证据

只使用LimitedFile相对路径 `record/<runId>.json`；该目录不进入Git。不读取或保存UID、Cookie和账号信息。写入返回true并逐字回读成功后才发出 `[AUTO_GAME_EVENT]`：

```json
{"task":"培养材料","runId":"由工作流指定","status":"success","evidenceVerified":true,"mode":"scan","readOnly":true,"reportRelativePath":"record/由工作流指定.json","completedSteps":0,"targetReached":false}
```

scan success仅表示所需、受支持的档案和材料扫描报告完整写入；材料已准备完毕、实际升级和全部资源需求都没有因此被确认。缺key、-1、-2始终写为 `unknown`，不会填0，报告依然导出但event为unknown。摩拉网格无法可靠读取，排除在受支持扫描之外并显式manual。基础升级经验、升级摩拉尚未计算；突破与天赋摩拉只是不完整的子总量。

报告 `schemaVersion=1` 包含runId/mode/target/profile/inventory/plan/blockers/warnings/steps/status/readOnly。inventory以材料ID为key，每项为 `{name,count,status,reason?}`；目前只产生exact或unknown，执行也不接受lower_bound。实际数量不变成合成等值。`plan.crafting.suggestionsOnly=true,executed=false`，按基础3:1配方推导建议，不执行、不扣库存、不提前计入角色随机额外产出。

execute复用有界普通boss与单轮秘境，已允许的boss优先。秘境每次 `DomainRoundNum=1`，明确一种树脂；原粹20次数字段=1，其余次数全0，或浓缩次数=1，其余全0。树脂优先级先复制为独立.NET List，避免Clear污染全局配置。脆弱/须臾、分解、制作浓缩均禁用。任务启动前先写入unknown状态checkpoint；任何崩溃/取消都不可当成功重放。达到步数/时间/预算边界停止，任务自身使用与BGI全局停止链接的取消令牌和剩余时间上限。

每步领奖前后重新扫描该材料系列和其合成低阶材料；所有数量exact、无减少、至少一种增长，才将step记success。任务返回的奖励字典不累加进库存，库存差为唯一收益台账。未确认增长、任一后置识别缺失、任务异常即unknown并停止，不重放。execute success只确认此次有界步骤，`targetReached`始终false；剩余的手动材料和缺数据继续显示blockers。

## API与测试

BGI接口：`characterDevelopmentTask.GetCharacter`、`dispatcher.RunCountInventoryItemTask`、`AutoDomainParam`、`dispatcher.RunAutoDomainTask`、`AutoBossParam`、`dispatcher.RunAutoBossTask`、`dispatcher.GetLinkedCancellationTokenSource`、`file.CreateDirectory/WriteText/ReadTextSync`。boss报告step使用type=boss、bossName、maxClaims=1、成本40、before/after/delta，并记录静态mapping与安全参数证据；不会叠加奖励字典。

```powershell
node --test tests/safety.test.js
```

测试使用fake BGI和内存文件，不消费资源。所需上游计算核心与许可证见 [UPSTREAM.md](UPSTREAM.md)。

## 独立只读资源覆盖诊断

```powershell
python scripts/workflow.py run --task '培养材料' --cultivation-mode scan --cultivation-resource-check --no-delay
```

此开关只运行一个scan节点，与树脂探针、画质验收及execute互斥。宿主生成临时零预算、禁用资源执行policy，不修改本机配置或消费授权。先调用 `ReadMoraSnapshot('{}',token)`，再以固定 `category=weaponExperience` 请求104011精锻用杂矿、104012精锻用良矿、104013精锻用魔矿。Mora原生读取会移开遮挡图标的指针；静态弱模型分数不能替代当前实机核验。

报告保留独立 `metadata.diagnostic=resource-coverage-only` / `resourceCoverage`，包括全部原始双帧、模型身份/分数、完整整数、选中标题和数量区域证据。Python与JS都重新核验；任一未知则整体unknown，未知数量始终null，不补0。全部exact的success只说明这一轮资源读取覆盖，不表示完整培养材料扫描、等级内经验、总升级成本或实际升级完成。`upgradeBudgetComplete=false`、`levelExperienceObserved=false`、`targetReached=false`。

这些数量不进入普通 `inventory`，正常扫描的202 excluded/manual保持原义。此只读入口也不解除任何paid unknown，不允许重放未确认消费。原始报告只存本机private `record` 和该run日志档案；公开测试只使用合成数据。

## 独立周本四库存只读诊断

```powershell
python scripts/workflow.py run --profile cultivation --task '培养材料' --cultivation-mode scan --cultivation-weekly-inventory --no-delay
```

仅读取 `113060` 残火灯烛、`113061` 丝织之羽、`113062` 否定裁断和 `113021` 异梦溶媒；`101016` 不属于此请求。入口固定调用 `dispatcher.ReadWeeklyConversionInventory('{}',linkedToken)`，JSON按UTF-8字节计最多1MB。与execute、树脂/资源/天赋诊断、画质验收、圣遗物/路线/战斗演练及其他节点互斥；临时执行开关false、预算0、最多3分钟，不改本机配置与授权。

JS与Python分别重新核验原始模型名称/分数≥.75、实际分类标题、完整选中材料名、原始整数与检测器OCR一致、四边2个缩放像素、四侧选中边框的实际像素和位置、独立新鲜双帧、统一客户端、当前读取时间范围及主界面恢复双帧。报告保留 `metadata.diagnostic=weekly-conversion-inventory-only` 和 `weeklyInventory.nativeObservation` 全部原始证据；普通17材料扫描和普通 `inventory` 保持原义。任一项不足，摘要全部保留unknown/null，不把未见堆栈填0，不通过通用网格库存替代证据。

success只表示本次四库存读取完整；`targetReached=false`、`completedUpgrades=0`。此接口不提供转换、配方或费用推测，也不执行消费或解锁未知消费重放。原始报告保存在本机private record/run档案，公开测试使用匿名合成数据。

## 单项天赋下一等级只读预览

```powershell
python scripts/workflow.py run --profile cultivation --task '培养材料' --cultivation-talent-preview --talent-type elemental-skill --no-delay
```

`--talent-type` 只允许 `normal-attack`、`elemental-skill`（默认）、`elemental-burst`，一次只读一项。目标来自本机 `cultivation.json` 的完整 `target.characterName`，由本run生成参数冻结；换角色重新读取，旧角色报告不能改名字复用。宿主复用互斥、游戏接管、画质与退出；新开关与execute、其它只读探针、画质验收及其它节点互斥，临时执行开关为false、预算0、最多3分钟，不改私人原配置或授权。

调用 `dispatcher.InspectTalentUpgrade(characterName,talentType,linkedToken)`，返回JSON上限1MB。原生只打开已识别的角色/天赋详情和下一等级预览，读取材料说明后以已识别页面的Escape恢复世界；从不点击最终确认。报告 `metadata.diagnostic=talent-upgrade-preview-only` 和 `talentPreview.nativeObservation` 保存全部原始角色三帧、详情双帧、预览双帧、材料tooltip、实际货币身份与世界恢复双帧。JS和Python分别重算fullname/type、显示与基础等级和固定+3证据、基础等级→下一等级、真实完整整数及ROI边缘、实际材料名称/持有数量与Mora模型分数，不把verified布尔当成全部证据。

材料tooltip的“培养需求”分母通常是培养目标合计，只核对持有分子；下一等级需求始终取实际升级popup，不能把合计分母替代成本。OCR将斜杠看作1时，只有原生实际斜杠像素几何与独立左右完整整数证据可以通过，不改原文字猜数字。当前Mora身份使用该popup实际模型≥0.75；若只有弱模型或余额常识，仍为unknown，不能伪造一个未读取的完整名称Mora tooltip。

全部独立证明齐全才返回诊断success。任何未知保留原始证据、`costs=null`；普通17类材料扫描和202 excluded不受影响。无论预览是否成功，都保持 `completedUpgrades=0`、`targetReached=false`，资源消费步骤为空，不解除圣遗物unknown或授权实际升级。

第17版还支持明确选定的实际背景货币区域：`coinVariant=real_background_padding_8_reference_53`，区域为(845,791,53,53)，旧(853,799,37,37)的名称/分数/区域仍完整保存在initialCoin字段。主区域仍必须真实Mora模型≥0.75，不能择两次识别的最高分；旧区域若高置信识别为其它货币则拒绝。旧14/15/16的37区域格式继续支持。

数量的新裁剪必须可独立重建：Mora只接受初始固定(903,797,275,55)中唯一完整ratio detector实际行，四边加 `Math.Round(12*s)`并限制在秘境预览中部；材料只接受真实父count行横pad20/竖pad5后与实际材料card相交的区域，初始pad8读取原样保留。JS和Python重新计算框、全部初始原行和同帧时点，最终完整raw与detector整数必须一致，2px边缘规则不降低。初始失败不能替代最终成功；初始高置信数量冲突仍拒绝，不从已知常见费用补值。

`privateCapture`仅保存完整预览的原生无resize无合成PNG和诊断元数据，不替代货币/数量/新鲜度证明。弱模型或不完整原行仍unknown；公开测试均是合成数据，不能当作第17版实机已验收。

第18版分离数字只接受明确 `splitRegionMethod=slash_vertical_band` / `splitVerticalPaddingReference=6`：从实际斜杠glyph上下各扩 `max(3,Math.Round(6*s))` 个自然像素，并与原count框相交。JS/Python精确重算两侧绝对region；4倍OCR投影后的完整整数必须四边≥2*s。旧无方法字段的数据仅按满高legacy区域核验，不把新带宽猜成旧模式。原斜杠140/-0.75/至少6墨点阈值不降，整行错误文字不替换；左右OCR失败时原生真实slash/regions/raw仍保留，但费用仍null/unknown。

四库存的角色养成页只新增精确完整头名“养成道具”，与旧“角色培养道具”均需唯一且两个独立帧的实际文字一致。贵重道具仍仅接受“贵重道具”；不做contains/模糊标题，不加入未审查别名，也不自动确认过期道具通知。其余同tab、完整标题/数量、实际模型、选中边框像素与新鲜时点标准不变。
