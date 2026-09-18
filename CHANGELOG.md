# Changelog

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
