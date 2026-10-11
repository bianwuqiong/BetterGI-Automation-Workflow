# BetterGI Automation Workflow

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](./LICENSE)
[![Tests](https://github.com/bianwuqiong/BetterGI-Automation-Workflow/actions/workflows/tests.yml/badge.svg)](https://github.com/bianwuqiong/BetterGI-Automation-Workflow/actions/workflows/tests.yml)

中文 | [English](#english)

一个面向 Windows 的原神日常自动化编排与核验项目。BetterGI 继续负责画面识别、路径、战斗和模拟输入；本项目负责一次运行的任务选择、互斥、时间预算、资源/VPN 保护、画质切换、日志隔离以及完成证据。

已保留 **2026-10-08 稳定基线**（包含 0.2.2 之后的改动），见[基线说明](docs/BASELINE_2026-10-08.md)。历史核心日常支持 Windows RDP 桌面分身与前台录屏双入口、启动前 HoYoLAB 官方网页签到，以及邮件领取、浓缩合成、秘境结算和每日委托奖励的机器事件核验。探索派遣仍缺少领取与重派后状态的独立证明，详见[派遣核验边界](docs/DISPATCH_VERIFICATION_2026-10-11.md)；仓库不提供 BetterGI 或原神二进制文件。

**2026-10-11 开发迁移快照已更新。** 最新瑞希培养流程已在开发机完成每日奖励与自然树脂清理，三个正常成功批次共37分48秒，尚未达到约20分钟目标。包含武器背包库存双帧读取、指南隐藏条目回退、单20原粹安全领奖与深灰加载修复，以及120秒以内的同run真实库存读数复用。默认配置仍只读；刀镡连续战斗、派遣重置及自动升级尚未验收。新电脑从[交接记录](docs/DEVELOPMENT_HANDOFF_2026-10-11.md)、[迁移步骤](docs/TRANSFER_SETUP.md)和[校验清单](docs/TRANSFER_MANIFEST_2026-10-11.json)继续。历史基线保持可用，不能把旧日常速度当作当前培养流程速度。

培养扩展需在固定源码基线上应用当前完整[执行引擎补丁](patches/cultivation-engine.patch)再编译，详见[构建步骤](docs/TRANSFER_SETUP.md)。补丁包含新增源码及C#回归测试；它替代旧培养补丁，不应重复叠加。源码基线＋本仓库补丁共同提供最新修改版源码。实机诊断截图、账号记录、运行授权与库存不在公开包中。

新增独立周本四库存只读入口 `--cultivation-weekly-inventory`：固定读取三种周本材料和异梦溶媒，JS/Python均重新核验原始具名、模型、数量和恢复双帧，任一不足保持unknown/null。临时零预算且不执行转换或消费；普通材料扫描保持原义。使用与证据边界见[培养脚本说明](bgi-scripts/AutoGameCultivation/README.md#独立周本四库存只读诊断)，离线测试不代表实机验收。

本轮继续开发的启动修复、库存读取优化、游戏日边界、选路与派遣证据修复见[开发验收记录](docs/LOCAL_TRANSFER_VALIDATION_2026-10-11.md)。原始校验清单描述下载包快照；后续修改用独立补丁和验收记录追踪，不能把离线测试通过当作完整实机通过。

## 与 BetterGI 的关系

本项目建立在 [BetterGI](https://github.com/babalae/better-genshin-impact) 之上，并维护一个用于工作流的[非官方 BetterGI 修改分支](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow)。修改分支改善了启动焦点、合成证据、秘境阶段边界、古树/领奖识别、邮件防吞与弹窗安全关闭、后台无窗口根实例直接激活以及桌面子会话（Child Session）凭据安全管理。

本项目不是 BetterGI 官方版本，也未获得 BetterGI、米哈游或 HoYoverse 的隶属、赞助或认可。上游代码和版权归 BetterGI 原作者及贡献者；修改版问题请先在本仓库反馈。完整声明见 [NOTICE.md](./NOTICE.md) 和 [许可证说明](./docs/UPSTREAM_AND_LICENSE.md)。

BetterGI 使用 GNU GPL v3，允许修改和再发布，但需要保留声明、显著标记修改并继续按 GPL v3 提供修改版；分发二进制时还要提供对应源码。本仓库也采用 GPL v3，并通过独立 fork 提供完整修改源码。

## 主要能力

- `core` 核心日常：HoYoLAB 网页签到（启动前）➜ 领取邮件（收取签到等奖励）➜ 合成浓缩树脂 ➜ 自动秘境清理可用树脂 ➜ 领取每日委托奖励及重新派遣。
- `extras` 扩展日常：地脉花和尘歌壶等额外奖励节点，与核心耗时分开衡量。
- 双启动模式：Windows 本地桌面分身（Child Session，后台免打扰静默执行）与前台可见模式（支持 FFmpeg HWND 窗口级高清录屏与覆盖率校验）。
- 每次生成唯一 OneDragon 配置与 `runId`，避免跨次日志和奖励混算。
- 依据库存差、树脂使用、奖励识别和明确结束事件核验结果，不把“点击过”视为成功。
- VPN 进程、可用内存、任务阶段和总时长保护；保护触发时停止本次拥有的进程。
- 自动化前保存手动画质，应用自动化低画质，游戏退出后恢复；异常中断可恢复。
- 正常执行不需要 AI；失败时可以把精简的 `agent-context.json` 交给低成本模型分析。

## 隐私设计

公开仓库只包含源码和匿名示例。以下内容由 `.gitignore` 排除：

- BetterGI 安装目录、构建产物和模型文件；
- `logs/`、`state/`、截图、进程转储和远程控制记录；
- 本机路径、账号/UID、注册表完整导出、培养目标和库存；
- `.env`、密钥、令牌、私人支付信息和二进制文件；原有公开赞助渠道和经哈希审核的赞助图片保留。

每次公开提交前运行：

```powershell
python scripts/audit_public_tree.py --tracked
```

## 环境要求

- Windows 10/11 x64；
- Python 3.10 或更高版本；
- 安装 `requirements-runtime.txt` 中的 Pillow（真实PNG/JPEG附件完整性核验）；
- .NET 8 SDK（自行构建修改版 BetterGI 时）；
- 原神简体中文界面；
- 16:9 分辨率。BetterGI 上游推荐 `1920x1080` 窗口化、默认亮度，并要求关闭 HDR/滤镜。

## 安装

1. 克隆本仓库：

   ```powershell
   git clone https://github.com/bianwuqiong/BetterGI-Automation-Workflow.git
   cd BetterGI-Automation-Workflow
   python -m pip install -r requirements-runtime.txt
   ```

2. 获取带完整 GPL 源码的 BetterGI 修改分支：

   ```powershell
   git clone --recurse-submodules --branch automation-baseline-2026-10-08 --single-branch `
     https://github.com/bianwuqiong/better-genshin-impact.git better-genshin-impact
   $sequence = Get-Content docs/SOURCE_PATCH_SEQUENCE_2026-10-11.json -Raw -Encoding UTF8 | ConvertFrom-Json
   if ((git -C better-genshin-impact rev-parse HEAD).Trim() -ne $sequence.sourceBaseCommit) { throw 'Unexpected source baseline' }
   if (git -C better-genshin-impact status --porcelain) { throw 'Keep the existing changes; use a clean source checkout for first application' }
   foreach ($entry in ($sequence.patches | Sort-Object order)) {
       $text = [System.IO.File]::ReadAllText((Resolve-Path $entry.path)).Replace("`r`n", "`n")
       $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
       $sha = [System.Security.Cryptography.SHA256]::Create()
       try { $actual = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
       if ($actual -ne $entry.sha256) { throw ('Patch hash mismatch: ' + $entry.path) }
       git -C better-genshin-impact apply --check ('../' + $entry.path)
       if ($LASTEXITCODE -ne 0) { throw ('Patch check failed; preserve this checkout: ' + $entry.path) }
       git -C better-genshin-impact apply ('../' + $entry.path)
       if ($LASTEXITCODE -ne 0) { throw ('Patch application failed; preserve this checkout: ' + $entry.path) }
   }
   dotnet build better-genshin-impact\BetterGenshinImpact.sln -c Release
   ```

   固定基线的源码标签为 [`automation-baseline-2026-10-08`](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-baseline-2026-10-08)，提交 `d8c0aa238a949d7d74bfe5087f3a48e39771575a`。按序列应用所有补丁一次，再编译；只应用原始培养补丁不能得到当前版本。已有修改不会被重置，失败或重复应用时保留目录并核对状态。使用前阅读 `MODIFICATIONS.md`。

3. 初始化不会进入 Git 的本地配置：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/initialize_config.ps1 -IncludeCultivation
   ```

4. 编辑 `config/settings.json`，填写 `bettergiExe`、`bettergiLogDir` 和 `gameExe`。可选 VPN 保护与前台进程清理默认关闭，避免在其他电脑上结束未知程序。

5. 首次打开 BetterGI，让它生成 `User/config.json`。确认自动秘境与地脉配置不允许使用脆弱树脂，再把 `config/one-dragon.example.json` 复制为 BetterGI 的 `User/OneDragon/DailyOneDragon.json`，或在界面中建立同名配置。

6. 至少填写并核实 `goals.json`。纯圣遗物目标只需要 `artifactDomain`，不需要天赋日历或书本库存；如果配置天赋升级目标，再运行 `scripts/initialize_config.ps1 -IncludeTalentPlanning` 并核实 `domain-calendar.json` 与 `book-progress.json`。缺少必要数据会阻止自动秘境计划。

## 验证与运行

运行离线测试：

```powershell
python -m pip install -r requirements-dev.txt
python -B -m unittest discover -s tests -v
```

先预览，不启动游戏：

```powershell
powershell -NoProfile -File scripts/run_task.ps1 -Task '合成树脂' -DryRun
```

保持 `checkpointOnly=false`，培养示例的 `executionEnabled=false`、零预算和独立账本限制真实消费。先做只读扫描，再逐项实机验证：

```powershell
powershell -NoProfile -File scripts/run_task.ps1 -Task '合成树脂'
powershell -NoProfile -File scripts/run_task.ps1 -Task '自动秘境'
powershell -NoProfile -File scripts/run_task.ps1 -Task '领取每日奖励'
```

确认所有节点在目标电脑上通过后，才把 `checkpointOnly` 改为 `false` 并运行完整核心流程：

```powershell
powershell -NoProfile -File scripts/run_daily.ps1 -NoDelay -Profile core
```

安装按需、无定时触发器的桌面入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_one_click_launcher.ps1
```

## 结果与 AI

每次运行的权威结果位于 `logs/runs/<runId>/result.json` 和同目录 `bettergi.log`。`results.json` 只指向最近一次真实运行，必须结合 `runId` 与游戏日使用。

AI 不是正常流程依赖。失败、部分完成或证据不足时，优先读取 `agent-context.json`；模型只能报告、要求更多证据或建议一个单项重试，不能自动执行建议。参见 [AI_WORKFLOW.md](./docs/AI_WORKFLOW.md)。

## 使用风险

本项目不读写游戏内存，也不修改游戏文件，但使用第三方自动化和模拟输入仍可能违反游戏服务条款或带来账号风险。开源许可证不代表游戏运营方授权。请阅读 BetterGI 上游 FAQ，并自行决定是否使用。

## 支持项目

本项目始终免费、开源。如果它帮助到了你，可以通过[支付宝、微信支付或 PayPal 自愿赞助后续维护](./SUPPORT.md)。赞助不影响软件功能、授权或问题处理。

## 许可证

本项目按 [GNU GPL v3](./LICENSE) 发布。BetterGI 的原始版权和许可证声明保持不变。

---

## English

BetterGI Automation Workflow is a Windows orchestration and evidence layer for Genshin Impact daily tasks. BetterGI remains responsible for computer vision, navigation, combat, and simulated input; this repository adds per-run configuration, locking, budgets, resource guards, graphics-profile leasing, log isolation, and completion verification.

The **2026-10-08 stable baseline** is retained, including changes after 0.2.2; see [baseline notes](docs/BASELINE_2026-10-08.md). Historical core execution supports Windows RDP Child Session and foreground recording, preflight HoYoLAB web check-in, and structured verification for mail, crafting, domain claims and daily commission rewards. Expedition collection and reassignment post-state still lack independent proof; see [verification boundaries](docs/DISPATCH_VERIFICATION_2026-10-11.md). No BetterGI or game binaries are distributed here.

The **2026-10-11 development transfer** includes current inventory evidence, hidden-guide fallback, single-20 resin claims, gray-loading recovery, and bounded same-run inventory reuse. Daily rewards and natural-resin cleanup passed locally; three normal batches took 37m48, above the 20-minute target. Continuous handguard combat, dispatch reset, and automatic upgrades remain unverified. Start with the [handoff](docs/DEVELOPMENT_HANDOFF_2026-10-11.md), [setup](docs/TRANSFER_SETUP.md), and [manifest](docs/TRANSFER_MANIFEST_2026-10-11.json). Configuration defaults to read-only with zero spending budgets.

Apply the [engine patch](patches/cultivation-engine.patch) to the retained source baseline and rebuild for this extension. It adds live resin observation, material crafting, party-deployment checks, HUD name verification, and disabled-by-default Zhongli hold-cast verification and single-round no-claim rehearsal. Only the avatar model uses CPU; read-only scans can skip final reward inspection while normal daily runs retain it. Private diagnostic screenshots and account records are excluded.

### Relationship to BetterGI

The project depends on [BetterGI](https://github.com/babalae/better-genshin-impact) and maintains an [unofficial modified fork](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow). It is not affiliated with, sponsored by, or endorsed by BetterGI, miHoYo, or HoYoverse. Upstream code and copyrights remain with the BetterGI authors and contributors. Report fork-specific problems here first.

BetterGI is licensed under GNU GPL v3. Modified source may be redistributed when notices are preserved, changes and dates are identified, and the derivative remains under GPL v3. Distributing a modified binary also requires corresponding source access. This workflow repository also uses GPL v3. See [NOTICE.md](./NOTICE.md) and [UPSTREAM_AND_LICENSE.md](./docs/UPSTREAM_AND_LICENSE.md).

### Quick start

1. Clone this repository and the pinned `automation-baseline-2026-10-08` tag of the modified BetterGI fork.
2. Apply the current complete engine patch to the clean baseline, then build with the .NET 8 SDK.
3. Run `scripts/initialize_config.ps1` and fill the local configuration. Artifact-only goals do not require the talent calendar or book inventory; add `-IncludeTalentPlanning` when configuring talent upgrades.
4. Keep `checkpointOnly=false`, with cultivation execution disabled and spending budgets zero for read-only acceptance.
5. Run the unit tests and a dry preview before any live task.
6. Enable the full `core` only after every checkpoint succeeds on the target machine.

Normal execution has no AI or API dependency. AI is an optional post-failure diagnostic layer that reads the minimized `agent-context.json`; it never performs automatic replay or upgrades an unknown outcome to success.

Third-party automation and simulated input may violate game terms or create account risk even when no game files or process memory are modified. Users are responsible for deciding whether and how to use the software.

### Support the project

This project will remain free and open source. If it helped you, you may [voluntarily support continued maintenance through Alipay, WeChat Pay, or PayPal](./SUPPORT.md). Sponsorship does not affect software functionality, licensing, or issue handling.
