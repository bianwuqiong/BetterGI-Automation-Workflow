# 只读天赋升级预览（2026-10-12）

第14层叠加固定基线及前十三层。接口为`dispatcher.InspectTalentUpgrade(characterName,talentType,ct)`，异步返回camelCase JSON字符串；类型只接受普通攻击/元素战技/元素爆发。只观察，不执行最终确认、升级或资源消费。equippedWeaponXP与自动升级执行器不在本层。

复用现有角色筛选/选择并停留在属性页，随后独立官方全名三帧核验。指定天赋入口后读取完整标题、类型、显示/基础等级两帧，再仅点击左下升级导航进入预览。一般角色读数的旧ROI保持；预览的较宽等级裁剪复用原完整等级/字形颜色/固定+3标准。背景暗化后的角色名字不作为新身份证明，carryover绑定刚刚核实的详情且其后没有角色选择输入。

预览要求完整属性变更/所需材料/取消/确认页标、基础当前→下一等级及完整整数成本。物品图标最高具名匹配仍至少0.75；tooltip要求实际完整名称OCR候选与卡片模型名字一致、拥有量交叉相同。只规范方/角引号，不替换稀有汉字。tooltip培养需求分母是聚合目标，不能当下一等级成本。微型卡片slash误识别时仅使用几何斜杠及左右独立完整整数/字框/边缘证据，绝不替换OCR数字为斜杠。

Raw证据包括尺寸、时间、区域、OCR框、whole/detector文本、slash位置/相关性/墨点、左右拆分框和整数、等级字形颜色及亮/白/青/冲突像素、加成文本、图标名字/分数、tooltip普通及有界4x高对比OCR候选和实际恢复世界两帧。只在已识别的角色/详情/预览/材料tooltip页面按Esc；未知页面不回退通用确认。150秒linked读取期限，另有最多10秒独立取消/世界清理期限。

返回`task=talent-upgrade-inspection`、`status=success|unknown`、`readOnly=true`、官方`characterName`、`talentType`、`talentName`、`currentBaseLevel/nextBaseLevel`、`materials[{name,owned,required}]`、`mora{owned,required}`、`evidenceVerified`、`mainUiRestored`、`confirmationSubmitted=false`、`observedAt/reason/rawReportPath`及`evidence{characterIdentity,detailIdentityCarryover,preview,materialTooltips,rawFrames,...}`。unknown顶层结果保持null，实际原始标量仍保留。完整原JSON尝试保存于本机`BetterGI_custom/log/talent-upgrade-inspection/<UTC时间>-<nonce>.json`，上层仍必须另存原文并独立验收。

本轮最终Release x64构建0错误，所选纯逻辑22通过；生产parser的私有静态组合回放1项失败，明确保留。已观测到详情、预览等级、两种具名卡片模型及完整数量/摩拉整数可解析；压缩小摩拉图标仍约0.52低于原0.75阈值，稀有材料名称OCR不完整以及tooltip数量方法/边缘不一致仍为unknown。最终静态测试停止在1536的tooltip数量边界，未宣称完整1920静态回放或实时预览通过。缺私有清单/图片不会空return或skip当成功；真实路径/期望库存全在忽略的清单中，公开测试仅匿名数字。

本层按严格只读入口部署供下一次物理1920新鲜截图诊断，静态负例不阻断安全只读未知返回，也不允许资源执行器借这些结果消费。前十三份补丁字节保持，MODIFICATIONS显著记录本层及前层实际验收范围；实际升级尚未执行。

部署只替换顶层引擎文件；181份User文件前后SHA一致。DLL14：`A40D27FB7320BA83E7677AB2A34C5B52FACF365893E669A2AE792C203A16AABE`。补丁14：`646F415606EB3A9D290DD4D3AE63516CCE6EE826127D528C5AEE201E4C5D52A3`。正向在基线及1..13后和源码反向检查通过；实际DLL13备份及新DLL14/相关完整源已冻结本机审计目录。公开补丁无真实余额、实际账户材料数量或私有图片路径。
