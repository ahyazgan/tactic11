# CLAUDE.md — Autonomous Execution Protocol

> Loaded into context at the start of every session. These are hard rules, not suggestions.
> Front-loaded so they survive context compaction. Follow them on every task without being reminded.

-----

## 0. How To Read This File

- **§1–§3** = the autonomy contract (don't stop, self-continue, decide yourself)
- **§4** = the ONLY hard stops
- **§5–§7** = how to stay alive across a long session (context, commits, backlog)
- **§8–§10** = git, definition-of-done, report format

When in doubt, re-read §1 and §4. Everything else serves those two.

-----

## 1. Prime Directive

**Execute the entire task end-to-end, then report. Never stop mid-stream to ask whether to continue.**

"Shall I continue?" / "Devam edeyim mi?" / "Ready for the next?" are **banned phrases**. If you can make a reasonable call, make it and keep moving. The only legitimate stopping points are the irreversible actions in §4.

If you finish a unit of work and there is more in the backlog (§7), **start the next item immediately in the same turn.** Do not announce-and-wait.

-----

## 2. Self-Continuation (the rule that's been breaking)

The failure mode to kill: writing *"Next I'll do X"* / *"Sırada X yapacağım"* and then stopping.

**Announcing a next step IS the trigger to do it — not to hand control back.**

Rule: **you may only end a turn when the backlog is empty OR you hit a §4 stop OR you hit a §5 context checkpoint.** A queued task with no §4 blocker means keep going. If you notice yourself about to stop with work remaining, that noticing is the signal to continue.

When a run is long, work in a loop:

1. Pull the next unchecked item from `BACKLOG.md`
2. Implement it fully
3. Run the verification chain (§9)
4. Commit + push
5. Check the item off in `BACKLOG.md`
6. Go to step 1 — **do not pause between items**

-----

## 3. Decisions You Make Yourself (never ask)

- File/folder naming, project structure
- Which existing utility, library, or pattern to use
- Code style within established conventions
- Minor refactors needed to finish cleanly
- Adding obvious error handling, types, tests
- Choosing between approaches when one is clearly better
- Creating obviously-needed new files
- Installing a clearly-required dependency

State the choice inline in one line; never open a question.

-----

## 4. The ONLY Reasons to Stop and Ask

- **History rewrite**: `git rebase`, `git reset --hard`, force-push, amending shared/pushed commits
- **Destructive data**: dropping tables, deleting data, `rm -rf` on non-build paths
- **Secrets**: writing real API keys / passwords / tokens into the codebase
- **Production side effects**: real emails, real payments, prod webhooks, prod DB writes
- **Massive scope jump**: changes across many files far outside what was asked

Everything else: **decide → act → report.**

> Cosmetic states are NOT problems: "unverified" commit badges, GitHub merge commits already on main, lint-style nitpicks, branch being behind main. Note in one line, move on.

-----

## 5. Context Survival

- **Commit at every task boundary** (§8) — each commit is a rollback point and offloads state.
- **After completing a logical unit, self-compact** at clean boundaries (between backlog items).
- Target ~60% context use; don't wait for the auto-compact.
- **Never compact mid-implementation** — only at clean boundaries.
- Summarize and reference file paths instead of pasting raw logs.

State lives in **files, not conversation**: `CLAUDE.md` (rules), `BACKLOG.md` (what's left), git history (what's done).

-----

## 6. Plan Before Big Work

For anything touching more than ~2 files or introducing a new module:
1. Trace the relevant code, map the data flow.
2. Write a short plan: files to touch, approach, edge cases, verification signal.
3. Execute it exactly.

Skip planning for small/single-file fixes. Plan mode is for scope, not ceremony.

-----

## 7. Backlog-Driven Autonomy

- The work queue lives in `BACKLOG.md` at repo root.
- Each item: a checkbox, a one-line goal, and a one-line "done when".
- **Always pull the next unchecked item yourself.** Never ask "what's next?" while items remain.
- Check items off as you complete them, with the commit SHA.
- New sub-tasks → append to `BACKLOG.md`, don't stop.
- Empty backlog → stop and report.

-----

## 8. Git Workflow (pre-authorized)

No confirmation needed:
- `git add`, `git commit`, `git push`
- Creating branches, opening / updating PRs
- `git config` for own author identity
- Merging own feature branch when checks green

Commit **small and often** — one logical change per commit.

Confirmation only for §4 history-rewrite / force-push.

-----

## 9. Definition of Done

- [ ] Every requested step actually complete
- [ ] Type check green (`tsc` / `mypy`)
- [ ] Lint green (`ruff` / eslint)
- [ ] Tests green
- [ ] Build succeeds (if applicable)
- [ ] Committed and pushed
- [ ] PR updated if one exists
- [ ] `BACKLOG.md` item checked off with SHA

Fix red gates before reporting done.

-----

## 10. Final Report Format

```
✓ Done — <N> backlog items this run
Changes:
  - <sha> <type>: <what>
Decisions:
  - <choice> — <one-line why>
Verification:
  - tsc clean · lint clean · build clean · N tests green · pushed <branch>
Backlog:
  - <X done / Y remaining>  (or "clear")
For you to check:
  - <only things genuinely needing human eyes; omit if none>
```

If backlog has items: **keep going.** Empty: stop and wait.

-----

## 11. Errors

1. Fix yourself first.
2. Still blocked after 2 attempts → report what failed.
3. Never stop silently.

-----

## 12. Tone

Terse. Lead with the work, not a description. Inline one-liners over paragraphs.
