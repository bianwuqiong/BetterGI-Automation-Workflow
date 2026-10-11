# 每日领奖与派遣证据边界（2026-10-11）

本轮只检查固定 BetterGI 源码及日志分析器、添加离线回归，没有打开游戏或执行领取、刷怪、树脂消费、重新派遣。新机每日派遣重置继续列为未验收；已领取每日委托奖励不能证明派遣完成。

## 固定源码实际行为

已检查 `automation-baseline-2026-10-08`（提交 `d8c0aa238a949d7d74bfe5087f3a48e39771575a`）与当前完整培养补丁：

- `BetterGenshinImpact/Model/OneDragonTaskItem.cs` 的“领取每日奖励”调用冒险家协会流程，该流程还会尝试探索派遣，之后领取纪行奖励。
- `GameTask/Common/Job/CheckRewardsTask.cs` 的 `检查每日奖励结果：今日奖励已领取` 来自冒险之证委托页的实际 OCR 状态；其证据只属于每日委托奖励。
- `GameTask/AutoSkip/OneKeyExpeditionTask.cs` 的 `全部领取`、`再次派遣` 分别在按钮点击后输出，`完成` 在按 ESC 后输出。它没有重新读取新派遣槽位、角色、倒计时或领取回执；异常被捕获后只打印异常文本。
- 已废弃的 `GameTask/AutoSkip/ExpeditionTask.cs` 同样不能提供重新派遣后的独立证据；其 `重新派遣完成` 是循环结束文本。
- 冒险家协会派遣选项的 `未探索完成或已领取`、`未找到领取按钮` 均有多种原因，不能证明无任务可领、无须派遣或已成功重派。

固定源码和完整补丁中没有能够证明派遣领取及重新派遣后状态的 `[AUTO_GAME_EVENT]`。本轮不为不存在的原生事件编造成功解析器。

另一个独立兼容性限制：启用 `DragonEndSummaryEnabled` 时，原生奖励检查输出的是 `一条龙结束汇总：…每日委托奖励：已领取`，而非旧的“检查每日奖励结果”行。当前分析器未将这一替代汇总文本升级为已核实领取；不能仅从通知成功或任务结束补出证据。

## 新的结构化结果

`scripts/analyze_run.py` 保留原有委托领取的独立结果，并明确标注范围：

- 每个每日领奖任务增加 `dailyRewardClaim`，包含原来的领取状态、原因及证据。已核实成功额外标记 `successScope=daily-reward-claim-only`。
- 顶层 `dispatchVerification` 包含 `status`、`collectionStatus`、`reassignmentStatus`、`postStateStatus`，当前都为 `unknown`，且 `evidenceVerified=false`。
- 只有匹配到本次每日领奖任务段的派遣文本才进入 `legacyEvidence`。这些文本始终为未核实操作描述，不参与成功判断；混合运行、错误配置或其他任务段不提供可归属的派遣文本。
- 日志中有每日领奖任务时，`fullDailyScopeVerified=false`；没有此任务时，该字段及 `dispatchVerification` 为 `null`，表示本次不涵盖完整每日派遣验收。
- 通用事件中即使附带 `dispatchVerified=true` 或声称派遣成功，也不能填补上述独立字段。

`outcome=completed` 保留原有请求任务范围的兼容语义。对于每日领奖，这个结果只确认委托领取范围，不能作为“领取及重新派遣均已核实”的全日常证据。要求完整日常范围的上层验收必须检查 `fullDailyScopeVerified` 与独立派遣证明，而不是复制委托领取状态。

最终 `result.json` 已由现有工作流保存分析器字段及任务明细。日志分析器不改变工作流启动或自动重放；证据不足保持未知，也不发起派遣补做。

## 支持范围的完整日常验收

`scripts/cultivation_full.py` 的父流程现已对培养日常子报告增加独立派遣门槛。子报告只有委托领奖等旧范围 `completed`，而派遣证明缺失、未知或类型不合法时，父层该阶段保留 `partial`，标记 `completionBlocker=dispatch_unverified` 并记录具体原因；不能得到支持范围完整日常的 `completed`。

原始子报告结果保留在 `claimedOutcome`，每日领奖任务及 `dailyRewardClaim` 原样透传；不删除已确认的委托、材料证据。原始 `dispatchVerification`、`fullDailyScopeVerified` 同时透传，并由父层另计算 `dispatchScopeVerified`。父报告的 `fullDailyScopeVerified` 仅在父流程整体 `completed` 且实际培养阶段通过独立派遣门槛时为真。已核实的培养恢复记录不能弥补新的必需队伍恢复失败或未知；即使培养子阶段完成，父流程跨游戏日等未完成结果也不设置全流程验收标志。

未来由独立原生回执／后状态验证器提供的契约必须同时满足：

- `dispatchVerification.status=verified`；
- `dispatchVerification.evidenceVerified` 严格为布尔 `true`；
- `collectionStatus`、`reassignmentStatus`、`postStateStatus` 分别为 `completed`；
- 子报告 `fullDailyScopeVerified` 严格为布尔 `true`。

单个成功标志、整数 `1`、字符串 `"true"`、只有领取成功、重新派遣未知、后状态缺失或 `skipped` 均不能通过。目前原生引擎没有此契约的真实成功来源；离线成功夹具只定义将来验证器的接口，不能冒充当前实机证明。

旧的同日 `completed` 子报告如无派遣证明，恢复请求也被拒绝，保留已知领取的 `partial` 及拒绝原因；不会启动新阶段、不会重放原步骤。预览仍可生成计划，但不要求或声称实际派遣验收，父层完整范围标志为 `null`。

## 后续原生核验要求

先建立本机只读的派遣界面夹具，验证槽位、角色和倒计时能稳定读取。真实操作另需用户授权。原生实现应保留本次 `runId`、任务范围和观测时间，分别核实领取回执与重新派遣后的新状态；领奖点击、重派按钮点击、ESC、空界面及缺少事件不能代替这些证明。

确认有真实原生事件与持久化原始证据后，再增加独立验证器及成功分支。未知或异常的领取结果不得自动重放；退出、主界面恢复、游戏进程退出及手动画质恢复仍须分别核实。

## 离线回归

`python -B -m unittest tests.test_analyze_run -v`：**43 项通过、0 失败**。新增 8 项覆盖委托与派遣范围分离、点击及结束文本不能证明重派、缺少按钮不能视为跳过、伪派遣标记、任务段隔离、混合运行与错误配置、跨 run 事件和后续失败，以及不包含每日领奖的运行。

现有工作流与培养工作流离线集成回归（`tests.test_workflow`、`tests.test_cultivation_workflow`）另 **67 项通过、0 失败**；保留既有领取与恢复契约。

完整日常父流程回归（`tests.test_cultivation_full`）**33 项通过、0 失败**；新增 7 项覆盖证明缺失、现有只确认委托的解析结果、假成功标志／部分证明、旧恢复请求不重放、预览范围、已核验培养恢复记录不能弥补新队伍恢复失败，以及父流程跨日部分结果不能设置完整范围标志；以明确标为未来契约的假夹具保留正向验收场景。

这些测试仅证明分析器保持证据边界，不证明新机派遣或完整日常实机验收通过。
