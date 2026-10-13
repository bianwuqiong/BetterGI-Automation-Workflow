# Changelog

## 开发迁移快照 / Development transfer - 2026-10-11

- 同步最新培养编排、完整引擎增量源码与回归测试；提供固定基线、校验清单和新电脑交接步骤。
- 新增完整名称、选中白框、原始数量和双帧验证的背包读取；指南隐藏达标材料时使用明确的库存回退。
- 单20原粹领奖保留提交边界，修复深灰加载检测；同run真实读数仅在120秒以内且谱系可独立核实时复用before，每笔after重新读取。
- 默认只读与零预算；不公开本机账号、路径、授权账本、库存、截图或录像。保留上游GPL声明和原有公开赞助渠道。
- 已完成的培养日常正常批次合计37分48秒，性能目标仍未达到。刀镡连续战斗、派遣重置与自动升级仍待验收。

- Publish the latest source, complete engine delta and offline regressions with a pinned baseline and portable handoff. Keep execution disabled by default and exclude private account, inventory, authorization and capture data. Current cultivation speed and unverified extensions are stated separately from older daily milestones.

## Material route recovery and sessions - 2026-10-09

- Add fixed-hub recovery with loading, grounded world UI, actual minimap coordinates and full slot-ordered party evidence; reuse a verified current party and switch only when necessary at startup.
- Apply bounded airborne/cooldown and target-identity checks to every material-combat switch while preserving same-character held-input commands and observed Zhongli shield timing.
- Add a two-route session profile with one login, recorder and graphics lease; reserve both native budgets together and archive independent segment results. Stop continuation on route, inventory or recovery uncertainty; retain verified partial gains.
- Require issued confirmation, stable loading/world frames and actual arrival before material-route movement; keep rejected-position diagnostics and the original arrival tolerance. Add a separate four-minute recovery-only recording profile with no inventory, combat or farming lease.
- Keep route data, local configurations, account observations and recordings out of the public source package. Offline checks and a successful single route do not establish consecutive live acceptance.

## Character cultivation extension - 2026-10-08

- Add read-only in-game character, equipped-weapon and material snapshots; unknown recognition is preserved instead of becoming zero inventory.
- Add a cultivation profile, bounded domain/world-boss adapters, before/after inventory evidence and explicit execution gates. Routes, weekly bosses, ley lines and exact level-up experience remain manual.
- Preserve the existing daily engine, shared lock, child-session and graphics isolation; pin and attribute the reused community calculation modules and data.
- Add offline plugin and runner integration tests; existing daily validation does not constitute live validation of the extension.

## 2026-10-08 baseline

- 固定本机后续迭代的工作流与 BetterGI 源码版本，保持现有日常行为；保留独立的私人运行文件备份和哈希清单。
- 增加不启动游戏的备份核验与可恢复回滚工具，并补充对应离线测试。
- Freeze the deployed workflow and source revisions without changing daily behavior; keep the private runtime snapshot separate from the public repository.
- Add offline snapshot verification and recoverable restore tools with focused tests.

## 0.2.2 - 2026-09-18

- Honor `killBettergiAfterDone` setting during workflow cleanup: ensure root BetterGI processes and associated foreground/child session processes are cleanly terminated when the daily run completes, preventing lingering background memory consumption.
- Add unit tests verifying `killBettergiAfterDone` behavior across both `childSession` and `foreground` execution modes.

## 0.2.1 - 2026-09-18

- Fix mail claim interaction: automatically press ESC after "Collect All" to dismiss the reward popup modal, remove spurious claim button disappearance exceptions, and standardize machine event property casing.
- Fix headless child session activation: directly invoke `HomePageViewModel.HandleActivation` in `ApplicationHostService` during `StartChildSessionOneDragon` to eliminate dependency on WPF visual tree `Loaded` events under `CREATE_NO_WINDOW` Task Scheduler launches.
- Update agent authorization policy: user execution authorization remains valid throughout the same Genshin game day (UTC+8 04:00 to next day 04:00) across transient/environmental aborts without repeated confirmation requests.
- Live milestone validation: verified 100% end-to-end success for 4+1 core workflow (HoYoLAB check-in + Mail claiming + Resin crafting + 4-round Artifact domain + Daily commissions & dispatch) in 13m 45s under Windows RDP Child Session with zero fragile resin consumption.

## 0.2.0 - 2026-09-17

- Support Windows RDP Child Session execution mode for non-intrusive background daily automation.
- Integrate official HoYoLAB web check-in preflight hook with fail-open error handling and sanitized credential management.
- Support foreground HWND-level HD video recording via FFmpeg (`h264_nvenc`) with frame coverage verification.
- Include mail reward claiming into core profile with multi-phase robust interaction (opening verification, click retry, async loading wait, and machine event reporting).
- Expand unit test suite to 94 tests covering child sessions, video recording, HoYoLAB check-in, and task resumption.

## 0.1.2 - 2026-09-14

- Allow artifact-only and already-completed talent goals to run without talent calendar or book-inventory files.
- Keep missing talent data fail-closed whenever an unfinished talent target is configured.

## 0.1.1 - 2026-09-14

- Add the maintainer's previously published optional Alipay, WeChat Pay, and PayPal sponsorship channels with hash-pinned QR assets.

## 0.1.0 - 2026-09-14

- Publish the privacy-minimized local workflow, tests, and configuration examples.
- Reference the GPL v3 BetterGI modification fork instead of distributing binaries.
- Include foreground focus recovery, bounded task stages, evidence verification, VPN/resource guards, graphics-profile leasing, and optional Luna diagnostics.
- Mark full continuous `core` and child-session execution as not yet generally validated.
