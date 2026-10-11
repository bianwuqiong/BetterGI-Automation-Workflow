# 可替换目标的工作流与核验边界

角色培养父流程从本机 `config/cultivation.json` 读取规范化目标，不再固定瑞希身份。目标包含角色名、等级、三项基础天赋目标、是否包括当前装备武器及武器等级目标。父流程保存这五字段与确定性摘要，开始后每阶段前后重新确认配置未换目标；换角色或目标等级时重新建立本机证据和授权，不搬旧库存或消费余额。

父流程的成功培养子记录、独立 `cultivation-report.json` 档案和恢复请求必须全部匹配同一目标。不能通过仅重写结果摘要的角色名，把旧角色材料报告用于新角色。资源检查仍调用已有授权约束，收据中的完整目标必须匹配；旧角色的未知消费预留也不能通过换角色消失。策略、材料映射和具体来源是否受支持，由已有执行器独立判断；参数化目标不扩大未验收的Boss、路线或升级机制。

## 执行阶段

| 阶段 | 输入和证据 | 当前完成含义 |
| --- | --- | --- |
| 本机配置与只读扫描 | 当前目标、角色/武器档案、受支持材料、真实树脂观测 | 只证明此次支持项的读取与报告保存；未知不补零 |
| 免费队伍恢复 | 明确四人队伍、固定神像、两帧身份和HP、无道具消费 | 证明当前队伍适合后续战斗；旧恢复不能替代新鲜健康证据 |
| 可选材料路线 | 显式本机固定路线配置、当前运行与独立路线证据 | 只证明该路线范围；不表示所有新角色缺口已覆盖 |
| 培养有界消费 | 相同目标、本机游戏日收据、限额、单次尝试、库存和树脂前后证据 | 只证明已核验的材料步骤；当前父流程仍保留原单20验证门槛 |
| 可替换圣遗物目标 | `artifact-farming` 的角色/套装/秘境/队伍/策略/主词条及预算 | 只证明有界合成和真实圣遗物奖励；主词条与最终配装仍未达成 |
| 每日奖励与派遣 | 每日奖励收据及独立领取、重派、后置状态证明 | 每日奖励已领取不等于完整派遣已核验；缺派遣合同则父流程partial |
| 实际角色/武器升级 | 完整等级内经验、升级成本、资源和等级变化证据 | 尚未接入自动执行；目标始终 `targetReached=false` |
| 单天赋下一等级预览 | 本run冻结角色全名、单项类型、详情/预览/材料说明与Mora身份/世界恢复的新鲜原始证明 | 只证明该下一等级实际成本，升级数0；不授权确认升级 |

每个子流程继续使用统一宿主的互斥、启动、画质快照、退出与日志隔离。父流程额外约束全程时间、UTC+8每日04:00游戏日、所属子进程和录像覆盖；未知消费不自动重放。免费恢复与固定路线的原生证明有各自范围，父记录保存其所服务的目标，不能因此宣称角色升级完成。

## 授权与恢复

培养父流程保留明确用户调用、当前游戏日授权、现有单次验证预算、独立派遣门槛和新鲜免费恢复；改变目标不会绕过这些限制。圣遗物层可记录用户明确批准的持续窗口，并原样保留真实批准时间与截止时间；每run仍不能跨04:00，刷新后用新run、新实读库存和当日账本。持续窗口不能为培养层伪造新的人工授权时间。

普通unknown始终阻止消费重放。仅在显式主代理审查下，圣遗物的零预算验证可使用 `reconcile_validation_no_consumption`：它只接受严格配方读取阶段失败、两类预算0、合成额度0、空步骤、没有任何domain/提交事件，以及另一运行的120秒内原生只读余额证明。此审查不把任务变成功；旧结果、报告和日志保持unknown，独立audit与账本记录 `originalStatus=unknown` / `resolved-no-consumption`。真正paid或任何unknown步骤均不适用，正常runner不会自动调用此helper。

若前一笔真实合成已核验、下一笔领奖unknown，账本保留全run `status=unknown` 和aggregate totals为null，另记 `confirmedSubtotals`、已确认step IDs及unknown step IDs。已确认浓缩消费小计0不能解释为unknown领奖最终没有消费；已证明的合成成本不能退款，授权仍被未解决的步骤阻断。这一记录只是事实保留，不允许paid恢复或消费重放。

任务结果与资源交易状态是不同维度。任务/步骤仍可为unknown，而资源状态仅在明确证明后归为 `known_not_submitted`：新的同run/step positive abort必须证明提交latch为false、按钮请求未发；旧版本只能在主代理明确选择已审查源码分支、核对对应DLL及精确提交前错误文字后使用，并以另一run的新鲜实际余额补充核验。缺事件、网络取消或余额没变本身均不足；请求标志已置true或有提交后的收据则不能用此分类。

`artifact_resource_review.review_known_unsubmitted_claim` 不改旧任务/步骤unknown或aggregate null，只新增资源0的独立审查证明。`review_approved_batch_stage` 可由主代理显式为同一已获人类批准batch尚未使用的资金创建一个新阶段：新scope/run/step身份、原粹0/浓缩1或原粹20/浓缩0、无合成、一领奖、最多5分钟，沿用真实批准时间和原截止，仍保留最初未被此证明覆盖的unknown来源。嵌套阶段回溯原始人类批准scope，累计已确认原粹消费（含合成成本）、浓缩消费和实际合成数；生成的浓缩仅记资源转移，不增加获批额度。同时只允许一个待执行阶段，真正提交后未知仍blocked。两种helper都不由正常runner自动生成或调用；它们不是追加花钱许可，不把旧失败任务标为成功，也不能伪造一个当前不存在的reward-prompt场景。

原native10钟离切人失败只有固定DLL和全体源码快照、精确单回合TXT参数、受保护重试一次、`await StartFight`异常必在古树/领奖入口之前退出的控制流，以及本run真实战斗上下文附件共同成立，才支持显式源码审查。冻结manifest逐文件hash和编译DLL必须吻合，普通网络取消不适用；另一run 120秒内世界树脂实读只是补充账户核对。新的native11则按同任务实例的单调phase、回合数、提交请求数和已完成领奖数提供正事件；`before_reward_interaction`要求未进入资源交互且全部消费请求计数为0，不能从任意异常文字拼出证明。

上下文附件保留原始bytes、格式与hash。支持完整PNG/JPEG客户端帧，或已核实的Sky原始1538×895窗口帧（含30像素标题栏，客户端region x=1/y=30/1536×864），不裁剪旧证据。没有精确截图/退出时间时，`capturedAtUTC`和`observedAtUTC`保持null，使用可信工具序列的真实区间：截图在本run `result.finishedAt`之后，原文件保存mtime为上界，区间不超过120秒；退出在保存之后，以随后真实已核验免费恢复的triggeredAt为世界状态上界，缺退出截图明确记录missing。不能把文件保存时间伪称截图时间。审查收据列出全部来源hash，后续分类/新阶段重新核对；原档案被改即拒绝。

### 原始持续窗口的未使用资金

后续批次首次实读库存所作的预算clamp，不自动撤销用户先前明确批准的原始额度。`artifact_window_funding.review_original_window_stage` 支持主代理显式归回原始200原粹/5浓缩/5合成额度窗口，但只接受原始授权、原目标、原真实批准/截止时间，以及后续直接人类“允许新建批次继续，保留原未知记录”许可的完整绑定。私有session书面摘要不能独立授予该权限。

原始未知run必须恰有已确认成功的一次60成本合成和随后唯一未知浓缩领奖，原生receipt、独立余额差、作用域nonce与配置摘要再次核验。初始60与生成1原样记账，未知领奖严格参数原粹0/浓缩1时仅支持保守预留浓缩1、原粹0；该预留不能被后来的余额或许可“退回”。后续同资金家族已确认消费全部累计，classified0仍仅是资源0而非任务成功。任一新的未分类unknown再次阻止下一阶段。

此入口只创建一份新scope的单阶段审查和对应授权，不改配置、不启动游戏、不改旧unknown。配置只能60原粹+一次合成+一浓缩领奖，或单浓缩，或单20原粹，最多5分钟；同资金同时只允许一个pending阶段。每次要求120秒内独立树脂实读；合成还需实际原粹≥60和安全空位。确认消费+保守预留+新stage不能超过原200/5/5，生成浓缩不是新增授权。当前实现按整个原窗口保守累计，不在04:00隐式补回额度；已有不同游戏日的旧接续资金记录需另作明确日期审查，不能自行放行。

主代理从实际当前聊天人类消息建立私有附件，schema如下（示意字段值须来自真实收据/消息，不能照抄日期造授权）：

```json
{
  "schemaVersion": 2,
  "kind": "root-reviewed-original-artifact-window",
  "sourceKind": "direct-user-request-in-current-thread",
  "reviewedBy": "root-agent",
  "originalScopeId": "<原始授权scope>",
  "continuationScopeId": "<明确继续许可scope>",
  "oldReceiptApprovedAtUTC": "<原始收据approvedAtUTC原样>",
  "validUntilUTC": "<原始收据截止原样>",
  "continuationApprovedAtUTC": "<真实继续许可收据时间原样>",
  "semanticGrants": {
    "target": {"<目标配置字段>": "<原始已批准目标完整对象，字段和值须逐项相同>"},
    "originalFundingCaps": {"originalResinCap": 200, "condensedResinCap": 5, "craftCap": 5},
    "allNaturalOriginal": true,
    "allCondensed": true,
    "preferCondensed": true,
    "forbidFragile": true,
    "forbidTransient": true,
    "forbidPrimogems": true,
    "continueUnusedStages": true,
    "preserveUnknown": true,
    "replayUnknownAllowed": false
  },
  "quotes": {
    "resourceAuthorization": "<直接用户完整资源授权原话>",
    "targetChange": "<直接用户目标设定或更换的原话>",
    "developmentWindow": "<直接用户给定持续运行窗口的原话摘录>",
    "continueNewBatch": "允许新建批次继续，保留原未知记录"
  }
}
```

新附件使用 schema2，所有语义授权字段仍须来源于实际人类请求并与原始目标、额度和收据哈希一致；这些布尔值不能自行产生权限。schema1 仅兼容已经被主代理明确审查的历史同路径／同哈希字节，不用于创建新的授权来源。

显式调用 `review_original_window_stage(root, initialScope, continuationScope, newConfig, freshProbeId, source_path=realSourcePath, source_sha256=realSourceSha256, reviewed_by='root-agent', apply=True)`。默认`apply=False`只返回可审查结果；普通runner不会生成此附件或调用此helper。新收据区分原始批准与后续继续许可，派生授权仅承接已有真实时间，不使用审查时刻作新人类批准。缺来源、错hash、改期限、native成本/前后库存不符、额外unknown或重复scope均拒绝。

### 原窗口内的显式游戏日转换

原持续窗口仍有效时，04:00之后须使用 `review_window_game_day_transition(root, initialScope, continuationScope, freshTodayProbeId, currentGameDate, new_config=newConfig, source_path=realNewSourcePath, source_sha256=realNewSourceSha256, reviewed_by='root-agent', apply=True)`。`new_config`必须由主代理明确提供新的scope、相同目标和有界费用，不自动生成。当前单20阶段配置为原粹20/浓缩0/合成0/领奖1/最多5分钟。

必须另有真实人类语义审查的schema2私有来源，`semanticGrants.allowGameDayTransition=true`；仍引用原始批准、继续许可与真实截止。该标志必须对应已有的人类持续运行与游戏日请求，不能由普通runner填写。新的schema2文件与历史schema1文件分开保存；历史已审查来源、路径、字节和hash不被重写，也不因旧schema1非空引文就扩出跨日权限。

审查重新核对当前UTC+8每日04:00游戏日、120秒内独立世界树脂实读、共享宿主档案中的唯一PID/准确gameExe、实际游戏进程指标及完整画质证明。物理客户端必须1920×1080，探针的expectedWindow与本机gameDisplaySettings完整一致，不能用1536×864逻辑尺寸或缺少期望窗口的报告代替。新范围仍累计全部旧日已确认费用和未知保守预留；不重置原200/5/5、延长窗口、更新人工批准时间或搬旧库存。额外unknown、过期/不明库存、错游戏日、目标变化、重复scope、资金不足、非唯一进程或画质不完整均拒绝。

显式apply仅保存该新scope的游戏日审查、window-stage收据和派生授权，不修改配置、旧日账本或任务结果。实际新run仍由主代理另外启动，标准runner在新当日账本登记新run/step并再次核对收据、来源hash、库存、日期和累计限额；旧unknown始终保留。审查时刻仅是审查事实，不能成为新人类批准时间。

消费登记前，控制器重新调用现有unique/exact-game校验和物理客户端查询，并将查询结果传给 `constrain_artifact_authorization(..., current_game_identity={'pid':currentPid, 'exe':verifiedAbsoluteExe, 'physicalClient':{'width':1920,'height':1080}})`。跨日stage要求这份当前身份与审查记录一致，不能重用旧probe的PID字段或以任意`verified=true`布尔代替平台查询。同exe重启得到新PID、缺参数、错误路径或当前尺寸变化都会在assign/写账本前拒绝；普通旧日入口仍兼容无此参数。

## 当前覆盖

可替换目标层已经提供角色培养父子身份绑定、圣遗物独立scope与批次、显式无消费审查，以及相应纯fake回归。离线测试不代表所有新角色、秘境、材料、摩拉或武器经验已在本机完成识别验收。缺静态规则、未支持的来源、未知数量和未完整计算的升级资源继续显示blocker/manual；不通过修改目标名就宣称全面支持。

`workflow.py run --profile cultivation --task '培养材料' --cultivation-talent-preview --talent-type elemental-skill` 提供独立零预算单天赋成本预览，默认只读战技。依赖原生14的rich raw schema；旧DLL没有接口或缺完整证据时保持unknown，而不会调用旧消费adapter替代。JS/Python各自核对基础等级/+3、实际下一等级popup成本及材料tooltip完整名称和持有分子；tooltip聚合培养需求不当作此次升级费用。Mora须有实际身份模型≥0.75，当前未加入未经实读的tooltip兜底。全部raw只写私人record/run档案，公开回归使用synthetic模型形状数据。

原生17的显式53货币区域与真实detector行推导的数量框有独立Host核验：旧37识别与失败initialReading全部保留，不搜索最高模型分数或用初值冒充最终费用。材料新框必须与实际card相交；Mora新框只能来自唯一完整初始ratio行的pad12几何。所有整数/同帧/2px边缘标准不降低，高置信旧币冲突或伪造derivedbox均拒绝；额外原生PNG只供私有诊断，不能将弱币/未知库存提升成功。

圣遗物合成批次可按当前余额、剩余预算与安全容量一次请求多颗；每批仍只有一次提交，按实际 `n≤requested` 与新鲜余额差核验和计账，不预测产出。现有单颗报告保持兼容。配方已验证与本机真实合成已验证是不同事实，不能通过配方探针把首次实际合成提前标为成功。

`scripts/artifact_target_yield.py` 提供独立事后统计，不更改任务结果：只读取已核验成功领奖的实际名称与数量，再使用显式目标套装/模型family对应和本机ItemV2分类表统计目标件。血红之证对应的已审查family为 `relic:15047_`；quality4/5模型行的奖励字典聚合会丢失星级，因此输出 `qualityObserved=false` / `fiveStarDrops=null`。主词条没有观察，目标仍未完成；只掉共生套时目标件进度为0，已核验的正确秘境消费结果仍保留。

针对目标替换和旧身份拒绝的离线检查：

```powershell
python -B -m unittest tests.test_cultivation_full -v
python -B -m unittest tests.test_cultivation_validation.ValidationLedgerTests.test_replacing_target_cannot_reuse_old_receipt_or_unknown_budget_reservation -v
python -B -m unittest tests.test_artifact_farming -v
```
