# 固定上游和修改范围

来源：[yunxi001/GenshinCultivationPlanner](https://github.com/yunxi001/GenshinCultivationPlanner)

固定提交：`3f1e938a6dcd5a34642dad03a91488db8d2da40c`。本插件没有导入上游 `main.js`、`inventory.js`、账号配置、作者记录、通知或任务执行器。

`upstream/core/` 中的 `calculator.js`、`requirements.js`、`crafting.js`、`level-state.js` 以及 `upstream/data/` 中的 `rulebook.json`、`materials.json`、`crafting-recipes.json`、`bettergi-boss-catalog.json` 均从该提交原样复制。代码继续采用 GPL-3.0-only；完整许可证在本目录 LICENSE。静态规则生成使用 genshin-db，MIT 声明保留在 THIRD_PARTY_NOTICES.md。boss支持白名单源自BetterGI AutoBossData；此声明仅表示静态名称支持，不代表全部boss已实机验收。

2026-10-08 新增的 main.js、core/safe.js、core/operator.js 和 tests 为本工作流的安全包装，采用 GPL-3.0-only。区别：缺库存字段不当作0；材料和合成建议分开；无通知和账号API；输出绑定runId的报告；任务执行需独立预算及本机验收。

该插件不是 BetterGI 官方已合并脚本，也没有宣称完成所有角色、材料或任务的实机验收。原作者与上游维护者不负责此安全包装的改动。
