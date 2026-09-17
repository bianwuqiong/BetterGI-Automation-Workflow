# Changelog

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
