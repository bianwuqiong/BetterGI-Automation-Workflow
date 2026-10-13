# BetterGI automation workflow

- Windows native desktop control must use the installed computer-use skill and its trusted native service (`mcp__node_repl__js` with `@oai/sky`). Browser-only tools are not a native desktop substitute; search deferred tools before claiming native control is unavailable.
- File removal must be recoverable: use the Recycle Bin or a clearly identified quarantine directory. Do not permanently delete files or empty the recovery location.

- Read `README.md` and `docs/UPSTREAM_AND_LICENSE.md` before changing release or attribution behavior.
- BetterGI is the execution engine. Use the GPL v3 modified source branch pinned in `NOTICE.md`; do not add BetterGI binaries, game files, model assets, or user data to this repository.
- Keep `checkpointOnly=false`. A dry run is not a completed game task. On a new machine keep cultivation `executionEnabled=false`, budgets zero and resource adapters disabled until read-only acceptance and explicit local authorization.
- Latest development context: read `docs/DEVELOPMENT_HANDOFF_2026-10-11.md` and `docs/TRANSFER_SETUP.md`. The fixed BetterGI baseline requires the complete current `patches/cultivation-engine.patch`; do not stack it on an older patch.
- Run through `scripts/run_task.ps1`, `scripts/run_daily.ps1`, or `scripts/workflow.py`. Do not bypass the shared lock or rewrite a user's production OneDragon file to select tasks.
- Daily authorization window: Within the same Genshin game day (defined by UTC+8 04:00 to next day 04:00), once explicit user instruction to run daily workflow has been received, that authorization remains valid throughout the game day. If a run aborts or encounters failure due to transient or environmental reasons (e.g. resource pressure guard, UI glitch, network lag), the supervisor may execute root-cause fixes/recovery and re-run/resume the workflow within the same game day without asking for repeated user confirmation.
- Safety invariants remain strictly enforced: Never spend fragile resin. Never upgrade an unknown outcome to success without verified evidence. Never change production configuration during an active run.
- Treat `logs/`, `state/`, local configuration, screenshots, registry exports, and process dumps as private. Run `python scripts/audit_public_tree.py --tracked` before publishing.
- On failure, read the run's `agent-context.json` before larger logs. Model advice is advisory and cannot convert an unknown result into success or trigger an automatic replay.
- Tests use fake processes and retained fixtures. Run `python -B -m unittest discover -s tests -v`; do not launch the game as a test.
