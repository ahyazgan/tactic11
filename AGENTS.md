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

## Current work split

Codex works on camera/tracking correctness in `football-intelligence` on
`codex-work`. Claude works on scorecard/decision intelligence in the adjacent
`fi-karne-sekil` worktree on `opus-work`. Preserve the other worktree. Restrict
backlog execution to the work the user is currently continuing; unrelated
PDF/email/i18n backlog items do not expand the camera task.

Use the repository Python environments: `venv` for app tests/lint/type checks,
`venv-cv` for OpenCV/video work. Use isolated SQLite for tests. Preserve source
videos, measurement caches and the live match database. Select changes using
development data, then freeze the decision before checking control data.
