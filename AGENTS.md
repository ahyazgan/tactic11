# Project workflow

## User-authorized PR workflow (2026-09-14)

For work requested in this project, commit and push changes, create or update
the PR, inspect its diff, and follow its checks without asking the user for
confirmation. Fix failing checks within the task scope. When all checks on
the latest PR head pass, merge that exact head with a normal merge commit,
verify the merge, and bring the current working branch up to date without
discarding local changes. Do not stop at an open PR with checks still running.
Do not rewrite shared history, force-push, delete working branches, or bypass
failed/pending checks as part of this workflow. This is an in-task workflow,
not authorization for unattended changes to unrelated PRs.

## Current work ownership (2026-10-09)

The user now continues development only through Codex in
`football-intelligence` on `codex-work`. Claude's merged scorecard/decision
work is part of the baseline. Preserve the adjacent `fi-karne-sekil` worktree
on `opus-work`; do not start or message another agent for it. Restrict
backlog execution to the work the user is currently continuing; unrelated
PDF/email/i18n backlog items do not expand the camera task.

Use the repository Python environments: `venv` for app tests/lint/type checks,
`venv-cv` for OpenCV/video work. Use isolated SQLite for tests. Preserve source
videos, measurement caches and the live match database. Select changes using
development data, then freeze the decision before checking control data.

Local ports 3000/3001/8000 are currently used by other projects. Use the
isolated `launcher/CODEX.bat` entry point (frontend 3100, backend 8100).
Verify process ownership before restarting a service; do not stop unrelated
apps to reclaim a port or memory.

Before continuing palette-control labeling/replay, run the read-only
`scripts.soccertrack_v2.validate_palette_acquisition` gate for the relevant
group. Missing manifests, zero/truncated samples or changed source hashes
are acquisition failures, not successful control results. The original
frozen candidate and control scripts remain immutable during this control.
