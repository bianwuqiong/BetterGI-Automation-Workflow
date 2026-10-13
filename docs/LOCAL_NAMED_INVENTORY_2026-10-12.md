# 第二十三层：绑定实际采集的只读培养库存

在固定对应源码完整1..22后应用独立第23层。历史补丁、冻结源、原manifest和未知结果均保持原字节。游戏已正常退出后的离线开发；本层 `actualNamedInventoryVerified=false`、`actualBoundMoraVerified=false`，没有实时验收，不重新启动游戏。

`Dispatcher.ReadNamedCultivationInventory(string requestJson, CancellationToken? customCt=null)` 与同名SoloTask（config.requestJson）接受 runId、stepId、phase（before/after/diagnostic）和1..8个互异完整 materialId/materialName。只准实际ItemV2 CSV中唯一ID/全名、合法培养类别及原模型原型，跨class名称冲突拒绝；113021仅沿已审贵重道具路线。请求不接受库存、成本、坐标、绑定或模型路径。每类别最多30页、每项最多两次双帧观察、主体174秒加最多6秒已知背包清理；missing为null，完整明确0才可为0。

`ReadBoundMoraSnapshot(string requestJson="{}", CancellationToken? customCt=null)` 与同名SoloTask复用原Mora image-only读取，实际CSV material:202/摩拉及Item模型锁同样必需。主体20秒加清理6秒，未知余额为null，不默认0。旧Mora与周本接口保持；新只读桥和捕捉构造器为内部原生调用。

`ReadNamedInventoryBinding(CancellationToken? customCt=null)` 只返回实际原生绑定收据，须真实TaskRunner持锁scope；不抓图、不导航。它可与控制器的可信OS前置读取交叉验证，然后匹配新读取的binding。所有三个入口均不接受caller伪造绑定，重复操作由独立gate阻止。

完整JSON包含实际CSV/Item ONNX相对路径、字节数和SHA、resolved实际CSV行、inventory/null、accepted/rejected原始pair、entryWorldFrames/worldFrames、rawFrames、gameBinding/captureSession、primaryReason/cleanupReason与原报告路径。rawFrames逐次保存 actualCapture（真实同步BitBlt调用开始/返回时间、返回矩形、像素类型、binding）、privateCapture（原生PNG/像素SHA与时间）和recognized原对象；world帧额外保存六个固定原模板/Recognition.json的路径、SHA、实际ROI/阈值/匹配及模板像素。原图仅留本机日志，未知／认证场景不保存、不输入。

binding包括真实PID/HWND、精确十进制字符串processStartedUtcTicks、exe路径、实际SystemInfo对象代次、BitBlt实际会话generation和capture程序集MVID。只支持审过的同步BitBlt与原生1920×1080，返回前后均核实际进程/窗口/前台/坐标/后端生命周期。不得用未实现的forceNew、Now、本地伪sequence或WGC缓存假装新采集。输入前实际返回年龄须≤1500ms；超过即未知，不恢复焦点。

strictModels明确本次只读锁内新建原ONNX CPU无缓存实例：V6无检测读数、固定V4检测/识别的原5 countModel资产，以及V6检测原资产第6项。配置要求受审cfg8，前后读回；Item CSV/模型和OCR文件从加载到最终验证保持只读锁。原数量算法、两路完整ASCII整数、模型.75、四边2px及选中边框全部保留，不做1/7修复、文本清洗、模型择优或数字估计。原周本与Mora body通过image-only重用，避免算法复制。

恢复world只从已核验两类完整背包页标/选中tab/noPrompt/focus允许一次Esc；未知层只等待，未获独立world双帧则不发布。原模板本次fresh加载，positive Paimon及negative domain/modal/revive/map六项全部记录。TaskRunner实际持锁scope对继承子任务有共享失效标志，捕捉/每次输入/全局trigger恢复持续核所有者；新网格守卫模式用纯等待，旧调用行为不变。

消费Session、CurrentPopup、After事务、转换、使用和最终升级确认均未接线。phase=after只是只读标签，不能被当作升级执行成功。本层不能放行实际消费；未来事务仍需独立许可与完整前后证明。

Release x64构建零错误；限定新/共享纯回归79项通过、0跳过，覆盖CSV/name唯一性、8项界限、坏初始原文保留、双模型、边缘/边框、null/明确0、实际调用区间、精确ticks、继承owner失效、后端代次、禁缓存与world负锚点。未运行依赖私有上游素材的大范围测试。

完整补丁正向/反向、用户文件一致性、DLL和新增Fischless.GameCapture依赖SHA见下方部署记录；私有对应源码冻结于 `state/audit-native23-deployed/manifest.json`，原运行包和User备份于 `state/named-inventory-engine-backup-20261012`。本层对应源码遵守原GPL v3与作者声明，不含账号、库存、凭据、私有截图或授权数据。

部署完成：闭锁期间game/BGI/testhost均为0；235份User文件状态前后完全一致（凭据文件内容跳过数0）。同步备份/部署顶层引擎与新capture依赖，无游戏启动。DLL23：`D8931B83B1277E484AF36C8C251206804234FA273EA5D651F640C24FBEB41DEB`；Fischless.GameCapture.dll：`F05BF69A9BA2752234BF4CFBCEAC25E06F7FA5177EEB02A6A12E59E595A52892`；补丁23：`839A651540F58BD42C50FE79376993C5272F568264373412222C81052DC2D964`。独立固定基线1..22后23forward/reverse与全部变更源码逐字重构通过。对应源/两DLL/原运行文件/序列在本机私有冻结，公开补丁序列完整1..23；实机标记仍false。
