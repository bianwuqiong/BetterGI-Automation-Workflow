# 可替换圣遗物刷取

复用 `scripts/workflow.py` 的互斥、启动、画质保存/恢复、日志归属与退出；插件只编排同一会话中的有界合成、战斗和每笔核验。默认公开示例只读禁用、零预算；当前用户指定血红之证/逆悬的冰河，另提供翠绿之影/铭记之谷与饰金之梦/缘觉塔示例。角色、套装、秘境、队伍、策略、主词条均可替换；主词条仅作目标元数据，`targetReached=false`，不会声称刷完即配装达成。

## 入口

```powershell
python scripts/workflow.py run --profile artifact-farming --artifact-config config/artifact-farming.json --dry-run --no-delay
python scripts/workflow.py run --task '圣遗物刷取' --artifact-config config/artifact-validation.json --keep-game --allow-existing-game --no-delay
```

生产运行只验证已经可恢复部署的插件与源码一致，不擅自覆盖 `User`。不登录HoYoLAB、不处理Cookie。不要通过直接调用JS绕过工作流锁和游戏日授权。

## 本机验证与授权

首次同目标秘境使用 `policy.validationOnly=true`、`maxClaims=1`、`maxCrafts=0`、两种树脂预算0、`domainValidated=false`。配置仍须明确 `executionEnabled=true` 与对应游戏日授权。先执行 `RunCondensedResinCraftTask(country,1,0,200,token)` 的无提交配方探针，再同域 `CombatOnly=true`、盾验证开启、所有树脂次数0的一轮战斗。Python要求原生无领奖完成事件、盾证据、树脂无消费与配方探针原生事件联合证明。

`recipeInspection.RecipeOriginalResinCost` 来自当前原生严格配方识别。`SafeCondensedCapacity` 为引擎的保守安全上界，`CondensedCapacityObserved=false` 明确不是当前游戏容量实读。配置 `craftOriginalResinCost` 与 `condensedCapacity` 必须由本机证据填写；后者仅作安全上界，不沿用旧版本40成本/5容量的默认假设。材料不足、界面或奖励未知会停止，无无限合成或补充树脂。

已获用户明确授权后，主代理可创建本机收据；helper只返回待保存对象，不申请或制造授权：

```python
from pathlib import Path
from scripts.artifact_farming import load_artifact_config, build_artifact_authorization
from scripts.workflow import atomic_json
config = load_artifact_config('config/artifact-farming.json')
receipt = build_artifact_authorization(config, '明确授权的带时区UTC时间')
atomic_json(Path('state/artifact-authorizations') / (config['policy']['scopeId'] + '.json'), receipt)
```

授权绑定目标/预算摘要与UTC+8每日04:00游戏日。未确认的持久检查点会阻止任何同日scope自动重放；完整核验的实际消费从scope剩余预算扣除。未知提交不会退款或当成成功。迁移不复制授权、库存、报告或检查点。

若用户明确授权持续开发/消费的时间窗口，可把真实批准时间与明确截止时间传给 `build_artifact_authorization(config, approved_at, valid_until)`。第二版收据原样保存 `approvedAtUTC` / `validUntilUTC`；不能在刷新时伪造新的人工批准时间。每run仍限制同一游戏日，04:00后用新run与新鲜库存；新日预算从独立当日账本计算，任何旧日unknown依然阻止自动重放。JS的取消期限同时限制每次原生调用不超过授权截止。

## 每笔证据

每run初始树脂都重新读取；只在同一run使用上一笔新鲜after作为下一笔before。合成优先使用一次有界批次：请求数量取剩余合成额度、保守容量减当前浓缩、实际原粹扣预留后可合数量、剩余原粹预算可合数量、原生最大5颗的最小值。传给原生的预算只有本批请求数量乘本机已验证成本，预先持久写unknown。

原生实际产出可为1至请求数量的有界partial数量，报告明确 `requestedCount`、`actualCreated`、`partialQuantity`。只按实际产出计账，要求新鲜原粹减少 `n*cost`、浓缩增加 `n`，并与原生返回、单提交日志收据完全一致；缺产出、数量越界或余额冲突均unknown停止，不重放。Python仍接受旧插件的单颗报告，不把配方探针当作实际合成成功证据。

每次秘境仅1领奖，一种树脂，其余计数0，关闭脆弱/须臾、原石补充和圣遗物分解。浓缩余额减少只证明消费，缺少实际正奖励字典或原生奖励收据仍为unknown。奖励必须至少包含本机ItemV2 `item_class_id=relic:*` 表中的实际圣遗物单件名称，只有摩拉也保持unknown。Python重新读取同一模型分类表，原生收据按步递增且不能复用，连续余额证据必须一致。每笔消费后必须重新读取余额，原粹每轮最多容许1点自然恢复差。

步骤/时间/真实余额/两类消费预算/合成次数均有界。原粹预算包含合浓缩消耗与原粹领奖；浓缩预算只计算实际消耗颗数，不把合成颗数当作原有库存。保留原粹按当前真实余额检查，不重复扣除已经反映到余额的历史消费。

## 离线验证

```powershell
python -B -m unittest tests.test_artifact_farming -v
node --test bgi-scripts/AutoGameArtifactFarm/tests/*.test.js
```

测试只用fake API、进程和保留夹具，不启动游戏，不证明本机识别或实际领奖已验收。
