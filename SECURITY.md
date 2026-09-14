# Security and privacy

Do not attach unredacted BetterGI logs, `GENERAL_DATA` registry exports, screenshots, account configuration, process dumps, or files from `logs/` and `state/` to public issues.

The tracked repository contains examples only. Local files such as `config/settings.json`, goals, inventory, run records, screenshots, and BetterGI installations are ignored by Git.

The two images under `docs/assets/support/` and the payment links in `SUPPORT.md`/`.github/FUNDING.yml` are intentional public sponsorship material. Their paths and hashes are explicitly checked by the audit script; no other media or payment material is allowed by default.

Before reporting a problem:

1. Reproduce with the smallest possible task.
2. Use `agent-context.json` rather than the full log when possible.
3. Remove usernames, absolute user-profile paths, account IDs, UIDs, device IDs, tokens, network credentials, and payment information.
4. If a report cannot be safely redacted, do not open a public issue.

Run `python scripts/audit_public_tree.py --tracked` before every public push.
