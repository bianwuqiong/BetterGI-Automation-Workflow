# 摩拉与武器经验库存读取边界（2026-10-12）

此第六独立 overlay 叠加于固定 BetterGI 基线 `d8c0aa238a949d7d74bfe5087f3a48e39771575a` 和前五份补丁。前五补丁不修改。本轮仅增加只读资源证据，不启动自动升级、强化、合成或消费。仍遵循 GPL v3 非官方修改版源码提供规则。

## 缺口原因

培养材料 `202` 摩拉在 `upstream/data/materials.json` 中明确 excluded，JS 读取与缺口计算据此排除。摩拉不是网格中的具名物品堆，旧 `CountInventoryItem` 网格扫描无法读取其余额。本机实际贵重道具页面在左下显示原石及摩拉，右上只有背包容量；此前假定右上余额的草稿没有接入执行或部署。

`CountInventoryItem` 已支持 Weapons 页的精锻用矿石，并滑到底部读取数量，但该接口为单帧网格 OCR。严格 `ReadBackpackInventory` 原只允许 114 武器突破材料。本轮增加独立 `category=weaponExperience`，仅接受下列固定 ID 与完整名称，不允许交叉配对、摩拉、任意资源或坐标：

| ID | 名称 |
|---|---|
| 104011 | 精锻用杂矿 |
| 104012 | 精锻用良矿 |
| 104013 | 精锻用魔矿 |

复用原 Weapons 末页扫描，并复用已有选中物品四边框、完整名称、原始数量和两个独立新帧协议。找不到或证据不足继续 unknown。默认无 category 的 114 请求保持原行为。

## 摩拉候选接口

`dispatcher.ReadMoraSnapshot("{}", token)` 返回 JSON：`materialId=202`、`materialName=摩拉`、可空 `balance`、`verified`、`observedAt`、`mainUiRestored`、`cleanupCompleted`、`reason` 及 first/second 原始证据。

接口先要求新鲜世界双帧，仅打开背包并选择已识别的贵重道具 tab，不点击币图标或确认按钮。画面必须同时证明贵重道具 checked 页标和完整页名。摩拉币图标以现有 ItemV2 模型分类，最高候选必须为完整名称“摩拉”且得分至少 0.75。数字必须为完整非负整数，原始无检测 OCR 与区域 OCR 单行相符且不贴裁剪边缘；两帧数值相同、时间不同且新鲜。任何条件不足或主界面双帧恢复失败均返回 unknown/null，不补成零。

默认坐标由本机实际贵重道具页面校准，采用 1920×1080 client 基准：coin `(354,1000,37,37)`，balance `(397,1000,140,40)`。请求可给 `iconRegion` / `balanceRegion`，但仅限邻接的左下摩拉区域；更左侧原石区域禁止进入。未暴露任意点击。小币图标与背包物品图标分布可能不同，因此必须独立复验模型分类，不能只因余额双帧正确便宣称身份通过。

## 浓缩配方斜杠修复

本机零预算配方探针遇到原粹材料行的 `/` 被 OCR 读为 `1`，完整原文变为五位数字，因第五补丁严格成本门槛而无提交退出。第六补丁不把 `1` 替换为斜杠，也不把旧兼容 `[/17]` 当成本证据。

新 reader 同时要求浓缩配方图标、原粹材料图标和右侧完整“浓缩树脂”标题。材料数量微区域先通过连通块及负斜向相关性证明一个独立 `/` 笔画，再分离左右数字裁剪并分别四倍放大 OCR；左侧须为完整 0 至 200 库存整数，右侧须为确切 60。全行 OCR 只作为诊断。三次独立 forceNew 捕获的原粹/浓缩读数稳定后才发布 `RecipeCostVerified`；40、错误标题、无斜杠、竖直 1 或数字不足均无提交。

私有两帧以原 client 1536 宽及规范 1920 宽复验，微区域与完整 production reader 均通过。此为静态图像复验，不替代 fresh 实时三帧或合成后的真实余额核验。

## 等级经验与摩拉成本尚未覆盖

现有 rulebook 提供角色/武器突破与天赋材料，包括相应摩拉。`requirements.js` 未提供逐级角色/武器升级经验或升级摩拉。原生角色读数有装备武器名称、等级和等级上限，但没有当前等级内经验、目标武器稀有度的独立证据。仅有三种矿库存不足以推出完整等级升级缺口；必须补可信逐等级经验表、稀有度、当前已积累经验和实际 UI 摩拉消耗范围。此轮不凭估算提供矿石换算或升级预算，更不自动执行升级。

## 验证与私有夹具

```powershell
dotnet build better-genshin-impact/Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj -c Release -p:Platform=x64 --no-restore
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_resource_balance_engine.ps1
```

只可在 BetterGI 退出后运行 testhost 或部署，防止共享单实例 IPC 干扰。纯测试不依赖游戏、图片或模型；私有图像测试独立标记 `Fixture=PrivateMora`，显式设置 `BETTERGI_PRIVATE_MORA_FIXTURE_DIR` 后才能运行，缺图失败而不空返回计通过。私人原始窗口帧须包含明确页标、真实币图标、完整币数及窗口/client 边界；至少两个独立捕获，鼠标移离币图标。另需原石相邻区域的负例和错误 tab/弹窗负例。原始帧、UID、余额与模型资产不进入公开源码补丁。

本轮 Release x64 构建零错误。所选六类纯测试 83 通过、0 失败、0 跳过；独立 `PrivateRecipeCost` 两项测试通过，每项分别验证 1536/1920 宽的实际微区域及完整 production reader。Mora 私有模型两项测试均失败：小币图标的最高候选为其他物品，得分约 0.431，未达到 Mora 身份标准。因此摩拉 API 保持 unknown，不能声称本机余额已验收；武器矿读取也仍待实时具名双帧验收。

发布前仅修正三个新增测试文件的隐私边界，生产源码不变：摩拉纯测试全部使用匿名合成数字；配方纯测试使用匿名合成库存；私有配方文件名及预期库存移至忽略的本机 fixture manifest，由 `BGI_PRIVATE_RECIPE_FIXTURE_MANIFEST` 显式提供。manifest 必须包含两个 `cases`，各项 `file` 指向保留原始帧、`expectedOriginalResin` 为明确库存整数；缺失或无效期望不能默认为零，也不能空返回记通过。成本60保持公开固定契约。私有Mora模型失败边界保留，没有因隐私修正升级为通过。

第六补丁在固定基线及前五补丁之后正向检查通过，当前源码反向检查通过。旧五份补丁保持原内容。部署备份旧顶层引擎文件，101 份 User 文件部署前后 SHA-256 一致；没有覆盖运行 User 或配置。DLL SHA-256：`945493FF75D4E4DE5A5E49CB236A590F13B4B7B1367EE50B61D30B2C8EA2AC9A`。第六补丁 SHA-256：`2A39FF6387722DEC289DB84F7BE36CF655278C056F0A4AB98ECB625A2EDC507D`。成本修复已部署供主代理开展零预算实时配方探针；不能把83项纯测试或静态图像通过当作真实消费验收，更不能复用第五补丁149项统计作为第六结果。
