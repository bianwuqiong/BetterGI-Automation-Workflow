# 四库存只读读取与预览原生诊断（2026-10-12）

第17独立overlay接固定基线及前十六层。四库存代码来源为本会话独立草稿，整合时补强2px边界、实际模型分数、失败证据保留及独立世界恢复，并移除草稿的假设转化规划。此前补丁字节不变。

`dispatcher.ReadWeeklyConversionInventory(requestJson="{}",ct)`返回camelCase JSON字符串。默认只读113060残火灯烛、113061丝织之羽、113062否定裁断（角色培养道具）和113021异梦溶媒（贵重道具）；ID/完整名称在本机ItemV2及固定材料数据交叉核对，101016不接受。JSON只能选择此白名单的非重复子集，不能传分类、坐标、确认、费率或重放指令。读取期限114秒，独立清理最多6秒，入口/退出世界均要求新鲜截图。

结果包括source/category/readOnly/status、primaryReason/cleanupReason/reason、mainUiRestored/cleanupCompleted、observedAt/rawReportPath、inventory按ID的int或null、accepted observations、每ID最多2个rejectedObservations及实际worldFrames。每观察包含selection及独立first/second；每frame保留尺寸、焦点/弹窗、tab/headerRegion/headerRows、iconName/iconScore/iconRegion/iconMethod及stack的完整名/原始数量/检测框/选中框四侧像素。模型仍至少0.75且有限数；完整名字和数量四边至少2px按宽度缩放，完整整数拒绝缩写/斜杠/前导零。四侧border的实际位置/样本计数必须匹配选中单元。不存在物品或无法验证时null，显式已证0与unknown区分。清理失败全部数量null；相同时间/重复世界记录不能证明恢复。私有报告保存在`BetterGI_custom/log/weekly-conversion-inventory/`，不包含任何转化/使用/确认/战斗/升级入口。

预览继续只读。材料数量以父扫描实际行作sourceCountRow，横20px/竖5px（按宽度缩放）pad后与实际card相交，不能带入邻项；旧8px失败读数放在initialReading。摩拉只在原903/797/275/55区域存在唯一完整ratio检测行时，以该真实字框四边12px重读；最初whole文本/原区域保留，不能抹掉幻字或通过常识补数。微型斜杠仍沿用已审查几何证据，未实际证明就unknown；本层不猜原生像素的斜杠原因。

币模型明确选择实际背景padding区域`(845,791,53,53)`、variant `real_background_padding_8_reference_53`，不按多区域最高分挑成功。旧37px名字/分数/区域保留；主模型至少0.75，旧区域若有高置信非摩拉冲突也拒绝。静态压缩币图仍被错分类且低于阈值，不能称货币已核实。

完整preview页标确认后，仅把当前forceNew native SrcMat无裁剪/无缩放/无改色地lossless PNG保留在私有`log/talent-upgrade-inspection/native-frames/`。privateCapture绑定observedAt、尺寸、pixelType、path、PNG SHA和原始像素SHA。PNG仅诊断，不能替代数值、名字、新鲜度或消费证明；登录/认证画面不符合完整预览条件，不保存。上层仍独立验证所有raw字段和同帧出处。

本轮Release x64构建0错误；所选纯58项通过（周本20、原始PNG像素保持1及已有/新增预览身份37），0失败/跳过。私有静态padding诊断1项通过，仅验证固定variant、初始失败保留和裁剪结构；币仍unknown，不宣称实际预览成功。此前私有组合的完整tooltip失败保留；真实原生PNG尚待下一次零消费实机检查后精确审查。第16实际全名三帧、正确技能/基础等级详情双帧及世界恢复已分别验收，本层不公开库存、运行标识、时间或图片，不据部分成功宣称升级。

最终确认、周本转化和实际升级都未接入。完整对应源/显著变更和补丁序列同步后，仅部署顶层引擎，User文件哈希保持，旧DLL16及新DLL17/完整相关源冻结本机审计。

部署只替换顶层引擎文件；193份User文件前后SHA一致。DLL17：`F44D73ED73376D8C4F1C51970818A0F39496D867C75E3C6AD362BE9D2726D113`。补丁17：`F210A454BB803E965AC38746C792A6AC390B9A557C3D43FB606EA031E26A8AFD`。明确repoRoot断言的独立私有Git中已实际逐层检查/应用基线后1..16，17正向检查及真实工作源码反向检查均通过；旧DLL16备份及新DLL17/相关完整源冻结本机审计目录。
