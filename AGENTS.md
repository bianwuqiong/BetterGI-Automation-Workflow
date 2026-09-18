# BetterGI automation workflow

- Read `README.md` and `docs/UPSTREAM_AND_LICENSE.md` before changing release or attribution behavior.
- BetterGI is the execution engine. Use the GPL v3 modified source branch pinned in `NOTICE.md`; do not add BetterGI binaries, game files, model assets, or user data to this repository.
- Keep `checkpointOnly=true` until every enabled task passes real verification on the target machine. A dry run is not a completed game task.
- Run through `scripts/run_task.ps1`, `scripts/run_daily.ps1`, or `scripts/workflow.py`. Do not bypass the shared lock or rewrite a user's production OneDragon file to select tasks.
- Daily authorization window: Within the same Genshin game day (defined by UTC+8 04:00 to next day 04:00), once explicit user instruction to run daily workflow has been received, that authorization remains valid throughout the game day. If a run aborts or encounters failure due to transient or environmental reasons (e.g. resource pressure guard, UI glitch, network lag), the supervisor may execute root-cause fixes/recovery and re-run/resume the workflow within the same game day without asking for repeated user confirmation.
- Safety invariants remain strictly enforced: Never spend fragile resin. Never upgrade an unknown outcome to success without verified evidence. Never change production configuration during an active run.
- Treat `logs/`, `state/`, local configuration, screenshots, registry exports, and process dumps as private. Run `python scripts/audit_public_tree.py --tracked` before publishing.
- On failure, read the run's `agent-context.json` before larger logs. Model advice is advisory and cannot convert an unknown result into success or trigger an automatic replay.
- Tests use fake processes and retained fixtures. Run `python -B -m unittest discover -s tests -v`; do not launch the game as a test.
