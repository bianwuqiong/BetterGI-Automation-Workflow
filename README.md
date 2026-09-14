# BetterGI Automation Workflow

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](./LICENSE)
[![Tests](https://github.com/bianwuqiong/BetterGI-Automation-Workflow/actions/workflows/tests.yml/badge.svg)](https://github.com/bianwuqiong/BetterGI-Automation-Workflow/actions/workflows/tests.yml)

中文 | [English](#english)

一个面向 Windows 的原神日常自动化编排与核验项目。BetterGI 继续负责画面识别、路径、战斗和模拟输入；本项目负责一次运行的任务选择、互斥、时间预算、资源/VPN 保护、画质切换、日志隔离以及完成证据。

当前是 **0.1.0 源码预览版**。合成浓缩树脂、自动秘境和领取每日奖励已分别在前台模式完成实机验证；完整连续 `core` 和桌面子会话仍在验证中。仓库不提供 BetterGI 或原神二进制文件。

## 与 BetterGI 的关系

本项目建立在 [BetterGI](https://github.com/babalae/better-genshin-impact) 之上，并维护一个用于工作流的[非官方 BetterGI 修改分支](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow)。修改分支改善了启动焦点、合成证据、秘境阶段边界、古树/领奖识别、运行标识和实验性子会话支持。

本项目不是 BetterGI 官方版本，也未获得 BetterGI、米哈游或 HoYoverse 的隶属、赞助或认可。上游代码和版权归 BetterGI 原作者及贡献者；修改版问题请先在本仓库反馈。完整声明见 [NOTICE.md](./NOTICE.md) 和 [许可证说明](./docs/UPSTREAM_AND_LICENSE.md)。

BetterGI 使用 GNU GPL v3，允许修改和再发布，但需要保留声明、显著标记修改并继续按 GPL v3 提供修改版；分发二进制时还要提供对应源码。本仓库也采用 GPL v3，并通过独立 fork 提供完整修改源码。

## 主要能力

- `core`：合成浓缩树脂、自动秘境清理可用树脂、领取每日奖励。
- `extras`：邮件、地脉花和尘歌壶等奖励节点，与核心耗时分开衡量。
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
- `.env`、密钥、令牌、支付信息和二进制文件。

每次公开提交前运行：

```powershell
python scripts/audit_public_tree.py --tracked
```

## 环境要求

- Windows 10/11 x64；
- Python 3.10 或更高版本；
- .NET 8 SDK（自行构建修改版 BetterGI 时）；
- 原神简体中文界面；
- 16:9 分辨率。BetterGI 上游推荐 `1920x1080` 窗口化、默认亮度，并要求关闭 HDR/滤镜。

## 安装

1. 克隆本仓库：

   ```powershell
   git clone https://github.com/bianwuqiong/BetterGI-Automation-Workflow.git
   cd BetterGI-Automation-Workflow
   ```

2. 获取带完整 GPL 源码的 BetterGI 修改分支：

   ```powershell
   git clone --recurse-submodules --branch automation-workflow --single-branch `
     https://github.com/bianwuqiong/better-genshin-impact.git better-genshin-impact
   dotnet build better-genshin-impact\BetterGenshinImpact.sln -c Release
   ```

   0.1.0 对应源码标签为 `automation-workflow-v0.1.0`，固定提交 `67884d7af80223405543f2882259d28ea8e4d227`；正式使用前应核对该提交并阅读其中的 `MODIFICATIONS.md`。

3. 初始化不会进入 Git 的本地配置：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/initialize_config.ps1
   ```

4. 编辑 `config/settings.json`，填写 `bettergiExe`、`bettergiLogDir` 和 `gameExe`。可选 VPN 保护与前台进程清理默认关闭，避免在其他电脑上结束未知程序。

5. 首次打开 BetterGI，让它生成 `User/config.json`。确认自动秘境与地脉配置不允许使用脆弱树脂，再把 `config/one-dragon.example.json` 复制为 BetterGI 的 `User/OneDragon/DailyOneDragon.json`，或在界面中建立同名配置。

6. 填写并核实 `goals.json`、`domain-calendar.json` 和 `book-progress.json`。空示例会故意阻止自动秘境计划，防止使用未经核实的目标。

## 验证与运行

运行离线测试：

```powershell
python -B -m unittest discover -s tests -v
```

先预览，不启动游戏：

```powershell
powershell -NoProfile -File scripts/run_task.ps1 -Task '合成树脂' -DryRun
```

保持 `checkpointOnly=true`，逐项实机验证：

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

## 许可证

本项目按 [GNU GPL v3](./LICENSE) 发布。BetterGI 的原始版权和许可证声明保持不变。

---

## English

BetterGI Automation Workflow is a Windows orchestration and evidence layer for Genshin Impact daily tasks. BetterGI remains responsible for computer vision, navigation, combat, and simulated input; this repository adds per-run configuration, locking, budgets, resource guards, graphics-profile leasing, log isolation, and completion verification.

This is a **0.1.0 source preview**. Crafting, automatic-domain, and daily-reward checkpoints have been validated individually in foreground mode. A continuous full `core` run and child-session mode are still under validation. No BetterGI or game binaries are distributed here.

### Relationship to BetterGI

The project depends on [BetterGI](https://github.com/babalae/better-genshin-impact) and maintains an [unofficial modified fork](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow). It is not affiliated with, sponsored by, or endorsed by BetterGI, miHoYo, or HoYoverse. Upstream code and copyrights remain with the BetterGI authors and contributors. Report fork-specific problems here first.

BetterGI is licensed under GNU GPL v3. Modified source may be redistributed when notices are preserved, changes and dates are identified, and the derivative remains under GPL v3. Distributing a modified binary also requires corresponding source access. This workflow repository also uses GPL v3. See [NOTICE.md](./NOTICE.md) and [UPSTREAM_AND_LICENSE.md](./docs/UPSTREAM_AND_LICENSE.md).

### Quick start

1. Clone this repository and the pinned `automation-workflow` branch of the modified BetterGI fork.
2. Build BetterGI with the .NET 8 SDK.
3. Run `scripts/initialize_config.ps1` and fill the local configuration.
4. Keep `checkpointOnly=true` while validating each live task.
5. Run the unit tests and a dry preview before any live task.
6. Enable the full `core` only after every checkpoint succeeds on the target machine.

Normal execution has no AI or API dependency. AI is an optional post-failure diagnostic layer that reads the minimized `agent-context.json`; it never performs automatic replay or upgrades an unknown outcome to success.

Third-party automation and simulated input may violate game terms or create account risk even when no game files or process memory are modified. Users are responsible for deciding whether and how to use the software.
