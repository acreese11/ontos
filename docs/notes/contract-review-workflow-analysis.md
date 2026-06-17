# Data-Contract Review Workflow — Analysis (2026-06-17)

Analysis of how the contract review/approval user journey is *intended* to fit
together, where it coheres, and where it breaks. Triggered by real friction:
"as a producer I see my own review request in My Actions; starting review makes
the contract read-only and I have to clone it; are the copies linked; how do I
track changes/comments/history together?"

Documentation only — no behavior change. File:line citations are as of this date;
verify against current code before acting.

## Intended journey (as designed)

1. **Producer drafts** → **Request Review** (`draft → proposed`).
   `data_contracts_routes.py:391`, gated `PermissionChecker('data-contracts', READ_WRITE)`.
2. **Steward Start Review** (`proposed → under_review`).
   `data_contracts_routes.py:197`, gated `ApprovalChecker('CONTRACTS')`.
3. Entering `under_review` **locks the contract read-only**: the frontend's
   `EDITABLE_STATUSES = ['draft','proposed']` (`data-contract-details.tsx:69`); a
   non-admin can no longer edit in place.
4. To change anything, **Clone for Editing** → a *personal draft*: a brand-new
   contract id with `draft_owner_id = you`, `status = 'draft'`, and
   `parent_contract_id → original` (`data_contracts_manager.py:4420+`,
   `contract_cloner.py:47,61`). This is the PRD's "tier-1" model
   (`docs/prds/prd-unified-lifecycle-tracking.md:87`).
5. **Commit Changes** promotes the draft (clears `draft_owner_id`) into a **new
   sibling version**, linked by `parent_contract_id` (`commit_personal_draft`,
   `data_contracts_manager.py:4587+`, route `:4194`).
6. **Approve / Reject** (`:147` / `:247`) act on the in-review contract,
   steward-gated.

The model is deliberate: **reviews don't edit a contract in place — they fork a
linked copy and version forward.**

## The frictions, answered

**(a) Why does a producer see their own review request in My Actions? → BUG.**
The approvals queue filters *only* by status, with **no reviewer/requester filter**:
`ApprovalsManager.get_approvals_queue(self, db)` →
`db.query(DataContractDb).filter(status.in_(['proposed','under_review']))`
(`approvals_manager.py:12`). The frontend shows them all
(`required-actions-section.tsx:82`). So everyone — including the requester — sees
every in-review contract. (Distinct from `/api/user/pending-approvals`, which is
the Terms-of-Use first-access wizard, `user_routes.py:85` — not review.)

**(b) Start review → read-only → must clone — intended or workaround? → INTENDED.**
It's the designed clone-to-edit flow (PRD tier model). But the UX cost is real and
baked in: a steward can't tweak in place; they must spawn a separate contract id.
Note the read-only lock is **frontend-only** (`EDITABLE_STATUSES`); backend update
endpoints aren't status-gated, so the lock is advisory.

**(c) Are the copies linked to the original? → YES.**
`data_contracts.py:48` `parent_contract_id = Column(String,
ForeignKey("data_contracts.id", ondelete="SET NULL"), nullable=True, index=True)`,
plus `base_name` (`:49`) and `change_summary` (`:50`); self-relationship `:87`. Set
by the cloner (`contract_cloner.py:61`). Caveat: `ON DELETE SET NULL` silently
orphans lineage if the parent is deleted.

**(d) Can you track changes/comments/history together? → NO — this is the real break.**
Comments and the change-log are keyed by the *literal contract id*
(`entity_type='data_contract'`, `entity_id=<id>`; `change_log.py:13-14`; the UI
mounts `<CommentSidebar entityType="data_contract" entityId={contractId}>`,
`data-contract-details.tsx:1875`). A clone gets a **new id**, and **nothing
aggregates across `parent_contract_id`** — the timeline/comment/change-log read
paths never traverse it. So:
  - Comments/history on a draft attach to the draft's id; the original never shows
    them, and vice-versa → **fragmented across every version**.
  - **"Commit Changes" does NOT merge back into the reviewed original** — it promotes
    the *copy* and leaves the original untouched (`commit_personal_draft:4636`),
    producing a new sibling, not an update. (`get_diff_from_parent:4653` can show a
    diff, but commit never writes to the parent.)

## Verdict

The *intent* is sound — immutable-once-in-review, version-by-clone, lineage via
`parent_contract_id`. But the journey doesn't cohere because **the lineage link is
structural-only: nothing reads it.** To actually "track changes/comments/history
together," the timeline/comment/change-log read paths would need to walk
`parent_contract_id` and present a unified thread; and the approvals queue needs
reviewer-scoping.

## Other flagged issues (real, secondary)

1. **Approvals queue: zero user filtering** (`approvals_manager.py:12`) → friction (a).
2. **`request_steward_review` logs "Created asset review record" but never persists one**
   (`data_contracts_manager.py:5086-5093`) — misleading no-op log.
3. **`request_steward_review` mutates status directly** (`:5069`) instead of via
   `transition_status`, bypassing the workflow gating the other transitions enforce.
4. **Dead, contradictory transition map** `_get_allowed_status_transitions` (`:6013`)
   includes a `certified` status the live map (`lifecycle.py:50`) lacks; no caller found.
5. **Doc/code mismatch on "Certified":** USER-GUIDE treats it as a lifecycle status;
   code made certification an orthogonal dimension (`:3860`).
6. **Comment/change-log fragmentation across parent↔clone** (no `parent_contract_id`
   traversal) → friction (d).
7. **Commit ≠ merge:** "Commit Changes" promotes the copy and leaves the original
   (`commit_personal_draft:4636`) → friction (b/d).
8. **Read-only is frontend-only** (`EDITABLE_STATUSES`); backend update endpoints
   aren't status-gated.

## Options (not yet acted on)

1. **Demo-only:** leave the workflow as-is; keep the demo on the no-edit happy path
   (request → start review → approve → activate → publish — no clone, no fragmentation).
   Zero code risk. This is what `demos/demo-1-author-contract-generation.md` beat 6 does.
2. **Cheap real win:** scope the approvals queue to reviewers (fixes friction *a*) —
   small, contained.
3. **The real fix:** make comments/change-log/timeline `parent_contract_id`-aware so
   history unifies across versions (fixes *d*) — larger; it's what makes the journey
   cohere.
