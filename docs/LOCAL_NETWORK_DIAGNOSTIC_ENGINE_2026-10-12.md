# 秘境掉线只读分类（2026-10-12）

第七独立 overlay 叠加于固定 BetterGI 基线 `d8c0aa238a949d7d74bfe5087f3a48e39771575a` 和前六份补丁，原补丁保持。修改版继续遵循 GPL v3；不将原始实机截图、游戏 UID、模型资产或用户状态纳入补丁。

## 现有证据与修改边界

真实秘境战斗取得一次钟离长 E 冷却证明后，后续严格切换未获双帧身份核验。失败后实机画面明确显示中央“连接已断开”标题和“连接超时”正文，HUD 保留上一出战角色。此证据支持掉线弹窗分类，不能把失败归因为角色切换等待时间过短。原护盾、角色号位、双帧身份、冷却阈值和重试窗口全部保持原状；未增加盲目补 E 或放宽识别。

旧 native 日志只有身份核验异常，未分类网络弹窗。本轮新增 `dispatcher.ReadGameNetworkSnapshot(token)` 只读 JSON 接口，以两个新鲜独立截图和通用弹窗角标，加固定区域完整标题及正文证明 `blocked_network`。返回 first/second 原文、时间、宽高、modal 页标；不点击确认、不重连、不移动、不消费。弹窗缺失仅为 `not_observed`；`connectivityVerified` 始终 false，不能据此宣称网络在线、游戏服务可达或 VPN 传输健康。

## 失败事件

受保护 `RunAutoDomainTask` 的非取消失败后，额外执行一次有界只读弹窗采样。仅在掉线双帧成立时发 `task=domain-network-interruption`、`status=blocked_network` 的事件，含 runId、stepId、stage、observedAt、first/second 和原始异常。stage 仅区分 shield_identity 与 domain_execution；它是失败分类，不是消费验收。

原异常继续抛出，`resourceOutcome=unknown`，不改变任何收据、余额、已成功的前一步或当前 unknown 步骤，不自动重放。诊断不可用也不能覆盖原异常。真实消费与失败后的余额必须由外层独立核验；网络恢复不自动解除消费 checkpoint。

## 验证

```powershell
dotnet build better-genshin-impact/Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj -c Release -p:Platform=x64 --no-restore
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_network_diagnostic_engine.ps1
```

私有图像复验独立标记 `Fixture=PrivateNetworkDisconnect`，显式指定 `BETTERGI_PRIVATE_NETWORK_FIXTURE_DIR`。缺失图像必须失败，不能空返回计通过。保留原窗口边框与 client 几何，在内存按实测 client 裁剪，以1536/1920宽度运行实际 production 页标和OCR reader；这是静态单帧分类复验，不冒充 live 双帧或联网证明。BetterGI 活动时不得启动 testhost 或部署，共享 IPC 必须由主代理协调。

本轮 Release x64 构建0错误。所选网络及原护盾/秘境纯测试60通过、0失败、0跳过；私有现场图像测试1项通过，在1536/1920宽度均由实际production reader识别到modal角标、完整断开标题和超时正文。此测试使用同一张保留静态画面，不能称 live 双帧或实际联网验收。实时采样仍须取得两个新鲜独立帧。

补丁在固定基线与前六份补丁之后正向检查通过，当前源码反向检查通过。部署只替换顶层引擎 DLL/EXE/deps/runtimeconfig 并保留可恢复备份；110份 User 文件部署前后 SHA-256 一致。DLL SHA-256：`53C3AF3401F6349ECA9E61A7E6276B71F7F103BF64962254851CB68A9534D882`。第七补丁 SHA-256：`DA115CB70C95F0729B583314A0AE4AD0D5B4FB034E5D149990F3DEFE6F0F8EAF`。未修改角色/护盾/号位识别源码及阈值；未重放真实失败步骤。
