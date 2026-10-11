# 迁移包离线验证 / Offline transfer checks

本次检查在独立公开工作副本与干净源码基线进行，没有启动游戏或消费资源。

- 公开工作流 Python：393项全部通过。
- 培养插件 JS：143项全部通过；材料路线及队伍准备 JS：30项全部通过；战斗演练 JS：6项全部通过。
- 当前完整引擎补丁在固定源码基线上通过应用预检、实际应用及 Release 编译；首次构建597个警告、0个错误。构建警告需要后续按来源核查，本次没有将其描述为无警告。
- 根据源码清单选择的 C# 开发回归：333项全部通过，私人图像相关方法明确排除。脚本为 `scripts/test_cultivation_engine.ps1`。
- 广泛 C# 测试：619项中512通过、107失败，存在未提供图像等资源的依赖；不是完整通过。不把环境变量为空时直接返回的图像方法算为实机图像验收。具体排除边界见 [迁移步骤](TRANSFER_SETUP.md)。
- 公开文件隐私审计及 Git 差异检查通过。原有公开赞助图片按既有许可保留并校验哈希。

此前开发机的游戏实测仅用于说明已观察到的行为；新电脑需要重新只读验收、配置本地路径和凭据。构建和离线测试成功不代表角色识别、网络或连续刷取已在新机通过。

English: Python 393/393; cultivation JS 143/143; material-route/preparation JS 30/30; rehearsal JS 6/6; selected portable C# development regressions 333/333. The complete patch applies to the pinned clean baseline and builds in Release (597 warnings, no errors). Broader C# tests were not all successful: 512/619 passed, with missing image/resource dependencies among the 107 failures. Private-image methods are explicitly excluded from portable acceptance. No game execution or resource spending occurred during this publication task.
