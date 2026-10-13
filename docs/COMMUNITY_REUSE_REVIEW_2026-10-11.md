# BetterGI 与社区实现复用核对（2026-10-11）

本轮先复用 BetterGI 原生状态机、OCR、模型与脚本接口，再补充本工作流的证据契约。公开资料只用于技术参考，不作为操作授权；未发布社区问题、评论或账号数据，也未运行未审查脚本。

## 已采用的原生接口

固定基线加完整培养补丁实际包含 `characterDevelopmentTask.GetCharacter`、三类天赋显示等级与加成字段，以及详情页门控、`StableValueAccumulator` 和有限重试。本机天赋修复继续在同一个原生模块内使用这些组件，实机与私人素材回放共用帧解析入口；三次连续完整值一致和未知状态不重放继续保留。

可参考 [上游角色养成模块](https://github.com/babalae/better-genshin-impact/blob/8a4db294362c682ca709ebeef205f77fca4d575e/BetterGenshinImpact/GameTask/CharacterDevelopment/CharacterDevelopmentTask.cs)。研究时另外核对官方 `main` 为 `8a4db294362c682ca709ebeef205f77fca4d575e`；它与项目固定基线不同，不能把移动分支的实现或公开 DTO 当成本机验收证明。没有找到可直接替代本机加成正负夹具的严格 `+3` 读取方案。

本地现有背包计数已经复用 `CountInventoryItemParam.ItemNames` 与 `dispatcher.RunCountInventoryItemTask`，按指定 `GridScreenName` 批量请求并返回物品名到数量的对象。额外具名背包读取和指南回退承担本项目更严格的新帧、完整身份与选中堆叠数量核验；优化跳过重复通用扫描时仍保留这些证明。

## 上游库存优化的兼容性发现

上游 [PR #3657](https://github.com/babalae/better-genshin-impact/pull/3657) 是回滚按物品元数据自动选背包页及提前结束扫描的改动，不能把该 PR 本身列成新增功能。随后 [PR #3705](https://github.com/babalae/better-genshin-impact/pull/3705) 于 2026-09-23 重新引入；作者明确指出删除单项 `itemName` 参数、背包页改为可选、统一多项返回，并使用物品顺序决定扫描结束。

固定版本中仍有 `ItemName` 和明确背包页参数，故本轮没有直接引入这些新参数或替换整体基线。后续采用跨页或提前结束扫描，需要在独立补丁中核对元数据／模型依赖、返回形状、缺项语义与顺序证明，并保持未知不当作零、每笔 `after` 用新帧读取完整链。上游版本号较大不能代替这项核对。

## 社区资料与已有固定复用

- [官方网格图标文档](https://github.com/huiyadanli/bettergi-docs/blob/main/src/dev/getGridIcons.md) 说明背景和相邻图标连通会影响传统图像分格，支持保持受控画面并独立核验条目身份，不能单靠图标位置接受数量。
- [原作者脚本仓库](https://github.com/babalae/bettergi-scripts-list) 和 [AutoPlan](https://github.com/babalae/bettergi-scripts-list/blob/main/repo/js/AutoPlan/README.md) 提供调度与原生 API 使用参考；本轮未发现其中可直接替代角色天赋读取的接口。背包连续截图计数的 [issue #524](https://github.com/babalae/bettergi-scripts-list/issues/524) 是功能请求，不能当成已实现模块。
- 本项目已经固定复用 GenshinCultivationPlanner 的纯计算与规则数据，来源、提交、GPL 与 MIT 声明见插件 `UPSTREAM.md`、`LICENSE`、`THIRD_PARTY_NOTICES.md`；没有导入其账号配置或任务执行器。
- 当日刀镡路线候选来自固定公开社区提交，元数据与文件哈希已核对；选路仍要求真实掉落依据、当日可用性与缺口有效产出，路线编号和战斗次数不作为掉落数量。详见 [选路核对](ROUTE_SELECTION_REVIEW_2026-10-11.md)。
- 已找到作者 Siki 的精确 [木偶星超导策略 PR #3639](https://github.com/babalae/bettergi-scripts-list/pull/3639)，合并提交 `4dcec436b856552df19397a38b28aa3161e2e540`、文件 blob `ce9295506d31f830b81967ddcdd51a4a31c9602f`。已下载到忽略的本机候选目录并复核 blob，仅供离线检查。原策略包含木偶、奥黛塔、八重等命令，没有钟离；现有原生 `ZhongliHoldShieldGuard` 可提供独立长 E 和补盾核验，但队伍／策略匹配、首次施放及战斗内刷新均需分别验收。原策略许可证未确认，因此本仓库不分发其源码；作者战斗时间不能作为本机完整日常基准。

以上复用与研究不证明新电脑的完整实机流程通过。真实截图、库存、账号和运行账本保存在本机忽略目录；公开记录仅含接口、固定来源、技术发现和验证范围。
