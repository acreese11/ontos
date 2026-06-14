---
name: peer-review-pr
description: >-
  Run immediately after creating a pull request in this repo (acreese11/ontos, base `dais`).
  Dispatches independent critical-review subagents that post findings to the PR, then
  synthesizes them — fix blockers before calling the PR ready / merging. Use after every `gh pr create`.
---

# Peer-review every PR

After opening **any** PR into `dais` in `acreese11/ontos`, immediately run this
review. It's automatic from PR creation onward — the user does not need to ask.
**Do not declare a PR "ready" or merge it without it.** (This repo has no
GitHub-Actions Claude review — the review is local, via this skill.)

**Why:** a single author has systematic blind spots. Independent reviewers —
fresh context, never saw the author's reasoning — catch correctness bugs, edge
cases, test gaps, security issues, migration hazards, and doc drift the author
missed. Process, not optional polish.

## How to dispatch

In the same turn as `gh pr create`:

- Launch **1–2 `general-purpose` subagents via the Agent tool with `run_in_background: true`**.
  Use **2 agents** for any non-trivial PR; a single agent is only acceptable for a tiny
  one-file change where a lens split would just duplicate work.
- Split the 2 by lens:
  1. **Correctness / security / tests** — bugs, edge cases, injection/SSRF, credential leaks,
     concurrency, auth gating, missing coverage.
  2. **Architecture / design-alignment / "what's missing"** — layering (route → controller →
     repository → db_model/api_model), CLAUDE.md/docs consistency, ODCS/ODPS conformance, UX.
- **Independence is the point.** Each agent reads the diff cold and must **verify rather than
  speculate** (run commands, inspect SDK/source, reproduce). Give them the **raw diff + the PR
  body**, not your re-summary, and have at least one derive the change's *intent* from the diff
  alone. Pin the diff to a fresh remote ref:
  `git fetch acreese11 && git diff acreese11/dais...<branch>` (base is `dais`).

## Reviewer authority (read this first)

The reviewer owns the scope of its own review. The author's pointers are a **floor, not a
ceiling** — optional hints about *suspected* weak spots, explicitly **non-exhaustive and possibly
wrong**. The highest-value thing a reviewer produces is a real problem the author **didn't** flag:

- **Do an independent, full-surface review regardless of any hints.** Form your own model of what
  the change does and where it could break.
- The author's questions can be **incomplete, mis-framed, or steer you away from the real issue.**
  Treat them as one input. **Challenge the framing itself** if it's hiding something.
- Findings **outside** the author's hints are the most valuable — surface them prominently.

**Baseline sweep every review covers** (a floor, not a ceiling — keep ranging past it):
correctness/logic, edge cases & error handling, concurrency/races, **security** (auth via
`PermissionChecker`/`FeatureAccessLevel`, SQL injection, SSRF — this repo has a prior DQX
SSRF fix; credential/token leakage in job logs), config & secrets handling, **data integrity &
Alembic migrations**, **API/contract changes & ODCS/ODPS conformance + backward-compat**,
idempotency/retry, observability/logging, dependency & supply-chain, **test coverage & whether
tests actually assert behavior**, performance/resource use, docs accuracy, and consistency with
CLAUDE.md + the rest of the codebase (the route→controller→repository pattern, RORO API models).

## Hard gates for this repo (BLOCKER-eligible)

- **Alembic single head.** CI enforces exactly one head (`scripts/check-alembic-heads.py`,
  `check-alembic-heads` job). A PR that adds a sibling revision (a second head) without a
  declared merge revision + `alembic-branch` label is **BLOCKER**. New migrations must descend
  from the live head (rebase first).
- **Doc/spec drift.** A PR that changes behavior, contracts, schema, or architecture should update
  the relevant living doc **in the same PR** — `CLAUDE.md` (feature/architecture descriptions),
  `src/docs/USER-GUIDE.md`, the relevant `docs/prds/*`, or the feature's section. The test is
  "did the behavior a doc describes move?" — not the PR's label. A "refactor" that quietly changes
  a contract is NOT exempt; a docs-only/test-only/behavior-preserving refactor is. When a doc that
  *defines* the changed behavior isn't updated → BLOCKER-eligible; a passing mention → IMPORTANT.
  Net-new surface no doc covers yet isn't drift (recommend a doc; don't block).
- **Auth gating.** New routes must carry the correct `PermissionChecker(feature, level)`; a new
  mutating endpoint with no/over-broad gating is BLOCKER-eligible. (See the ODCS endpoint model:
  machine pull `/odcs.yaml|.json` is gated to published status via `_assert_pullable`; the
  browser `/odcs/export` is intentionally ungated for authors — match that intent for new endpoints.)

## Reviewer prompt template

Don't say "review this," and don't *only* hand over a question list. Give the agent the standing
mandate + context, then optional pointers clearly marked as such:

> You are a critical, independent code reviewer. Find bugs/design flaws/risks in PR #N of
> `acreese11/ontos`. Repo: /Users/alan.reese/Source/ontos (branch `<branch>`, base `dais`).
> Run `git fetch acreese11`, then read `git diff acreese11/dais...<branch>` (don't trust a stale local ref).
> Context: <one-paragraph what the PR does>.
> **Your mandate: run a full independent review. Form your own view of what could break.**
> Cover the baseline sweep (correctness, edge cases, error handling, concurrency, security/auth,
> data integrity + Alembic single-head, API/ODCS conformance + back-compat, test quality,
> performance, CLAUDE.md/docs + codebase consistency). **If the PR changes behavior/contracts/
> schema the docs describe but doesn't update them in the same PR, that's BLOCKER-eligible drift.**
> **Findings beyond the pointers below are the most valuable — actively hunt for them, and
> challenge the PR's own framing if it's hiding something.**
> Optional pointers (NON-EXHAUSTIVE, may be incomplete or wrong — do not treat as the scope):
> 1. <suspected risk> … 2. <suspected risk> …
> For each finding: **severity BLOCKER / IMPORTANT / NITPICK**, `file:line`, problem, concrete fix.
> Then post the top BLOCKER/IMPORTANT findings as a consolidated review on the PR.
> **Switch the gh account in the SAME bash command** (it does not persist across calls):
> `gh auth switch --user acreese11 && gh pr review <pr> --repo acreese11/ontos --comment --body "..."`.

Keep optional pointers **short** — a few genuine uncertainties, not an exhaustive checklist that
frames the whole review. Every finding (chat + PR comment) carries **severity**, **file:line**,
**problem**, **suggested fix**.

## gh account quirk (important)

The active gh account is often `alan-reese_data` (an **Enterprise Managed User**) which **cannot
act on `acreese11/ontos`** (a personal fork) — `gh pr create`/`review` fail with
"Unauthorized: As an Enterprise Managed User…". Use the **`acreese11`** account, and because the
active account does **not** persist across bash invocations, prepend the switch in the **same** call:

```
gh auth switch --user acreese11 && gh pr review <pr> --repo acreese11/ontos --comment --body "..."
```

`gh pr review --comment` works on your **own** PR (only `--approve`/`--request-changes` are blocked
for self-authored PRs). A `--comment` review can't later be dismissed via `gh`/API — don't post
throwaway/probe reviews. (`git push` uses a separate credential and works regardless.)

## Synthesis & fix loop

When the agents report back:

1. **Aggregate & dedup** findings in chat, categorized BLOCKER / IMPORTANT / NITPICK. Collapse
   duplicates across lenses. When reviewers **disagree**, adjudicate it yourself and state the call.
2. **BLOCKER** → fix on the same branch (new commit) *before* ready/merge.
3. **IMPORTANT** → surface to the user: fix now / defer to a follow-up / accept (with rationale).
4. **NITPICK** → note; don't act unless asked.
5. Reviewers are advisors, not authorities — **push back** when a finding is wrong (contradicted by
   a live test you ran, or asserts behavior that doesn't hold in *this* environment). Report honestly.
6. **Re-check the fix commits** — blocker fixes are fresh single-author work with the same blind
   spots; re-diff them, and for a non-trivial fix send it back through a reviewer.
7. Post a **synthesis comment** on the PR: what was fixed, deferred, or rejected, and why.
8. **Done** = blockers fixed + re-checked, importants dispositioned, synthesis posted. Merge only then.

## Caveats

- Subagents occasionally die on transient API errors. If both attempts fail, **do the review inline
  yourself** — run the full baseline sweep, not just the seeded pointers — and **tell the user the
  review was self-run** (the independence the process leans on was lost).
- The value is in the independent sweep, not the seeded pointers. If you only ever confirm the
  author's hints, the review added nothing.
