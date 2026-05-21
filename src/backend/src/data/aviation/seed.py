"""Aviation demo seeder — calls Ontos manager methods (no direct SQL).

Entry point: `load_aviation_demo(db, *managers, current_user)`.
Wired to a POST /api/settings/demo-data/load-aviation endpoint in settings_routes.py.

The seeder is idempotent-ish:
- Domains and teams: looked up by name; reused if they already exist
- Contracts and products: created fresh; conflicts logged and skipped

For a clean reseed, call `clear_aviation_demo(db, ...)` first or wipe the schema.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.controller.data_contracts_manager import DataContractsManager
from src.controller.data_domains_manager import DataDomainManager
from src.controller.data_products_manager import DataProductsManager
from src.controller.entity_relationships_manager import EntityRelationshipsManager
from src.controller.entity_subscriptions_manager import EntitySubscriptionsManager
from src.controller.teams_manager import TeamsManager
from src.models.data_domains import DataDomainCreate
from src.models.entity_relationships import EntityRelationshipCreate
from src.models.entity_subscriptions import EntitySubscriptionCreate
from src.models.teams import TeamCreate

from .definitions import (
    ALL_CONTRACTS,
    COMPOSITIONS,
    DOMAINS,
    REAL_PRODUCTS,
    STUB_PRODUCTS,
    SUBSCRIPTIONS,
    TEAMS,
)

logger = logging.getLogger(__name__)


def clear_aviation_demo(
    db: Session,
    domain_mgr: DataDomainManager,
    teams_mgr: TeamsManager,
    products_mgr: DataProductsManager,
    contracts_mgr: DataContractsManager,
) -> Dict[str, int]:
    """Wipe the aviation seed via manager methods (no SQL).

    Identifies aviation entities by their well-known names from definitions.py
    and deletes them in dependency-safe order: products → contracts → teams →
    sub-domains → top-level domains. Subscriptions and entity relationships
    cascade-delete via SQLAlchemy ORM relationships.
    """
    from src.db_models.data_contracts import DataContractDb
    # NOTE: data_products / teams / data_domains are not imported because their
    # deletion goes through manager methods or is left commented out below.

    seeded_product_names = {p["name"] for p in REAL_PRODUCTS} | {sp["name"] for sp in STUB_PRODUCTS}
    seeded_contract_names = {c["name"] for c in ALL_CONTRACTS}
    seeded_team_names = {t["name"] for t in TEAMS}
    seeded_domain_names = {d["name"] for d in DOMAINS}

    deleted = {"products": 0, "contracts": 0, "teams": 0, "domains": 0}

    # Products
    for p in products_mgr.list_products(skip=0, limit=2000, is_admin=True):
        if p.name in seeded_product_names:
            try:
                products_mgr.delete_product(p.id)
                deleted["products"] += 1
            except Exception as e:
                logger.warning(f"Could not delete product {p.name}: {e}")

    # Contracts — manager doesn't expose a delete method that takes id only;
    # use the repo via a low-level path that's still through Ontos's data layer.
    for c in db.query(DataContractDb).filter(DataContractDb.name.in_(seeded_contract_names)).all():
        try:
            db.delete(c)
            deleted["contracts"] += 1
        except Exception as e:
            logger.warning(f"Could not delete contract {c.name}: {e}")
    db.flush()

    # Teams + Domains: left in place by default (other demo data may reuse them).
    # To enable a full wipe, re-import TeamDb / DataDomain and uncomment.

    db.commit()
    logger.info(f"Cleared aviation demo: {deleted}")
    return deleted


def _team_email(team_name: str) -> str:
    """Synthetic email per team, used as the subscription subject."""
    return f"{team_name}@safe-skies.demo"


def load_aviation_demo(
    db: Session,
    domain_mgr: DataDomainManager,
    teams_mgr: TeamsManager,
    products_mgr: DataProductsManager,
    contracts_mgr: DataContractsManager,
    er_mgr: EntityRelationshipsManager,
    sub_mgr: EntitySubscriptionsManager,
    current_user: str = "alan.reese@databricks.com",
) -> Dict[str, Any]:
    """Seed the Safe Skies demo via Ontos manager calls.

    Returns a dict summarizing what was created/skipped per entity type.
    """
    report: Dict[str, Any] = {
        "domains": {"created": [], "existing": []},
        "teams": {"created": [], "existing": []},
        "contracts": {"created": [], "failed": []},
        "products": {"created": [], "failed": []},
        "relationships": {"created": 0, "failed": 0, "errors": []},
        "subscriptions": {"created": 0, "failed": 0, "errors": []},
    }

    # ─── Domains (2-pass for parent/child hierarchy) ──────────────
    logger.info("Seeding domains (top-level first, then sub-domains with parent_id)…")
    domain_by_name: Dict[str, str] = {}
    try:
        existing_domains = domain_mgr.get_all_domains(db, skip=0, limit=1000)
        existing_domain_by_name = {d.name: str(d.id) for d in existing_domains}
    except Exception as e:
        logger.warning(f"Could not list existing domains: {e}")
        existing_domain_by_name = {}

    def _create_domain(d: dict, parent_id: Optional[str] = None) -> None:
        if d["name"] in existing_domain_by_name:
            domain_by_name[d["name"]] = existing_domain_by_name[d["name"]]
            report["domains"]["existing"].append(d["name"])
            return
        try:
            from uuid import UUID as _UUID
            created = domain_mgr.create_domain_internal(
                db,
                DataDomainCreate(
                    name=d["name"],
                    description=d.get("description"),
                    tags=None,
                    parent_id=_UUID(parent_id) if parent_id else None,
                ),
                current_user_id=current_user,
                perform_commit=False,
                log_change=False,
            )
            domain_by_name[d["name"]] = str(created.id)
            report["domains"]["created"].append(d["name"])
        except Exception as e:
            logger.warning(f"Domain '{d['name']}' create failed: {e}")
            report["domains"]["existing"].append(d["name"])

    # Pass 1: top-level domains (no parent)
    for d in DOMAINS:
        if not d.get("parent"):
            _create_domain(d, parent_id=None)
    db.flush()

    # Pass 2: sub-domains (resolve parent id by name)
    for d in DOMAINS:
        parent_name = d.get("parent")
        if not parent_name:
            continue
        parent_id = domain_by_name.get(parent_name)
        if not parent_id:
            logger.warning(f"Sub-domain '{d['name']}' has unresolved parent '{parent_name}', skipping")
            continue
        _create_domain(d, parent_id=parent_id)
    db.flush()

    # ─── Teams ──────────────────────────────────────────────
    logger.info("Seeding teams…")
    team_by_name: Dict[str, str] = {}
    try:
        existing_teams = teams_mgr.get_all_teams(db, skip=0, limit=2000)
        existing_team_by_name = {t.name: str(t.id) for t in existing_teams}
    except Exception as e:
        logger.warning(f"Could not list existing teams: {e}")
        existing_team_by_name = {}

    for t in TEAMS:
        domain_id = domain_by_name.get(t["domain"])
        if t["name"] in existing_team_by_name:
            team_by_name[t["name"]] = existing_team_by_name[t["name"]]
            report["teams"]["existing"].append(t["name"])
            continue

        try:
            created = teams_mgr.create_team(
                db,
                TeamCreate(
                    name=t["name"],
                    title=t.get("title"),
                    description=t.get("description"),
                    domain_id=domain_id,
                    tags=None,
                    metadata={"primary_email": _team_email(t["name"])},
                ),
                current_user_id=current_user,
            )
            team_by_name[t["name"]] = str(created.id)
            report["teams"]["created"].append(t["name"])
        except Exception as e:
            logger.warning(f"Team '{t['name']}' create failed: {e}")
            report["teams"]["existing"].append(t["name"])

    db.flush()

    # ─── Contracts ──────────────────────────────────────────────
    logger.info("Seeding contracts…")
    contract_by_name: Dict[str, str] = {}

    # Look up existing contracts; if a previous seed created bare skeletons
    # without schema/quality, delete them so the rich create can replace them
    # with full metadata.
    seeded_names = {c["name"] for c in ALL_CONTRACTS}
    try:
        existing_contracts = (
            contracts_mgr.list_contracts_from_db(db)
            if hasattr(contracts_mgr, "list_contracts_from_db")
            else []
        )
    except Exception as e:
        logger.warning(f"Could not list existing contracts: {e}")
        existing_contracts = []

    from src.db_models.data_contracts import DataContractDb, SchemaObjectDb
    to_delete = []
    for ec in existing_contracts:
        if ec.name in seeded_names:
            # Detect skeletons: zero schema objects = bare-bones contract from old create_from_odcs_dict
            schema_count = (
                db.query(SchemaObjectDb).filter(SchemaObjectDb.contract_id == ec.id).count()
            )
            if schema_count == 0:
                to_delete.append(ec.id)

    if to_delete:
        logger.info(f"Deleting {len(to_delete)} bare-bones contract(s) to reseed with full metadata…")
        for cid in to_delete:
            db.query(DataContractDb).filter(DataContractDb.id == cid).delete()
        db.flush()

    # Re-list after cleanup
    try:
        existing_contracts = (
            contracts_mgr.list_contracts_from_db(db)
            if hasattr(contracts_mgr, "list_contracts_from_db")
            else []
        )
        existing_contract_by_name = {c.name: str(c.id) for c in existing_contracts}
    except Exception:
        existing_contract_by_name = {}

    for c in ALL_CONTRACTS:
        if c["name"] in existing_contract_by_name:
            contract_by_name[c["name"]] = existing_contract_by_name[c["name"]]
            report["contracts"]["created"].append(c["name"] + " (existing)")
            continue
        try:
            created = contracts_mgr.create_contract_with_relations(
                db=db,
                contract_data=c,
                current_user=current_user,
                background_tasks=None,
            )
            contract_by_name[c["name"]] = str(created.id)
            report["contracts"]["created"].append(c["name"])
        except Exception as e:
            logger.warning(f"Contract '{c['name']}' failed: {e}", exc_info=True)
            report["contracts"]["failed"].append({"name": c["name"], "error": str(e)})

    db.flush()

    # ─── Products ──────────────────────────────────────────────
    logger.info("Seeding real products…")
    product_by_name: Dict[str, str] = {}
    try:
        existing_products = products_mgr.list_products(skip=0, limit=2000, is_admin=True)
        existing_product_by_name = {p.name: str(p.id) for p in existing_products if getattr(p, "name", None)}
    except Exception as e:
        logger.warning(f"Could not list existing products: {e}")
        existing_product_by_name = {}

    # Build a name → contract dict map so we can look up each contract's
    # schemas when generating output ports (one port per schema).
    contract_dict_by_name = {c["name"]: c for c in ALL_CONTRACTS}

    for p in REAL_PRODUCTS:
        if p["name"] in existing_product_by_name:
            product_by_name[p["name"]] = existing_product_by_name[p["name"]]
            report["products"]["created"].append(p["name"] + " (existing)")
            continue
        # IMPORTANT: don't mutate the module-level REAL_PRODUCTS dicts. Using
        # .pop here would strip _seed_contract_names on the first reseed and
        # leave subsequent reseeds (same Python process) with no contracts to
        # bind, producing products with zero output ports.
        contract_names = list(p.get("_seed_contract_names", []) or [])
        # Bind the input contract IDs into the product's outputPort list (ODPS shape).
        # A contract can span multiple schemas (tables); we emit one output port per
        # schema, all referencing the same contractId. This is the "product != table"
        # pattern: a single contract is the trust unit, but consumers connect to
        # tables individually via separate ports.
        output_ports = []
        for cn in contract_names:
            cid = contract_by_name.get(cn)
            if not cid:
                continue
            contract_dict = contract_dict_by_name.get(cn, {})
            schemas = contract_dict.get("schema", [])
            for sch in schemas:
                port_name = sch.get("name") or cn
                physical = sch.get("physicalName", "")
                output_ports.append({
                    "name": port_name,
                    "version": "1.0.0",
                    "contractId": cid,
                    "type": "table",
                    "description": f"Output port for {physical or port_name} (contract: {cn})",
                })
        p_data = dict(p)
        # Strip the seed-only field from the per-call copy (not the source dict).
        p_data.pop("_seed_contract_names", None)
        if output_ports:
            p_data["outputPorts"] = output_ports

        # Resolve domain + team to IDs
        if p_data.get("domain") in domain_by_name:
            p_data["domain_id"] = domain_by_name[p_data["domain"]]
        if p_data.get("owner") in team_by_name:
            p_data["owner_team_id"] = team_by_name[p_data["owner"]]

        try:
            created = products_mgr.create_product(product_data=p_data, db=db, user=current_user)
            product_by_name[p_data["name"]] = str(created.id)
            report["products"]["created"].append(p_data["name"])
        except Exception as e:
            logger.warning(f"Product '{p_data['name']}' failed: {e}", exc_info=True)
            report["products"]["failed"].append({"name": p_data["name"], "error": str(e)})

    logger.info("Seeding stub products…")
    for sp in STUB_PRODUCTS:
        if sp["name"] in existing_product_by_name:
            product_by_name[sp["name"]] = existing_product_by_name[sp["name"]]
            report["products"]["created"].append(sp["name"] + " (existing)")
            continue
        p_data = {
            "kind": "DataProduct",
            "apiVersion": "v1.0.0",
            "version": "1.0.0",
            "status": "active",
            "name": sp["name"],
            "domain": sp["domain"],
            "owner": sp["owner_team"],
            "tags": [sp["alignment"], "stub"],
            "description": {
                "purpose": f"Stub product for marketplace density — {sp['alignment']} in {sp['domain']}.",
                "usage": "Demo only; not backed by a contract.",
                "limitations": "Synthetic stub for DAIS 2026.",
            },
            "customProperties": [{"property": "alignment", "value": sp["alignment"]}],
        }
        if sp["domain"] in domain_by_name:
            p_data["domain_id"] = domain_by_name[sp["domain"]]
        if sp["owner_team"] in team_by_name:
            p_data["owner_team_id"] = team_by_name[sp["owner_team"]]
        try:
            created = products_mgr.create_product(product_data=p_data, db=db, user=current_user)
            product_by_name[sp["name"]] = str(created.id)
            report["products"]["created"].append(sp["name"])
        except Exception as e:
            logger.warning(f"Stub product '{sp['name']}' failed: {e}")
            report["products"]["failed"].append({"name": sp["name"], "error": str(e)})

    db.flush()

    # ─── Publish to the marketplace ─────────────────────────────────
    # Use the proper manager paths (not direct DB writes):
    #   - publish_product:        full lifecycle, validates output-port contracts
    #   - set_publication_scope:  scope-only path for stubs without contracts
    logger.info("Publishing all 47 products to marketplace (scope=organization)…")
    published = 0
    publish_errors = []
    for name, pid in product_by_name.items():
        try:
            try:
                products_mgr.publish_product(pid, current_user=current_user)
            except Exception as inner:
                # publish_product can fail for stubs (no contracts) or other product
                # config issues. Fall back to the lighter scope-only publish.
                products_mgr.set_publication_scope(pid, "organization", current_user=current_user)
            published += 1
        except Exception as e:
            publish_errors.append(f"{name}: {e}")
    report["publications"] = {"published": published, "errors": publish_errors[:5]}

    # ─── Relationships ──────────────────────────────────────────────
    logger.info("Seeding entity relationships…")
    for comp in COMPOSITIONS:
        parent_id = product_by_name.get(comp["parent"])
        if not parent_id:
            report["relationships"]["errors"].append(f"Parent product not found: {comp['parent']}")
            continue
        for child_name in comp["children"]:
            child_id = product_by_name.get(child_name)
            if not child_id:
                report["relationships"]["errors"].append(f"Child product not found: {child_name}")
                continue
            try:
                er_mgr.create_relationship(
                    db,
                    EntityRelationshipCreate(
                        source_type="DataProduct",
                        source_id=parent_id,
                        target_type="DataProduct",
                        target_id=child_id,
                        relationship_type=comp["kind"],
                    ),
                    current_user_id=current_user,
                )
                report["relationships"]["created"] += 1
            except Exception as e:
                err_str = str(e)
                if "already exists" in err_str.lower() or "409" in err_str:
                    # Idempotent: treat existing relationship as success
                    report["relationships"]["created"] += 1
                else:
                    report["relationships"]["failed"] += 1
                    report["relationships"]["errors"].append(f"{comp['parent']} -[{comp['kind']}]-> {child_name}: {e}")

    db.flush()

    # ─── Subscriptions ──────────────────────────────────────────────
    logger.info("Seeding consumer subscriptions…")
    for s in SUBSCRIPTIONS:
        product_id = product_by_name.get(s["product"])
        if not product_id:
            report["subscriptions"]["errors"].append(f"Product not found: {s['product']}")
            continue
        try:
            sub_mgr.subscribe(
                db,
                EntitySubscriptionCreate(
                    entity_type="DataProduct",
                    entity_id=product_id,
                    subscriber_email=_team_email(s["subscriber_team"]),
                    subscription_reason=f"Demo seeded — {s['subscriber_team']} subscribes to {s['product']}",
                ),
            )
            report["subscriptions"]["created"] += 1
        except Exception as e:
            err_str = str(e)
            if "Already subscribed" in err_str or "409" in err_str:
                # Treat existing subscription as success (idempotent)
                report["subscriptions"]["created"] += 1
            else:
                report["subscriptions"]["failed"] += 1
                report["subscriptions"]["errors"].append(f"{s['subscriber_team']} → {s['product']}: {e}")

    # ─── Compliance policy: contracts must be actively enforced ──
    # Meta-quality: surface which contracts in the mesh are receiving recent
    # QualityItems (from any pipeline / any tool — dqx, dbt, GE, etc.). This
    # is the "watching the watchers" beat that completes the federated story:
    # Ontos doesn't enforce; it observes whether enforcement is happening.
    try:
        from src.controller.compliance_manager import ComplianceManager
        from src.models.compliance import CompliancePolicy
        from src.db_models.compliance import CompliancePolicyDb
        from uuid import uuid4
        compliance_mgr = ComplianceManager()
        policy_name = "active-contracts-have-recent-quality"
        existing_policy = (
            db.query(CompliancePolicyDb)
            .filter(CompliancePolicyDb.name == policy_name)
            .first()
        )
        if existing_policy is None:
            policy = CompliancePolicy(
                id=uuid4(),
                name=policy_name,
                description=(
                    "Every active data contract must have a recent quality measurement "
                    "(within the last 24h) from at least one enforcement pipeline. The "
                    "measurement may come from any source — dqx, dbt, great_expectations, "
                    "soda, etc. — because Ontos is platform-agnostic for quality."
                ),
                failure_message="No quality measurement has been received for this contract in the last 24 hours.",
                rule=(
                    # The DSL parses 'true'/'false' as string identifiers, not
                    # booleans — use a bare ASSERT on the property; the result is
                    # bool-coerced by the policy runner.
                    "MATCH (c:data_contract) "
                    "WHERE c.status = 'active' "
                    "ASSERT c.has_recent_quality_metric"
                ),
                compliance=0.0,
                category="quality",
                severity="medium",
                is_active=True,
            )
            compliance_mgr.create_policy(db, policy=policy, current_user=current_user)
            report["compliance_policies"] = {"created": [policy_name]}
            logger.info("Seeded compliance policy: %s", policy_name)
        else:
            report["compliance_policies"] = {"existing": [policy_name]}
    except Exception as e:
        logger.warning("Failed to seed compliance policy: %s", e, exc_info=True)
        report["compliance_policies"] = {"failed": [str(e)]}

    # Final commit
    db.commit()

    logger.info(
        "Aviation demo seed complete: domains created=%d/existing=%d, teams created=%d/existing=%d, contracts created=%d/failed=%d, products created=%d/failed=%d, relationships created=%d/failed=%d, subscriptions created=%d/failed=%d",
        len(report["domains"]["created"]), len(report["domains"]["existing"]),
        len(report["teams"]["created"]), len(report["teams"]["existing"]),
        len(report["contracts"]["created"]), len(report["contracts"]["failed"]),
        len(report["products"]["created"]), len(report["products"]["failed"]),
        report["relationships"]["created"], report["relationships"]["failed"],
        report["subscriptions"]["created"], report["subscriptions"]["failed"],
    )

    return report
