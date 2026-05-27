# Ask Ontos — Discovery Quality Plan

**Status:** drafted 2026-05-26, not yet prioritized.
**Owner:** Alan.
**Context:** triaged after a failure case where the agent gave a portfolio gap analysis from a broken+partial view of the catalog.

## TL;DR

The agent is failing at *complete discovery* because the tool layer is broken in three independent ways:

1. The tools that fetch product detail can't read `description` or `output_ports` — they treat ORM relationships as JSON strings. Every product reports `description: None`.
2. The search tool truncates to 20 results and there is no `list_all_*` tool, so portfolio-shape questions get answered from a sample.
3. Semantic links and tags — the discovery surfaces that would catch lexical near-misses — are effectively unpopulated (0 semantic links, 3 tag rows for 47 products).

The agent then layers on its own discipline problems (forgets prior pagination, no "completeness" guard in the system prompt). But fixing the agent before fixing the tools is the wrong order — the tools are lying to it.

**Priority sequence:** tool correctness → tool coverage → semantic surfaces → prompt discipline → skill bundle.

## Why this matters

Discovery is asymmetric: a missed product (false negative) costs duplicate builds, contract conflicts, governance debt, and — in the demo's safety framing — blind spots in operational data. A false positive ("here's a product you didn't ask about") is cheap. The current system is optimized for the wrong side of the asymmetry.

For DAIS specifically: the "watch how Ontos prevents a duplicate-build by surfacing semantic matches" demo only lands if discovery is grounded and complete. Right now the agent would actively recommend building a product that already exists (verified: it called out "Fuel Hedging & Pricing" as a gap while "Hedging Positions" sits in the same Fuel domain).

## Empirical findings (verified against `ontosdb` Lakebase, schema `app_ontos_dais`)

### Tool bugs

| # | File:Line | Bug | Effect |
|---|-----------|-----|--------|
| F1 | `src/backend/src/tools/data_products.py:53,265` | `product.description` is an ORM relationship (`DescriptionDb` object) but treated as JSON string | `description` always returns `None` |
| F2 | `src/backend/src/tools/data_products.py:65,253` | `product.output_ports` is a `list[OutputPortDb]` but treated as `list[dict]` | `output_tables` always returns `[]` |
| F3 | `src/backend/src/tools/data_products.py:287` | `filtered[:20]` hard truncation | Caller never sees beyond 20 even though `total_found` is set correctly |
| F4 | `src/backend/src/tools/data_products.py:186` | `limit(500).all()` then in-memory filter | Doesn't scale, but acceptable at current sizes |

Same `description`/`output_ports` pattern likely repeats in `data_contracts.py`, `domains.py`, etc. — needs audit.

### Data state

| Surface | State | Implication |
|---|---|---|
| Products | 47, all have populated `purpose` in `data_product_descriptions` | Descriptions exist but agent can't see them (F1) |
| Contracts | 12 | Discoverable separately, not part of `search_data_products` |
| Semantic links | **0 rows in `entity_semantic_links`** | Ontology grounding has nothing to ground against |
| Tags | 3 rows total | Tag-based discovery non-functional |
| Domains in DAIS catalog | Crew, Flight Ops, Fuel, Maintenance, Passenger, Reference Data, Regulatory, Scheduling | Agent's transcript referenced old domain names — session was against stale local data |

### Gap-recommendation audit (the actual failure case)

Of the 11 gaps the agent recommended, verified against `app_ontos_dais.data_products`:

| # | Agent recommendation | Status | Existing product |
|---|---|---|---|
| 1 | Revenue & Yield Management | ✅ genuine gap | — |
| 2 | Cargo & Freight Manifests | ✅ genuine gap | — |
| 3 | Ground Operations & Turnaround Times | ✅ genuine gap | — |
| 4 | NOTAM Feed | ✅ genuine gap | — |
| 5 | TAF Forecasts | ✅ genuine gap (METAR ≠ TAF) | — |
| 6 | Fuel Hedging & Pricing | ❌ **DUPLICATE** | "Hedging Positions" (Fuel) |
| 7 | Aircraft Lease & Ownership Register | ⚠ partial — only fleet reference data exists | "Aircraft Type Master" (Reference Data) |
| 8 | Disruption Recovery / IROPS Plans | ⚠ partial — diversions covered | "Diversion Decisions" (Flight Ops) |
| 9 | Customer Feedback & NPS | ✅ genuine gap | — |
| 10 | Sustainability / SAF Usage | ❌ **DUPLICATE** | "SAF Supply Forecast" (Fuel), "Flight Emissions" (Flight Ops) |
| 11 | Crew Fatigue Risk Management | ⚠ partial — bidding/rosters/sick calls exist; no FRMS analytics | Crew Bidding, Sick Call Tracking, Crew Rosters & Duty Logs |

2 direct duplicates (false-positive gaps), 3 partial overlaps the agent failed to nuance, 6 genuine gaps. The 2 dupes alone justify the work.

## Recommendations

### Phase 1 — Stop lying to the agent (tool correctness)

Goal: when the agent asks for a product, it gets the actual data.

1. **Fix `GetDataProductTool` description/output_ports read** (`tools/data_products.py:51-72`). Replace the JSON-parse dance with proper ORM attribute access:
   ```python
   desc_purpose = product.description.purpose if product.description else None
   output_tables = [p.name for p in (product.output_ports or [])]
   ```
2. **Same fix in `SearchDataProductsTool`** (`tools/data_products.py:225-271`) — both the match-filter branch and the result-projection branch.
3. **Audit all other tools** (`tools/data_contracts.py`, `tools/domains.py`, etc.) for the same `json.loads(orm_relationship)` pattern. Grep `json.loads(p.` and `isinstance(*, str) else *.description`.
4. **Lift the `[:20]` truncation** (`tools/data_products.py:287`) — return all matches up to the 500 cap, add `truncated: bool` based on the cap, not a fixed window. Same for `data_contracts.py`.
5. **Add a regression test** that asserts a fetched product's `description` and `output_tables` round-trip correctly against seed data. Catch this class of bug going forward.

**Effort:** ~half a day. **Blocker for everything else.**

### Phase 2 — Give the agent the right verbs (tool coverage)

Goal: portfolio-shape questions never get answered from a sample.

6. **New tool: `list_all_data_products(fields=[...])`.** Returns *every* product in one call with a configurable compact projection. Default fields: `name, domain, status, purpose, output_tables, tags`. Same for `list_all_data_contracts`, `list_all_domains`.
7. **New tool: `get_portfolio_overview()`.** Returns one document:
   ```json
   {
     "products": {"total": 47, "by_domain": {...}, "by_status": {...}},
     "contracts": {"total": 12, "by_status": {...}},
     "domains": [...],
     "ontology_coverage": {"concepts_with_products": N, "uncovered_concepts": [...]},
     "orphans": {"products_without_contract": [...], "products_without_domain": [...]}
   }
   ```
   This is what the agent should call *first* for any "what do we have / what's missing" question.
8. **New tool: `get_ontology_coverage()`** — per-concept linked-products count. Returns the empty/sparse rows that define gaps semantically rather than lexically. Useless until Phase 3 lands data, but ship the tool now so the seam exists.
9. **Add a `complete: bool` and `total_count: int` to every list-shaped tool response.** Force the agent to confront partial data.
10. **System-prompt addendum:** "Portfolio, coverage, and gap questions must call `get_portfolio_overview` first. If any subsequent list result has `complete: false`, either fetch the remainder or state explicitly that the answer is provisional. Never speculate about gaps from a partial inventory."

**Effort:** 1-2 days.

### Phase 3 — Populate the semantic surfaces

Goal: lexical near-misses ("Hedging" vs "Fuel Hedging & Pricing", "SAF Supply Forecast" vs "Sustainability / SAF") stop being misses.

11. **Seed `entity_semantic_links` for the 47 DAIS products.** Link each to its ontology concept(s). Even a one-link-per-product baseline closes most fuzzy-match failures. Demo data generation script under `data/dais/` or similar.
12. **Seed product tags meaningfully.** At minimum: lifecycle stage, criticality, source-vs-aggregate-vs-consumer alignment (the `source-aligned`/`consumer-aligned` patterns already in the descriptions). Expose as a discovery surface.
13. **Extend search to traverse semantic + tag surfaces.** `SearchDataProductsTool` already attempts semantic matching at `data_products.py:201-215` — once links exist, it'll start working. Add tag matching with the same pattern.
14. **Return matched-surface attribution.** Each search hit should report *why* it matched: `{"matched_on": ["name", "ontology:concept_iri"]}`. The agent can then justify its answers, and you can debug false negatives.

**Effort:** 2-3 days (mostly data generation for DAIS, code is small).

### Phase 4 — Agent discipline (prompt + skill)

Goal: even with perfect tools, the agent doesn't drift mid-conversation.

15. **System prompt: completeness contract.** Add a section: "Discovery answers must enumerate the surfaces checked (name, description, ontology concept, tag, output-table FQN). When stating something doesn't exist, list which surfaces returned empty."
16. **Build the first real skill: `portfolio-analysis`.** Per the prior discussion, this is the workflow that's earned a skill. Bundle: `get_portfolio_overview`, `list_all_data_products`, `get_ontology_coverage`, `search_data_products` (forced multi-surface). Prompt fragment enforces ontology-first reasoning over name-brainstorming.
17. **Skill scaffold** — file-based skills under `src/backend/src/skills/`, registry mirroring `ToolRegistry`, `list_skills` + `invoke_skill` meta-tools, session-level `active_skill` field on `LLMSessionDb`. Only build this if we end up wanting >1 skill — for a single skill the prompt-fragment approach is fine.

**Effort:** 1 day for prompt + portfolio skill; 2-3 days additional if scaffold-as-framework.

## What we are NOT doing (and why)

- **Migrating to a routing LLM ("skill-routed orchestration").** Premature. Sonnet picks tools well enough; the failures here are upstream of tool selection.
- **Adding a vector index / embeddings layer for products.** Tempting but unnecessary if semantic links are populated. Revisit only if Phase 3 doesn't close the recall problem.
- **Streaming/render bug investigation.** The transcript has truncated words (`1asonal`, `Pricimption`, `pro draft`). Frontend issue, not LLM. Logged but out of scope here.

## Open questions

- Should `list_all_*` tools enforce a hard cap (e.g., 1000 rows) and lean on the `truncated` flag? Or unbounded and trust the caller? Lean toward bounded with a clear flag.
- For DAIS demo: is it worth scripting a deterministic "find the duplicate" demo case? Yes — a recorded Hedging-Positions-style example is the cleanest narrative beat.
- Is `data_contracts` the right next discovery surface to add as a first-class tool, or do we surface contracts only via products? Contracts can describe data that has no product yet — they are a leading indicator of intent. Worth surfacing directly.

## Sequencing recommendation

Phase 1 unblocks everything else and is half a day. Do it next time the branch has air.
Phase 2 ships the right verbs and lets us measure improvement.
Phase 3 is the DAIS-specific data work and the demo's real foundation.
Phase 4 is the discipline layer — meaningful only after 1-3 are in.

Do not start Phase 4 before Phase 1.
