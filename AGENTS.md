# BetterGI automation workflow

- Read `README.md` and `docs/UPSTREAM_AND_LICENSE.md` before changing release or attribution behavior.
- BetterGI is the execution engine. Use the GPL v3 modified source branch pinned in `NOTICE.md`; do not add BetterGI binaries, game files, model assets, or user data to this repository.
- Keep `checkpointOnly=true` until every enabled task passes real verification on the target machine. A dry run is not a completed game task.
- Run through `scripts/run_task.ps1`, `scripts/run_daily.ps1`, or `scripts/workflow.py`. Do not bypass the shared lock or rewrite a user's production OneDragon file to select tasks.
- Never spend fragile resin. A retry that may spend resources requires explicit user direction and new evidence.
- Treat `logs/`, `state/`, local configuration, screenshots, registry exports, and process dumps as private. Run `python scripts/audit_public_tree.py --tracked` before publishing.
- On failure, read the run's `agent-context.json` before larger logs. Model advice is advisory and cannot convert an unknown result into success or trigger an automatic replay.
- Tests use fake processes and retained fixtures. Run `python -B -m unittest discover -s tests -v`; do not launch the game as a test.
