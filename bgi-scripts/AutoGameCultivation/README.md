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
