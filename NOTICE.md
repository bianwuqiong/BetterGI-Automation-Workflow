# Notices and attribution / 声明与署名

Copyright (C) 2026 `bianwuqiong` for the original workflow and orchestration code in this repository.

本仓库是一个独立的社区工作流项目，依赖并修改了 BetterGI，但不是 BetterGI 官方项目，也未获得 BetterGI、米哈游或 HoYoverse 的隶属、赞助或认可。

This repository is an independent community workflow that depends on and modifies BetterGI. It is not an official BetterGI project and is not affiliated with, sponsored by, or endorsed by BetterGI, miHoYo, or HoYoverse.

- BetterGI upstream: <https://github.com/babalae/better-genshin-impact>
- BetterGI license: GNU General Public License version 3
- Unofficial modified source branch: <https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow>
- Reviewed source tag: [`automation-baseline-2026-10-08`](https://github.com/bianwuqiong/better-genshin-impact/tree/automation-baseline-2026-10-08)
- Modified source commit: `d8c0aa238a949d7d74bfe5087f3a48e39771575a`
- Upstream base commit: `9424d1f3c344f8ba99363e0b0d3756f76bce836d`
- Modification dates: 2026-09-12 through 2026-10-12
- Current corresponding source: the pinned baseline above plus every patch, applied once in the exact order and with the UTF-8/LF hashes recorded in [SOURCE_PATCH_SEQUENCE](docs/SOURCE_PATCH_SEQUENCE_2026-10-11.json). This includes the complete cultivation patch and subsequent startup, character, artifact, resource-reading and network-diagnostic changes. The baseline or cultivation patch alone does not provide the current modified engine. See [setup](docs/TRANSFER_SETUP.md) and [local validation boundaries](docs/LOCAL_WORKFLOW_VALIDATION_2026-10-12.md).
- Original development-transfer snapshot: `docs/TRANSFER_MANIFEST_2026-10-11.json` remains the downloaded package's manifest. Later source changes have their own patches and validation records; account state and spending authorization are not transferred.

This repository does not contain BetterGI binaries, Genshin Impact files, game assets, account data, or login credentials. BetterGI and Genshin Impact names are used only to identify compatibility and upstream origin. All related trademarks belong to their respective owners.

The repository is distributed under GNU GPL v3. See [LICENSE](./LICENSE) and [the upstream and license notes](./docs/UPSTREAM_AND_LICENSE.md).

## 培养计算模块 / Cultivation calculation modules

`bgi-scripts/AutoGameCultivation/upstream/` 包含社区项目 [GenshinCultivationPlanner](https://github.com/yunxi001/GenshinCultivationPlanner) 的纯计算代码及静态数据，固定提交 `3f1e938a6dcd5a34642dad03a91488db8d2da40c`。原作者署名、GPL v3 许可证与基于 `genshin-db` 的 MIT 数据声明保留在插件根目录的 `UPSTREAM.md`、`LICENSE` 和 `THIRD_PARTY_NOTICES.md`。该社区模块不是 BetterGI 官方的已验证功能。

The cultivation plugin retains GPL v3 calculation modules and static data from GenshinCultivationPlanner at the pinned commit above. Original attribution, license and MIT data notices are preserved in `UPSTREAM.md`, `LICENSE` and `THIRD_PARTY_NOTICES.md` at the plugin root. This is an independent community component, not an officially validated BetterGI feature.
