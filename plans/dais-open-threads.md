# DAIS 2026 — Open Threads Tracker

Single source of truth for in-flight work on the Safe Skies / DAIS 2026 talk.
Updated as items close. Legend: ✅ done · ⏳ in progress · ⚠️ blocked · ❌ not started · ❓ needs clarification.

## Current execution order (per Alan, 2026-06-14)

1. **Get deck + flesh demos 2 & 3** → ✅ done (deck pulled + parsed; demo-2/demo-3 fleshed to 5-min slots; README reconciled)
2. **Commit the dev tooling** (Makefile + peer-review-pr skill) → ⏳ next
3. **Fast-deploy work** → ❌
4. **Build Ask-Ontos streaming** → ❌

### Decisions needed from Alan (raised, not blocking)
- **Narration ownership:** honored the deck (Enforce = Alan lead + Michael ops;
  Discover = Michael lead + Alan arch). Confirm or override.
- **Genie slide 22:** keep as ~30s static payoff or remove? (Not in agenda lineup.)

---

## A. Talk & speaker notes
- **A1** Speaker notes (Alan's slides) — ✅ largely done; verify append-only block is complete.
- **A2** Current deck reference (`safe_skies_dais2026.pptx`, id `1cTT3tMou9RVEnuZatAdCIVR__UqXNldC`, modified 2026-06-14 05:41) — ✅ pulled + parsed (33 slides, `/tmp/deck_outline.md`). Reference only, do not edit. Agenda (slide 5 notes) = reconciled source: 4 demos × ~5 min, lifecycle order.
- **A3** Flesh demos 2 (Enforce) & 3 (Discover) toward ~5 min — ✅ done.

## B. Demo docs
- **B1** demo-1 Author — ✅ ready.
- **B2** demo-2 Enforce (DQX quarantine) — ✅ fleshed to ~5:00 slot (deck slide 16).
- **B3** demo-3 Discover (marketplace/subscribe) — ✅ fleshed to ~5:00 slot (deck slide 18); subscribe live on camera. Realistically ~3:30 — thinnest demo.
- **B4** demo-4 Maintain — Coverage ✅ built+validated; notify loop ❌; drift ❌.

## C. Code / dev
- **C1** Live-run bug fixes — ✅ merged (PR #12).
- **C2** Compliance feature (Contract Coverage) — ✅ merged (PR #16/#18).
- **C3** Dev tooling (`make dev` Makefile + `peer-review-pr` skill) — ❌ untracked; needs PR. **(Order #2)**
- **C4** Ask-Ontos streaming (generation-progress/CoT) — ❌ deferred, never built. **(Order #4)**
- **C5** Fast-deploy work (Boeing pattern: no root package.json, prebuilt dist, dev-mode bundle sync) — ❌. **(Order #3)** Confirm exact scope.
- **C6** Deploy dais fixes to live app — ❌ PRs #12/#16/#18 on `dais` but live app on old code.

## D. Decisions deferred
- **D1** Compliance rule refinement — conflict-example (multi-contract table) for Maintain beat is the one to decide.
- **D2** Drift beat (Lakehouse Monitor) — Alan plans to build; fold into demo-4 Appendix B. Cut candidate otherwise.

## Constraints (always)
- Everything through branch + PR; no direct commits to `dais`.
- gh: `acreese11` acts on the fork (not `alan-reese_data`); switch in same bash command.
- Local dev = local Postgres; UC tables always remote; never restart servers.
- Commits end `Co-authored-by: Isaac`; PR bodies end `This pull request and its description were written by Isaac.`
