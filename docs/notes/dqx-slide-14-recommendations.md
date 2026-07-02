# DAIS deck — slide #14 "DQX in 2026 — What Shipped": review & recommendations

**Reviewed:** 2026-06-17 against DQX **0.15.0** (released 2026-06-13).
**Source deck:** Google Slides (`.pptx` in Drive). ⚠️ The editor's `?slide=id.p19`
anchor maps to the **"Built on Open Source"** slide, *not* this one — the DQX-updates
slide is **#14 "DQX in 2026 — What Shipped."** (If the OSS slide was meant instead,
recommendations differ.)

## Slide #14 as it stands
Title "DQX in 2026 — What Shipped". Bullets: native ODCS→DQX rule generation
("the contract compiles into running rules, not a script we wrote"), DQX Studio
(no-code authoring), AI-assisted rule generation, Presidio PII detection, ML anomaly
detection (Isolation Forest), `has_no_aggr_outliers` rolling-window, Agent Skills
(Claude Code / Cursor / Copilot / Genie Code generate DQX rules from the contract).
Version markers: **"v0.11 — Dec 2025 → v0.14 — May 2026."**

The slide is **one release stale** — 0.15.0 shipped 2026-06-13. Recommendations:

## Recommendations

1. **Bump the version marker `v0.14 — May 2026` → `v0.15 — Jun 2026`.** For a June-2026
   talk, leading with last month's release reads as current; the old marker visibly
   dates the slide. Also accurate — the demo now pins `databricks-labs-dqx>=0.15.0`.

2. **Add the upstream-contribution beat (strongest credibility line).** 0.15 fixed
   native ODCS→DQX rule generation working *without* the `[llm]` extra — **DQX #1191,
   our own PR.** Suggested line: *"Native ODCS→DQX rule-gen now runs anywhere —
   upstream fix (#1191) ours, shipped in 0.15."* Turns the top bullet from "we use DQX"
   into "we contribute to DQX" — lands hard with an OSS-Labs audience.

3. **Upgrade the anomaly bullet for 0.15.** "ML anomaly detection (Isolation Forest)"
   is now joined by **AI-generated explanations by default** — `has_no_row_anomalies`
   attaches plain-language cause / business-impact / suggested-action via `ai_query`
   against Model Serving (no driver-side LLM). Reframe as *"ML anomaly detection +
   AI-explained anomalies (0.15)."* Freshest capability; ties to the talk's GenAI thread.
   *Caveat:* it's on by default and makes serving-endpoint calls — fine to showcase,
   flag for cost in a live run.

4. **Add the new 0.15 checks; lead with geofencing (on-theme for Safe Skies).** 0.15
   adds `is_valid_email` and geospatial checks (`is_geo_contains` / `covers` /
   `intersects` / `touches` / `within`). For an aviation deck, a geofencing example —
   *"validate aircraft lat/lon falls within expected airspace"* — is a concrete bullet
   no generic DQX slide would have.

5. **Emphasis / framing.**
   - Make **"the contract compiles into running rules — not a script we wrote"** the
     visual **headline**, not one bullet among seven. It's the talk's thesis
     (governance-as-code); everything else is supporting evidence.
   - Keep **Agent Skills** prominent (coding agent generates DQX rules from the
     contract) — most forward-looking, and in 0.15 it no longer needs the `[llm]`-extra
     workaround.
   - **Cut / de-emphasize DQX Studio** unless a demo actually shows it — don't surface
     UI you won't demonstrate.

## Cross-deck note
These edits share a spine with the proposed **"Where this goes next"** slide (parked):
upstream-#1191 + new-0.15-checks + *contract-is-the-ruleset*. Keep slide #14 to
*shipped* capabilities; keep roadmap items on the (future) next-steps slide.
