# 第二十层：独立具名数量读取及滚动完整角色名

基于固定对应源码及完整1..19补丁序列；所有历史补丁和unknown记录原样保留。本层没有升级、转化、资源确认或通用确认入口，通用8材料草稿留后续独立整合。

四种周本资源的旧 `initialStack` 完整保留初始标题区域、115×22计数区域、无检测原文、检测行、同帧时间及选中轮廓。新标题ROI为 `(1280,110,540,78)` 按客户端宽缩放，只改变本独立reader，旧矿石与共享库存helper不改。新的 `countReading.sourceRegion` 由旧RawCountRect的Y减pad、高加2pad得到，pad=max(1,round(8×cardWidth/125))；不更改原像素或OCR框以凑边距。

确定的单一处理方法为 `grid_hsv_foreground_exact_dual_ocr`：3x Linear、HSV最大饱和140/明度210、原轮廓高度/面积/底部位置过滤，并拒绝宽高比超过3的横条。全部组件与过滤结果、union以及floor/ceil映回的实际前景区域均保留。前景等比例Nearest到48px，白色画布四向24px自然识别留白；OcrScale=1，不多变体择分。归一化检测框逆映原来源框，两套四边边距均保持至少2px。完整非负整数、无检测与检测原文按既有 Unicode 兼容归一化和空白规则一致才可验收，单字也须实际检测框；原文保留，缺失不是0，不把1/7相互替换或删除波浪及其他文字来修数。

本机受审配置值8为V6；实际V6 detector对单字无框的失败另存私有诊断。生产采用固定双模型：实际配置V6的WithoutDetector＋固定bundled PaddleV4 detector/rec，必须在同一输入一致。模型版本不由调用者提供，不改全局OCR设置；受审配置之外保持未知。`countReading.modelEvidence` 明确rawPaddleConfig=8/rawPaddleName=V6、fixedDetectorConfig=7/fixedDetectorName=V4、五个实际bundle文件相对路径/长度/哈希与整个会话只读锁；每帧 `rawPaddleReadback=8` 必须匹配。Host必须从可信运行目录独立重读配置和模型文件，不能从raw任意绝对路径打开文件或仅信布尔。

`stack`的新CountMethod、CountRegion/Rows/RawCountText必须精确绑定 `countReading`；旧 `initialStack` 必须同帧、同选中矩形/轮廓且保留旧形状。有效旧读数若冲突拒绝。图标至少0.75、精确页名、实际全名、独立两帧和世界恢复仍需原始证据，私有截图/哈希不提升弱身份或未知数量。

姓名入口 `characterIdentityMethod=bounded_rolling_exact_triple`，最多12秒/41张、300ms只读观察，不重新选角色。完整有序 `characterIdentityTrials` 留下标点错误及原始字框/私有PNG；`characterIdentity`只能是首次连续三张通过原exact姓名/四边2px/新鲜度/总5秒判据的末三张，不能删坏帧、修句号或挑旧三张。第十九层入口双帧及点击前第三帧绑定继续保持。

Release x64构建零错误。限定测试112项全部通过，零失败/跳过，含111纯测试和1私有回放测试。真正8张1920原PNG按生产方法回放24次，覆盖V4/V5/V6原无检测＋固定V4检测；当前V6四个完整标题及数量均严格通过。私有期望只在忽略manifest，公开测试没有实际账户数量或图像。该回放不是实时新鲜验收；第20完整角色预览与四库存仍待独立实机检查。

部署后的独立新鲜只读检查已通过四种周本材料的完整名称、选中轮廓、固定双模型数量双帧及世界恢复，工作流另行核对五份实际资产和当前配置，没有转换、升级或消费。另一个新鲜天赋检查的滚动属性页身份已通过；天赋列表仍拒绝，因为沿用的右侧属性页姓名区域在此页实际显示技能名称，不能当作当前角色名。该失败保持未知且世界恢复通过，下一层仅修正此页面实际全局身份来源，不降低完整姓名或候选几何标准。本段是部署后验收，冻结构建快照中的验收状态仍保留当时事实。

部署仅替换顶层引擎文件，226份User文件按当前授权新增文件后的状态逐个SHA核对完全不变。DLL20：`C8862A4EE024F23B57942E1FDFD217CCCB711165CA733B6842CE7D23EE374C13`；补丁20：`2F003A189643CA19D26A1282ABAA9B8DAAC863DFF157FC2AD16E38EB4F169A45`。真正isolated固定基线1..19后20forward及主源reverse检查通过；旧DLL19及新DLL/完整对应源/序列只在本机审计冻结，历史补丁字节不变。
