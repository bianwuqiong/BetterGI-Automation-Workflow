# 开发交接（2026-10-11）

本文记录瑞希培养扩展的公开开发目标、当前验证边界和在另一台电脑继续开发的起点。只保留可复现的功能说明，不包含本机运行标识、库存明细、授权凭据或设备路径。

## 当前目标与进度

培养目标是瑞希等级 90、天赋 9/9/9、装备武器等级 90。工作流负责读取证据、限定每笔操作和核验结果；未知库存继续标记为未知，不以估算值代替实读。

最近一轮日常中的每日奖励领取和自然树脂清理已完成。三个正常批次合计用时 37 分 48 秒，仍未达到约 20 分钟的性能目标；不能用清理剩余树脂的局部耗时替代完整流程成绩。

当前开发改动包含以下修复，发布包应同时提供对应的 BetterGI 源码补丁、工作流代码和离线回归测试：

- 背包材料读取要求完整标题、选中物品的数量区域和两帧一致证据；证据不足时保持 `unknown`。
- 指南材料读取遇到目标项隐藏或列表饱和时，使用受限的回退读取流程，不能把未见项目当作零库存。
- 单笔 20 原粹树脂流程能够识别秘境灰色加载状态，并在有界等待内确认真实世界状态；前一笔的真实 `after` 只可在同一运行中作为下一笔 `before`，每一笔消费后仍须重新读取并核验新的 `after`。

以下事项仍未验收：刀镡路线的连续战斗、每日派遣重置，以及自动升级角色或武器。日常领奖和树脂清理完成不代表这些扩展功能已通过实机验证。未知或部分结果不得自动升级为成功，也不得据此重放已提交的消费步骤。

## 在另一台电脑继续开发

先阅读 [项目 README](../README.md)、[AGENTS.md](../AGENTS.md)、[培养工作流说明](CULTIVATION_WORKFLOW.md)、[上游与许可证说明](UPSTREAM_AND_LICENSE.md) 和 [BetterGI 执行引擎补丁](../patches/cultivation-engine.patch)。使用迁移清单中指定的公开源码版本与补丁；不要把开发机当前运行目录当作源码基线。BetterGI 是 GPL v3 项目，修改后的引擎必须随相应源码、修改说明和可复现构建信息提供，不能只迁移二进制文件。

在新电脑上从示例配置建立本地配置，并为该机重新填写可执行文件和日志位置。HoYoLAB 凭据如有需要，应由使用者在本机单独配置和保护；不要复制旧机的凭据、授权账本、收据、运行状态、日志、截图或备份。旧机的日常授权不随代码或配置迁移；任何真实日常操作都须在新机当前 UTC+8 游戏日取得明确授权。

网络与游戏配置也按新机独立确认：保持使用者所需的 TUN 设置；旧机的服务器直连 IP、DNS、代理或路由规则不能直接复制。按新机环境配置兼容模式及 1920×1080 窗口画质，并使用项目的画质保存、校验和恢复流程。

建议按以下顺序推进：

1. 完成源码、补丁和依赖版本核对，读取新机配置示例并填入本地路径。
2. 只运行离线验证，不启动游戏：

   ```powershell
   python -B -m unittest discover -s tests -v
   node --test bgi-scripts/AutoGameCultivation/tests/*.test.js
   ```

   BetterGI 引擎代码还应按迁移清单指定的 .NET SDK 执行构建和单元测试。测试数量以实际命令结果为准，本说明不预先声明通过数量。

3. 保持示例中的 `checkpointOnly=false`；它用于记录真实执行结果，不能以预览冒充完成。培养消费由 `executionEnabled=false`、零预算和未授权账本独立阻断。先做 dry run，再进行只读实机检查，确认画质、识别、证据格式和安全退出均符合新机情况。
4. 仅在用户于新机当前游戏日明确授权后，才进入对应的真实日常流程。遵守每笔消费的独立授权和核验边界；永不使用脆弱树脂、须臾树脂或原石补充。

## English summary

The current goal is level 90 Mizuki, 9/9/9 talents, and a level 90 equipped weapon. Daily rewards and natural-resin cleanup completed on the development machine, but three normal batches took 37 minutes 48 seconds, above the roughly 20-minute target. Backpack evidence now requires a full title, selected-item count, and matching frames; guide saturation has a bounded fallback; and single-20 resin handling recognizes gray loading with same-run verified snapshot reuse and a fresh post-spend read. Continuous handguard combat, dispatch reset, and automatic upgrades remain unverified.

On a new computer, follow the README, `AGENTS.md`, source patch, and migration manifest. Create local paths and credentials there; do not migrate private receipts, authorization ledgers, logs, or machine-specific network rules. Keep the required TUN configuration, establish the 1080p compatibility profile, run offline checks, then read-only live checks. A real daily run requires explicit authorization for that computer's current UTC+8 game day.
