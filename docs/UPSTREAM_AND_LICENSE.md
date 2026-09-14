# 与 BetterGI 的关系及许可证说明

## 关系声明

本项目以 BetterGI 作为实际的视觉识别和游戏操作引擎，在其外部增加运行编排、互斥、资源保护、结果核验和可选的低成本 AI 诊断。同时，我们为了改善登录焦点、合成证据、秘境古树/领奖识别和实验性子会话支持，维护了一个 BetterGI 修改分支。

- 官方上游：<https://github.com/babalae/better-genshin-impact>
- 非官方修改分支：<https://github.com/bianwuqiong/better-genshin-impact/tree/automation-workflow>
- 具体变更：<https://github.com/bianwuqiong/better-genshin-impact/blob/automation-workflow/MODIFICATIONS.md>

本项目及修改分支均为独立社区项目。BetterGI 上游维护者不负责这里新增的行为和故障；修改分支的问题应先在本项目反馈。

## GPL v3 如何适用

BetterGI 官方仓库包含 GNU GPL version 3 许可证。该许可证允许运行、研究、修改和再发布。发布修改源码时，应保留原有版权与许可证声明，显著注明已经修改并给出相关日期，并继续按 GPL v3 提供该衍生作品。发布修改后的二进制时，还必须向接收者提供机器可读的对应源码及构建所需脚本，或按许可证规定提供等价的源码获取方式。

GPL v3 也说明，独立作品与 GPL 程序仅作为聚合发布时，不会当然让独立部分自动受到 GPL 约束。这里为了让使用和再分发条件清楚一致，工作流仓库本身也主动采用 GPL v3。

当前仓库不分发 BetterGI 二进制；它将用户引导至带完整源码和历史的 GitHub fork。以后若发布定制 BetterGI 二进制，下载页必须同时清楚链接到生成该二进制的精确源码提交，并保留 LICENSE 与修改声明。

## 推荐的公开表述

> 本项目是基于 BetterGI 的非官方自动化工作流，并维护一个遵循 GNU GPL v3 的 BetterGI 修改分支。BetterGI 的名称、原始代码和版权归其原作者及贡献者；本项目与 BetterGI 官方、米哈游及 HoYoverse 无隶属、赞助或认可关系。修改版问题请优先在本项目反馈。

## 其他使用边界

开源许可证解决的是复制、修改和分发代码的版权许可，并不替代游戏服务条款。BetterGI 官方 README 也提示第三方工具和模拟输入可能存在账号风险。使用者应自行判断并遵守适用规则。

## Primary sources

- BetterGI LICENSE: <https://github.com/babalae/better-genshin-impact/blob/main/LICENSE>
- BetterGI README and FAQ: <https://github.com/babalae/better-genshin-impact/blob/main/README.md>
- GNU GPL v3 text: <https://www.gnu.org/licenses/gpl-3.0.html>
