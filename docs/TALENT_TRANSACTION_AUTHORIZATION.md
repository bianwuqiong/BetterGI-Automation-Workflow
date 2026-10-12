# 单次天赋 Host 授权与预算核心

`scripts/talent_transaction_authorization.py` 是纯 Host 事务策略核心。它没有实际授权创建、凭据读取、游戏 API、UI 操作、dispatcher 注册或生产 composition。`TalentSpendPermit.native_consumption_enabled` 始终为 `False`，`native_admission()` 始终抛出 `Unintegrated`。现有 Native24 默认 `UnintegratedTalentEvidenceVerifier` 和 `CurrentPopup` 的拒绝保持原样。

本模块的完成只表示离线策略闭环，不表示受信本机授权桥、当前窗口确认门禁或真实消费已经接线/验收。过期的历史授权不能因开发、只读核验或游戏日变化获得新的消费权限。

## 公开调用及受信输入

公开调用是 `issue_permit(TalentStepRequest)`、`assert_still_valid(permit)` 和 `finalize(permit)`。调用方只能填写运行/步骤、角色、三个天赋之一、当前基础等级、目标上限和既有授权 ID。请求不包含批准布尔值、账号 scope、文件路径、价格或库存。目标支持参数化角色及 `normal`、`skill`、`burst`；当前契约的基础等级上限为 9。

私有 `_TrustedBoundary` 是未来同进程受信 composition 的接口说明，当前没有生产实例。它固定本机私有根、原有本机 nonce、原有本机受保护账本密钥、实际 runner 持有的 `workflow.RunLock`（可选）和五类受信 reader。未提供有效边界/密钥就拒绝。本模块不创建、部署或保存 nonce、密钥、grant，不读取授权原话或任何账号登录凭据。

| Reader | 必须由受信组件独立建立的内容 |
| --- | --- |
| `read_grant(authorization_id)` | 本机既有不可变 `LocalGrant`，原始授权来源 SHA-256、原批准时间/截止、原游戏日、实际账号身份、原目标及逐具名物料/Mora 上限。原授权文本留在既有本机配置入口。 |
| `read_context()` | 当前 runner 的实际唯一进程、精确启动 ticks 字符串、实际账号身份、原本机 nonce、已载入执行文件/程序集 hash、capture session、backend generation、原生 actual binding receipt hash 和真实时间。 |
| `read_before(request, context)` | 严格原始验证器认可的完整本日 `VerifiedBefore`，完整角色/天赋标题/基础等级/固定 +3、每种具名旧材料 owned/required、Mora 及完整原始来源。 |
| `read_outcome(request, context)` | 独立严格验证器认可的 `VerifiedOutcome`：真实提交边界，全部 after 原始证据，最终世界双帧；或确定未提交的正面原生证明及世界恢复。 |
| `read_account_holds(context)` | 同一实际账号的完整既有 artifact、cultivation、native 账本枚举，含全部未解消费；枚举原件和 hash，不允许只传自称完整的空列表。 |

这些 reader 必须返回同一个私有 `_ReceiptAuthority` 原本注册的对象。`LocalGrant`、`VerifiedBefore` 等 frozen dataclass 是数据类型，直接构造它们不构成认证；JSON、`evidenceVerified=true`、调用方布尔值及来自另一 authority 的 receipt 均不能通过。authority 持有原对象身份和不可变内容，拒绝未注册、换值或突变对象。它只能由未来经过审查的本机配置/原生验证组件持有；`_seal()` 是私有 adapter seam，不能包装成 JS/JSON/API 的 mint 入口。

这是同进程受信组成边界，Python 私有标识不是代码沙箱。已有任意可信 Python 代码执行权限的代码可访问私有对象，拥有同 Windows 用户权限的恶意进程也不因 DPAPI/HMAC 得到隔离。这里只防止普通请求 JSON、未认证数据和账本文件替换伪造授权或成功。当前密钥 composition 为 deferred；没有新增用户凭据操作或部署流程。

## 预留、持久化和旧 unknown

scope 由原本机 nonce 与原生实际账号身份计算；请求不能换 scope。固定 root 的 `host-identity.json` 记录原 nonce 的 hash，nonce 替换或部分目录不能另开预算。所有步骤使用同一个 `state/workflow.lock`；正常 runner 可传其实际已持有的 `RunLock`，不会嵌套锁。

`issue_permit` 读取真实当前绑定、既有有效授权、完整 account holds 和完整 before 后，逐个 exact named material 加上 Mora 预留。它读取所有旧 account 目录；未终结、unknown、部分写入、格式异常、原件 hash 改变、terminal/outcome 不匹配都阻止新的步骤，不因换 run、步骤、授权 ID 或游戏日绕开。已成功的实际消费累计到原 grant 上限；同授权 ID 的原 grant 内容/digest 不能改变。当前已认定的显式零库存回读路线尚未接线，故 owned==required 和 Mora owned==required 均拒绝。

记录采用固定私有路径、无 reparse/symlink 祖先、CreateNew、flush/fsync 和精确字节读回；每份记录带注入的本机密钥 HMAC，terminal 链绑定 reservation/outcome 的原始 SHA-256。HMAC key 不写入记录；nonce/密钥不能被本模块重置或重新生成。Windows 文件 flush 对应同步文件持久化，POSIX 另同步父目录。文件损坏/写入异常保留原记录，没有删除、overwrite、退款或恢复重放 API。

已签名旧记录仍须重新核对全部 before、submission、after、world 的原始来源 SHA 链。即使 no-submission 曾释放预算，该旧 run/step 也不能再次执行。permit 还要求同进程原对象身份；重启后不能加载 JSON 重建 permit 或重放旧步骤。

其他消费模块当前未调用这个新核心；“所有账号消费阻塞”是未来共用 runner admission 的接线约束，不是本轮对现有消费者已经生效的声明。正式接线必须让所有消费 admission 共同读取这个 ledger，并让此核心的 account-holds reader 完整枚举既有各账本。

## 原始认证及最终 native 门禁

每个 `RawSource` 绑定实际 binding SHA、capture session、原始时间、固定私有相对路径、长度和原始 SHA-256。模块核对原件真实字节、路径与时间，要求 before 的角色/天赋入口/详情/popup/Mora 类别和每个具名 material tooltip 双来源；after 要求角色/完整详情/Mora 及每个旧材料 named inventory 双来源；最终世界要求真实有序双帧及新鲜性。

before 全部原件须在本游戏日。准备过程的角色/详情/tooltip 可以早于最终 popup；最终 popup 的有序两帧和 before 接受时间须仍在 1500ms 内，原件及旧账本 I/O 后、创建预留前还须重新核对两帧真实 capture 时间，较新的摘要不能刷新旧 popup。较长准备过程的完整连续时间线由原生严格 verifier 认证。account-holds 来源是受信完整枚举器本次保留的清单及其完整历史原件 hash 链；不能把历史 journal 伪称为当前 capture，清单完整性必须由这个受信 reader 负责。

这些形状、来源 hash 和类别检查不等同于原始图像认证。本模块不 OCR、加载模型或验证截图像素，不能靠类别标签或布尔值建立可信证据。未来原生 adapter 只可在严格 parser 已独立重算完整原始角色三帧、天赋入口连续三帧、详情/完整费用/具名 tooltip、固定 +3、原始模型与 loaded assembly/binding/time 后发布 receipt；成本不完整、缺项、零数不可证明或模型不一致均拒绝。

未来 `ITalentTransactionAuthorization` adapter 必须使 Host 固定 reservation 与实际 Native24 同进程 request/binding/capture session/原生 journal 完整一致，并保留原 `commit_armed` 的 CreateNew/Flush(true) 单次提交门。最终 native 仍须在实际持有的 runner semaphore 和当前绑定下重新验证最后 popup 的完整价格/库存、真实按钮几何、≤1500ms 新鲜性与原授权截止，再且仅一次提交。Host permit 不能单独授权 input；任何 raw JSON serialization 或跨进程 IPC 不能替代这条受信最终门禁。此 adapter 与最终门禁目前均未实现/启用。

`finalize` 不接收调用方结果，只从受信 reader 取得认证 outcome。Success 要求真实 native commit 在原截止前，after 基础等级精确 +1、同标题/+3、每种旧材料及 Mora 精确减去完整原费用，并在这些独立核验后有新的世界双帧。NoSubmission 要求 native 全部 journal/正面输入边界证明绝未 armed/提交，再有世界恢复；“没看到事件”、取消/异常和状态布尔值不能释放预算。unknown 不写 terminal、不释放任何预留。原截止过后允许保存已发生消费的独立结果和恢复证据，但不再允许任何 input 或新 reservation。

## 离线验证

`tests/test_talent_transaction_authorization.py` 使用明确标注的纯临时 fixture 和私有受信 port 替身；它不启动游戏/BetterGI/.NET，不读取真实授权，不创建真实 grant/key，不执行合成或升级。测试验证策略和持久化失败封闭；不能作为真实原始图像、完整 account 枚举、native gate 或单次消费验收。

```powershell
python -B -m unittest tests.test_talent_transaction_authorization -v
```
