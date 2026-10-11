# 角色培养工作流 / Character cultivation workflow

## 中文

**当前状态以[2026-10-11交接](DEVELOPMENT_HANDOFF_2026-10-11.md)为准。** 下文的初验60预算与未验收说明属于早期开发边界；当前已增加独立当天授权、单20领奖、背包完整材料链证据和有界同run读数复用，均不随公开包移植私人授权。最新构建与新机只读验收见[迁移步骤](TRANSFER_SETUP.md)。

培养档使用已经登录的原神，通过 BetterGI 读取角色等级、天赋、当前武器和本次需要的背包材料，再按固定规则计算缺口。它不需要 AI，也不需要提供账号密码或 HoYoLAB Cookie。

默认示例为梦见月瑞希 **90 级、天赋 9/9/9、当前佩戴武器 90 级**；武器 90 级是可修改的默认目标。三项天赋按基础等级计算，命座增加的 3 级不会被当作实际已培养等级。

### 先读取，再决定刷什么

1. 复制 `config/cultivation.example.json` 为不进入 Git 的 `config/cultivation.json`，调整目标。
2. 安装只读入口：`powershell -NoProfile -File scripts/install_cultivation_launcher.ps1`。
3. 点击桌面“原神培养计划（只读扫描）”。它复用默认桌面分身、共享锁、画质隔离、网络守护和停止入口。
4. 在该次 `logs/runs/<runId>/cultivation-report.json` 查看当前角色、当前武器、实际材料数量、未知项、材料来源及开放日。扫描不会刷本、领奖、签到、合成或升级。

也可直接运行：

```powershell
powershell -NoProfile -File scripts/run_cultivation.ps1 -DryRun
powershell -NoProfile -File scripts/run_cultivation.ps1
```

`-DryRun` 只检查配置和生成计划入口，**不读取游戏或实际库存**。已有前台游戏仅用于读取诊断时，可显式加入 `-KeepGame -AllowExistingGame`；游戏进程仍须通过原有归属校验。

开发诊断可加 `-ExecutionMode foreground`，或运行 `scripts/run_daily_recorded.ps1 -Profile cultivation -TimeoutMinutes 6` 保留原神窗口录像。录屏默认只读，显式加 `-CultivationMode execute` 才按预算执行；两种模式均保持低画质、兼容模式和1920×1080校验，默认日常仍使用桌面分身。

只读树脂探针：`python scripts/workflow.py run --profile cultivation --cultivation-resin-check --execution-mode foreground --no-delay --timeout-minutes 4`。它不读取培养材料、不领奖，也不把getter成功当作培养扫描成功。

### 可信库存与材料计算

- 图标未找到、没有返回、OCR 失败均为 `unknown`；只有明确读取到 0 才记库存 0。未知项显示“待核实”，不显示猜测的数量缺口。
- 各条3:1材料链独立核验，未知武器材料不会清空已知天赋书的建议。合成后的假设缺口可避免过刷，但不会更改实际库存或声称已经得到产物。
- 完整可信库存链才用于该类任务选择；每次执行前会复核相关材料，领奖后再读取数量。
- 同时升级角色、三个天赋和当前武器时，共享材料先合并需求，不能把同一批刀镡或摩拉重复扣除。
- 报告包含突破与天赋材料、武器突破材料。**当前规则没有角色／武器升级经验和对应摩拉的精确计算，摩拉余额也不能通过背包网格可靠读取。**这些资源列为待人工核对，不能把报告描述为全部培养成本。

### 瑞希材料来源

固定规则中的映射如下，实际缺口仍以本次读取为准：

| 材料 | 来源及当前处理 |
|---|---|
| 谜土的护符 | 灵觉隐修的迷者；普通 Boss 有界适配，默认关闭，待本机验收 |
| 海灵芝 | 特产路线；本机没有订阅路线，列为待处理 |
| 刀镡系列 | 野伏众／海乱鬼与合成；路线尚未接入 |
| 「浮世」系列 | 菫色之庭，周一、四、日；需本机核实目标关卡和周日奖励序号 |
| 残火灯烛 | 零落丘墟周本；只列需求，不自动执行周本 |
| 自在松石系列 | 突破玉与合成；只列需求及合成建议 |
| 当前武器材料 | 从识别到的装备武器推导，不猜武器名称 |

### 执行培养日常

刷取入口默认关闭。先验证相关秘境或 Boss、队伍及读取能力，再在私人配置中设置 `executionEnabled=true`、对应的 `allow*` 和 `*Validated` 开关，并填写本次预算；未验证的类别保持关闭。

```powershell
powershell -NoProfile -File scripts/run_daily.ps1 -Profile cultivation -CultivationMode execute -NoDelay
```

该档按“邮件 → 培养材料 → 委托领奖”执行，**不先将原粹全部合成为浓缩**。培养节点每次至多领取一轮，核验后才决定下一轮；培养步骤受 `maxSteps`、最多 15 分钟及树脂预算限制，整次流程沿用约 20 分钟目标及现有超时保护。耗时和成功率仍需对应任务的实机证据验证。

- 普通 Boss 每轮只用 40 原粹，零死亡重试，单轮 120–180 秒超时。
- 秘境每轮只用 20 原粹或一颗浓缩，其余树脂类型／次数显式清零；运行前须确认 BGI 全局秘境复活尝试上限为 1，避免发生重复消费。
- 原粹预算是最大支出，不是当前树脂数量。设置保留量时，需要 120 秒内的实际原粹数量观测；没有观测就拒绝可能侵占保留量的任务。
- 不使用脆弱／须臾树脂，不自动分解或升级。收益无法核实时停止，不自动重放。
- 本次成功只证明扫描或已核验的有限领奖步骤；`targetReached=false`，不意味着角色已经升至目标。

实时树脂来自两帧稳定读数，浓缩未显示或未读到仍为未知；原粹可独立核验。配置成本与实读前后净减少分开记录。只读快照失败可有限重取新帧，不重复已提交或不明的消费步骤。

`validationMode=true` 另受私人 `state/cultivation-authorization.json` 的独立游戏日／目标／累计预算约束：最多60原粹、零浓缩、最多两步、每类来源一次。未确认attempt按40／20保守预留；只有绑定完整来源和时间证据的独立未提交审计才能解除，不扩大授权，不覆写旧失败或unknown。初验授权不代替已通过验收的标志。

素材合成适配通过 `allowCrafting` 与 `craftingValidated` 独立控制，默认关闭。启用后每批先记录，再用真实取消令牌执行单批合成，重读完整材料链核验3:1输入和实际产物；返还或不明结果停止。摩拉成本未可靠读取，初验60树脂模式不启用合成。经验、升级、周本和路线的现有限制仍保留。

小树脂预算不一定满足全部委托领奖条件；保留手册实际进度，不额外消费或把未满足条件标为完成。

### 钟离补盾与不领奖演练

`requireZhongliShieldCast=true` 在培养秘境开启挑战前长按钟离E，只有两帧9.5–12.5秒的实际冷却读数才认可施放。战斗中按12秒补盾节奏及长动作窗口检查，并切回下一条策略命令的角色。该证据证明合格长E释放，不能测量盾剩余生命，也不能保证敌人不会破盾；核验失败立即停止。原普通日常默认行为保留。

可先单独验证已核实队伍和旧木偶星超导策略，不消耗培养预算：

```powershell
python -B scripts/workflow.py run --profile combat-rehearsal --execution-mode foreground --no-delay
powershell -NoProfile -File scripts/run_daily_recorded.ps1 -Profile combat-rehearsal -TimeoutMinutes 8
```

该档固定一轮逆悬的冰河，在挑战达成后、寻树和领奖前退出；不签到、领取邮件、分解或自动吃药，所有树脂参数为0，独立硬禁领取。仅在原生挑战/退出/长E证据和实际参数报告同时核验后，记为战斗演练成功；空奖励或脚本返回不等于材料获取成功。

2026-10-09已完成本机前台录屏验收：整轮189秒，两次长E请求间隔约13.6秒，确认未领奖退出并回到大世界；零树脂消费，录像帧覆盖99.68%，画质恢复核验通过。该结果证明本轮战斗和退出流程，不代表材料领奖、其他秘境或培养目标已完成；材料执行验收标志仍独立保留。

初验跨游戏日续跑需保留原累计账本，再写入绑定不可变回执快照的日期授权；不能用改游戏日或新建60额度清除旧未知预留。版本字符串迁移只接受同一白名单证据中画质项和性能配置不变的实际版本变化，严格画质守卫保留。

后一步结果不明时，报告仍保留前面独立核实的材料收益与已确认花费小计；`confirmedSubtotalOnly=true` 表示这不是全程总消耗，`actualResinDelta=null` 表示全程消耗尚不能确认。未知步骤仍占用预算预留，不因保留小计而自动重放。

### 官方养成计算器与游戏内手册

[HoYoLAB 计算器](https://act.hoyolab.com/ys/event/calculator-sea/index.html)与[米游社计算器](https://webstatic.mihoyo.com/ys/event/e20200923adopt_calculator/index.html)可用于对照完整需求。目前没有接入账号 API、自动授权同步或官方 JSON 导出；不要把签到 Cookie 当作材料同步已授权。

游戏内养成手册可用于核对缺口和零库存；现有 BGI“根据提升指南选择秘境”接口仅选本，不能导出整张材料表。本版以角色档案和背包为主，并新增武器材料tooltip的专门读取：仅对本次所需、背包未知的武器突破材料进入目标角色的提升指南，核实装备武器及目标等级，再读取完整材料名与“培养需求 拥有／所需”两帧。前后角色／武器上下文、需求分母和帧时间均需一致，Python再次独立核验；可合成数量不当作库存，卡片未出现仍为unknown。该新增路径已于2026-10-09通过简体中文1920×1080前台只读实机验收，完整扫描含启动共425秒；一般手册材料表完整导出尚未实现。使用此路径需要包含 `GetCharacterForDevelopmentGuide` 的定制引擎补丁。

`normalize_calculator_material` 支持今后导入官方计算结果：当 `lack_num>0` 时记录精确推导库存；当缺口为 0 时只记录库存下界，不能当成精确库存。此次不运行账号请求，也不提供虚构的自动同步功能。

### 来源与验证

本机已验证游戏内角色档案与多类材料读取。头像模型在本机 DirectML 默认输出读回路径出现异常，定制执行引擎现仅将 `AvatarGridIcon` 改用 CPU；其他识别模块继续采用原来的设备配置。只读扫描还通过独立配置字段跳过最终奖励检查，避免额外打开手册／地图。使用其他 BetterGI 构建时，应先核实这些能力；不要把脚本测试通过当作引擎实机验收。

复用了社区项目 [GenshinCultivationPlanner](https://github.com/yunxi001/GenshinCultivationPlanner) 的四个纯计算模块及静态数据，固定提交 `3f1e938a6dcd5a34642dad03a91488db8d2da40c`；这不是 BetterGI 官方已验证的培养模块。版权、GPL v3、数据来源 MIT 声明保留在插件 `upstream/` 中。

新增逻辑使用 fake BGI 接口做离线测试：

```powershell
python -B -m unittest discover -s tests -v
node --test bgi-scripts/AutoGameCultivation/tests/safety.test.js
```

## English

This profile reads character progress, equipped weapon and relevant inventory through the existing BetterGI game interfaces. It computes material gaps without AI, account passwords or HoYoLAB API access. The example targets Mizuki level 90, talents 9/9/9 and equipped weapon level 90.

The desktop scan entry is read-only. Missing icons or failed OCR remain unknown; they are never silently converted to zero. Exact inventory is separate from hypothetical 3:1 crafting. Reports cover ascension and talent materials, but exclude exact level-up experience and associated Mora; unimplemented routes, weekly bosses and ley lines remain manual.

For diagnosis, use `-ExecutionMode foreground` or `scripts/run_daily_recorded.ps1 -Profile cultivation -TimeoutMinutes 6`. Recording defaults to a read-only scan; `-CultivationMode execute` explicitly selects bounded execution. Both modes retain low graphics, compatibility mode and 1920×1080 validation; normal daily runs retain child-session execution.

Execution defaults to disabled. Validated domain and world-boss adapters use single claims, explicit budgets, inventory verification and the existing shared lock, child session, graphics isolation and stop handling. Unknown outcomes are never replayed automatically. Successful steps do not mean the cultivation target has been reached.

Official calculator synchronization and general training-guide table export are not implemented. A new weapon-tooltip reader supplements unknown backpack counts with two explicit material-name and owned/required observations, verified character/weapon/target context before and after, bounded timestamps and independent Python evidence checks. Craftable quantity and absent cards never become inventory counts. This path passed a local read-only foreground validation on 2026-10-09 with Simplified Chinese at 1920×1080, taking 425 seconds for the full scan including startup. It needs the custom `GetCharacterForDevelopmentGuide` engine entry. The calculator import normalizer preserves lower bounds instead of inventing exact inventory. The upstream GPL/MIT attribution and pinned source revision remain in the plugin.

The local custom engine uses CPU only for `AvatarGridIcon` to avoid an observed DirectML output-readback defect; other models retain their configured providers. Read-only scans use a separate flag to skip the final reward inspection. Check these engine capabilities when using a different BetterGI build; plugin tests alone do not establish live engine compatibility.

Independent recipe chains separate unknown inventories from known crafting suggestions. Live resin observations and configured costs remain separate. Initial validation uses a private cumulative ledger capped at 60 original resin, no condensed resin and two steps; audited non-commit reviews release reservations without changing old outcomes. Crafting has separate disabled-by-default gates, real cancellation and actual material evidence; it is disabled during initial validation. Small resin budgets do not imply that all commission rewards are available.

If a later step is uncertain, independently verified gains and claim costs remain as a confirmed subtotal. `confirmedSubtotalOnly=true` and `actualResinDelta=null` do not imply that the full run spent zero resin. Uncertain attempts still reserve their budget and are not replayed automatically.

`requireZhongliShieldCast=true` verifies two fresh 9.5–12.5-second hold-skill cooldown readings before activating the challenge, then schedules refreshes between safe command boundaries. It verifies a hold cast, not shield health or immunity to shield-breaking damage. Failure stops the task. The separate `combat-rehearsal` profile runs one known domain round, exits before finding or claiming rewards, and requires native challenge/exit/cast evidence plus the actual parameter report. It performs no material or daily reward task and does not allocate the cultivation budget. Cross-day initial validation needs an immutable receipt snapshot and explicit dated continuation; previous uncertain reservations remain.

A recorded local rehearsal passed on 2026-10-09: 189 seconds overall, about 13.6 seconds between two hold casts, verified exit without claiming rewards, zero resin spent, 99.68% recording frame coverage and verified graphics restoration. This validates that battle and exit only; material claims, other domains and cultivation completion require separate evidence.
