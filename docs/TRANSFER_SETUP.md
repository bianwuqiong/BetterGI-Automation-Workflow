# 跨电脑开发包 / Development transfer

## 中文

本快照是截至 2026-10-11 的开发版本。先阅读 [交接记录](DEVELOPMENT_HANDOFF_2026-10-11.md)和 [源码与脚本清单](TRANSFER_MANIFEST_2026-10-11.json)。清单固定源码基线、完整增量补丁及关键脚本的 SHA-256；此包不包含 BetterGI 可执行程序、模型、原神文件或私人运行状态。

### 源码与依赖

Windows 10/11 x64、Python 3.10+、Node.js 22、.NET 8 SDK；录屏另需本机 FFmpeg 与 ffprobe。初始化第三方子模块和模型依赖时遵循 BetterGI 基线仓库说明。

在本仓库根目录执行：

```powershell
git clone --recurse-submodules --branch automation-baseline-2026-10-08 --single-branch https://github.com/bianwuqiong/better-genshin-impact.git better-genshin-impact
git -C better-genshin-impact rev-parse HEAD
# 应为 d8c0aa238a949d7d74bfe5087f3a48e39771575a
git -C better-genshin-impact apply --check ../patches/cultivation-engine.patch
git -C better-genshin-impact apply ../patches/cultivation-engine.patch
dotnet build better-genshin-impact/BetterGenshinImpact.sln -c Release
```

补丁从固定基线到当前修改生成，包含新增源码和 C# 回归测试，不是依次叠加旧补丁。已应用过旧补丁的工作树应保留备份，再另建干净基线应用本补丁。不要在未知改动上强制 reset 或覆盖。

本机迁移另外发现启动时序问题，已生成独立 `patches/local-startup-fix-2026-10-11.patch`。仅在上述完整迁移补丁之后应用一次，先做正向检查；已应用时反向检查应通过。详见 [本机启动修复与验证边界](LOCAL_STARTUP_FIX_2026-10-11.md)，原始完整补丁保持不变。

第二次只读实机进入角色识别后，天赋 OCR 保留未知。另有 `patches/local-character-talent-fix-2026-10-11.patch`，仅在启动修复之后单次应用；其严格解析与有界诊断的 [说明和验收边界](LOCAL_CHARACTER_TALENT_FIX_2026-10-11.md) 不代表本机天赋识别已通过。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/initialize_config.ps1 -IncludeCultivation
python -B -m unittest discover -s tests -v
node --test bgi-scripts/AutoGameCultivation/tests/*.test.js
node --test bgi-scripts/AutoGameMaterialRoute/tests/*.test.js
node --test bgi-scripts/AutoGameCombatRehearsal/tests/*.test.js
```

将构建后的完整 BetterGI 输出及其运行依赖部署到自己的 `BetterGI_custom/`，编辑 `config/settings.json` 中的路径。首次手动打开 BetterGI，建立其本机 User 配置和 OneDragon。示例默认前台便于诊断；稳定后再配置 Child Session。Windows 密码通过本机安全凭据界面输入，不放入代码或聊天。

`cultivation.example.json` 默认只读、零树脂预算、关闭 Boss/合成/路线/周本。`party-preparation.example.json` 只是已测试队伍顺序的示例，需要确认新账号实际四人和策略。路线文件通过本机 BGI 订阅获得并核对哈希；此包不再分发第三方路线。新机库存、材料完成情况、开放日、画质配置和网络状态均重新读取。

### 测试边界

离线测试不启动游戏，也不证明新电脑识别成功。C# 全部测试还依赖上游测试资源和模型。干净源码构建后的广泛测试有107项因未提供的图像等资源失败，512项通过；这不是完整通过。旧 `PartyAvatarInitTests` 有七项依赖PNG；`ResinSnapshotImageTests` 和标记 `Fixture=PrivateProtectedLoading` 的复测依赖未公开的本机截图。不要把环境变量为空时的方法返回计为图像验收。

迁移脚本按清单选择此次修改的开发回归类，并明确排除私人树脂／加载图像类或标记，以及 `TpAreaSelectionTests.RealRegionMenuFramesRequireTheNormalMapControls` 的两张未公开区域菜单录像帧；保留该类其余纯逻辑回归。这是有界开发回归，不能称上游完整测试全部通过。新机另外建立自己的图像夹具复验：

```powershell
powershell -NoProfile -File scripts/test_cultivation_engine.ps1 -SourceRoot better-genshin-impact
```

此入口使用显式 x64，并在对应本机补丁存在时把启动与天赋新增纯回归类纳入；若补丁文件存在而新增测试源码缺失，立即报错，不把旧基线测试数当作本轮覆盖。`Fixture=PrivateCharacterTalent` 与其他私人图像回归仍独立排除；有真实本机夹具后另行运行，缺图不能以空返回记为通过。

完整移植顺序：离线测试 → `run_cultivation.ps1 -DryRun` → `run_cultivation.ps1 -ExecutionMode foreground` 只读实机 → 检查该 runId 的 `result.json` 与 `agent-context.json`。核实全部未知项和退出、恢复后，才在新机当前游戏日明确授权消费并建立自己的账本；旧机器授权不随代码迁移。

保持 TUN 可用。需要游戏直连时配置本机代理规则，不能复制旧机器临时服务器 IP 或关闭 TUN。保持默认亮度、1920×1080 窗口、极低画质及兼容模式，使用现有画质保存和恢复机制。

## English

Use the pinned BetterGI baseline plus the complete patch, then build with .NET 8. This source-only snapshot excludes models, binaries, accounts, private recordings and authorization ledgers. Initialize local configuration with `-IncludeCultivation`, run the Python and all three JS test suites, and perform a read-only live scan before authorizing spending on the destination computer. Private-image tests and missing upstream PNG tests require separate fixtures and are not portable acceptance evidence. See the Chinese commands above and the development handoff for remaining work.
