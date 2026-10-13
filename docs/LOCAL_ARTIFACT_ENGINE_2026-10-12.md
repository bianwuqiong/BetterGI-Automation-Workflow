# 单次浓缩圣遗物引擎扩展（2026-10-12）

第五份独立 overlay `patches/local-artifact-engine-2026-10-12.patch` 仅叠加在固定 BetterGI 基线 `d8c0aa238a949d7d74bfe5087f3a48e39771575a` 和既有四份补丁之后。保留原四份补丁内容，不将本补丁叠加到未知源码状态。仍为 GPL v3 的非官方修改版；对应源码由固定基线、四份补丁和本第五份补丁共同组成。

## 原有引擎及最小修改

战斗继续使用 `dispatcher.RunAutoDomainTask(param, token)`。现有 `DomainCombatSafety`、`ZhongliHoldShieldGuard` 已核验 TXT 木偶星超导中的实际桑多涅、八重神子和钟离；用两个独立冷却截图核验刚释放长 E，在约 12 秒或长动作即将跨补盾窗口时刷新。冷却证明战技释放，不证明护盾剩余生命值。单动作长度限制仍为 6 秒。

新增浓缩领奖契约：`DomainRoundNum=1`、`SpecifyResinUse=true`、`CondensedResinUseCount=1`、其余树脂计数全部零、`ResinPriorityList` 仅浓缩树脂、`RequireZhongliShieldCast=true`、`CombatOnly=false`、`AutoArtifactSalvage=false`。战斗策略须为 TXT。浓缩资源完整标签及同行唯一按钮取得新鲜双帧证明后，仅点击一次；复用原受保护单20路径的加载与世界双帧退出验证。提交后异常不能重放，禁止普通领奖或双 ESC 兜底。

原生奖励字典仅为观察，不证明 paid 成功。外层必须读回浓缩库存实际下降 1，并独立验证圣遗物收益；证据不足保持 unknown。

## 限额合浓缩接口

`dispatcher.RunCondensedResinCraftTask(country, maxCrafts, originalResinBudget, minResinToKeep, token)`：国家仅蒙德或璃月；次数 1 至 5；预算和保留树脂均为 0 至 200。复用原 `GoToCraftingBenchTask` 的配方定位、稳定数量、库存变化和返回主界面流程。这个入口不读写 User/OneDragon，不自动重试。培养普通材料合成接口继续拒绝所有树脂名。

返回字段：`Status`（success 或 skipped）、`OriginalResinBefore/After`、`CondensedResinBefore/After`、`CondensedResinCreated`、`OriginalResinSpent`、`MainUiRestored`、`RecipeOriginalResinCost=60`、`RecipeCostVerified=true`、`SafeCondensedCapacity=5`、`CondensedCapacityObserved=false`。独立机器事件 `task=artifact-condensed-craft` 同时提供这些字段的 camelCase 形式及 `evidenceVerified=true`。

限额入口在任何提交前要求三帧稳定的配方原粹库存与确切 `/60` 成本，拒绝 `/40`、历史兼容 `/160` 或 `/200` 和斜杠 OCR 歧义。调用 `(country,1,0,200,token)` 只读检查配方后返回 skipped，不提交消费。容量 5 仅为保守安全上界，未声称从界面读到实际容量；真实合成时还读取三帧界面实际可合成最大数量，并和预算、保留量、安全容量共同约束一次提交数量。成本不同或库存超出安全边界则无提交；unknown 不能自动再次提交。

可选 `AutoDomainParam.ArtifactRunId` / `ArtifactStepId` 提供相应单笔 `artifact-domain-claim` 原生事件。ID 须成对为 1 至 128 位 ASCII 安全标识（字母、数字、下划线、点、冒号、连字符），在任何秘境执行前校验。事件中的 `rewards` 来自真正返回的奖励字典；`evidenceVerified` / `rewardEvidenceVerified` 仅描述非空正整数奖励观察，`resinEvidenceVerified=false`。消费仍以外层独立读回的余额变化核验，空字典保持 unknown。

## 构建与纯测试

```powershell
dotnet build better-genshin-impact/Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj -c Release -p:Platform=x64 --no-restore
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_artifact_engine.ps1
```

测试入口只运行单浓缩、单20、合成边界、现有护盾及普通材料合成的纯逻辑类，排除私人图像。BetterGI 运行时不能启动 testhost，因为共享单实例 IPC。部署也须等待 BetterGI 退出，备份旧可执行文件后替换编译输出，不覆盖 User 或运行配置。离线构建及纯测试不代表本机浓缩领奖、合成或圣遗物收益已验收。

本轮 Release x64 构建 0 错误（保留上游警告）；所选八类纯测试 149 通过、0 失败、0 跳过。第五补丁在固定源码归档与前四份补丁后正向检查通过，当前源码反向检查通过。部署后 70 份 User 文件 SHA-256 与部署前一致。引擎 DLL SHA-256：`E6E25245ABBBB0023CB73750223ED25164DD0DE654644A90CECE934AFBEA4069`；第五补丁 SHA-256：`53F38499FE1375349B294DCF402107F6D81696CB10F7BA87A5AE2804D7B92AA4`。实机验收由主工作流另行记录。
