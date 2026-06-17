from __future__ import annotations
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from sqlalchemy.orm import Session

from src.common.logging import get_logger
from src.repositories.quality_repository import quality_items_repo, QualityItemsRepository
from src.models.quality import QualityItem, QualityItemCreate, QualityItemUpdate, QualitySummary
from src.repositories.change_log_repository import change_log_repo
from src.db_models.change_log import ChangeLogDb

if TYPE_CHECKING:
    from src.controller.data_products_manager import DataProductsManager
    from src.controller.notifications_manager import NotificationsManager
    from src.controller.entity_subscriptions_manager import EntitySubscriptionsManager

logger = get_logger(__name__)


class QualityManager:
    def __init__(
        self,
        repository: QualityItemsRepository = quality_items_repo,
        *,
        notifications_manager: Optional["NotificationsManager"] = None,
        entity_subscriptions_manager: Optional["EntitySubscriptionsManager"] = None,
        data_products_manager: Optional["DataProductsManager"] = None,
    ):
        self._repo = repository
        # Collaborators for the "trust loop": when a quality run records a
        # failure against a contract, notify the contract owner + every
        # subscriber of products built on that contract. All optional so the
        # plain CRUD paths (and most tests) don't need to wire them.
        self._notifications_manager = notifications_manager
        self._entity_subscriptions_manager = entity_subscriptions_manager
        self._data_products_manager = data_products_manager

    # ── helpers ──────────────────────────────────────────────────────────

    def _log_change(self, db: Session, *, entity_type: str, entity_id: str, action: str, username: Optional[str]) -> None:
        entry = ChangeLogDb(
            entity_type=f"{entity_type}:quality_item",
            entity_id=entity_id,
            action=action,
            username=username,
        )
        db.add(entry)
        db.commit()

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, db: Session, *, data: QualityItemCreate, user_email: Optional[str]) -> QualityItem:
        obj = self._repo.create(db, obj_in=data)
        db.commit()
        db.refresh(obj)
        self._log_change(db, entity_type=data.entity_type, entity_id=data.entity_id, action="CREATE", username=user_email)
        item = QualityItem.model_validate(obj, from_attributes=True)
        # Trust loop: a failing quality result fans out a notification to the
        # contract owner + every subscriber. Never let a notification problem
        # break the (already-committed) quality ingestion.
        try:
            self.notify_quality_failure(db, item=item)
        except Exception:
            logger.exception("Quality-failure notification fan-out failed for %s/%s", item.entity_type, item.entity_id)
        return item

    # ── trust loop: failure → notify owner + subscribers ─────────────────

    @staticmethod
    def _is_failure(item: QualityItem) -> bool:
        """A quality result counts as a failure when at least one check failed
        (or rows were quarantined). When the run reports per-check counts we use
        those; otherwise we fall back to a sub-100% score."""
        if item.checks_total is not None and item.checks_passed is not None:
            return item.checks_passed < item.checks_total
        return item.score_percent < 100.0

    @staticmethod
    def _failed_check_count(item: QualityItem) -> Optional[int]:
        if item.checks_total is not None and item.checks_passed is not None:
            return max(item.checks_total - item.checks_passed, 0)
        return None

    def resolve_failure_recipients(self, db: Session, *, contract_id: str) -> List[str]:
        """Recipients for a contract quality failure: the contract owner plus
        every subscriber of any data product whose output port uses the
        contract (product → output-port → contract traversal via
        DataProductsManager.get_products_by_contract). De-duplicated, owner
        first. Returns [] if collaborators aren't wired."""
        recipients: List[str] = []
        seen: Set[str] = set()

        def _add(email: Optional[str]) -> None:
            if email and email not in seen:
                seen.add(email)
                recipients.append(email)

        _add(self._contract_owner_email(db, contract_id=contract_id))

        if self._data_products_manager and self._entity_subscriptions_manager:
            try:
                products = self._data_products_manager.get_products_by_contract(contract_id)
            except Exception:
                logger.exception("Failed resolving products for contract %s", contract_id)
                products = []
            for product in products:
                pid = getattr(product, "id", None)
                if not pid:
                    continue
                try:
                    summary = self._entity_subscriptions_manager.get_subscribers(
                        db, entity_type="DataProduct", entity_id=str(pid)
                    )
                except Exception:
                    logger.exception("Failed resolving subscribers for product %s", pid)
                    continue
                for sub in summary.subscribers:
                    _add(sub.subscriber_email)

        return recipients

    def _contract_owner_email(self, db: Session, *, contract_id: str) -> Optional[str]:
        """Owner email from the contract's ODCS team members (role == 'owner').
        Falls back to the first team member if no explicit owner role exists."""
        try:
            from src.db_models.data_contracts import DataContractTeamDb
            members = (
                db.query(DataContractTeamDb)
                .filter(DataContractTeamDb.contract_id == contract_id)
                .all()
            )
        except Exception:
            logger.exception("Failed loading team for contract %s", contract_id)
            return None
        if not members:
            return None
        owner = next((m for m in members if (m.role or "").lower() == "owner"), None)
        chosen = owner or members[0]
        return chosen.username

    def _contract_name(self, db: Session, *, contract_id: str) -> str:
        try:
            from src.db_models.data_contracts import DataContractDb
            row = db.query(DataContractDb).filter(DataContractDb.id == contract_id).first()
            if row and row.name:
                return row.name
        except Exception:
            logger.exception("Failed loading contract name for %s", contract_id)
        return contract_id

    def notify_quality_failure(self, db: Session, *, item: QualityItem) -> int:
        """Fan a contract-level quality failure out to owner + subscribers.

        Returns the number of notifications created. No-op (returns 0) when:
        the item isn't a contract, isn't a failure, or NotificationsManager
        isn't wired."""
        if item.entity_type != "data_contract":
            return 0
        if not self._is_failure(item):
            return 0
        if self._notifications_manager is None:
            logger.debug("NotificationsManager not wired; skipping quality-failure fan-out")
            return 0

        contract_id = item.entity_id
        recipients = self.resolve_failure_recipients(db, contract_id=contract_id)
        if not recipients:
            logger.info("No recipients resolved for quality failure on contract %s", contract_id)
            return 0

        contract_name = self._contract_name(db, contract_id=contract_id)
        rule_name = item.title or item.dimension
        failed = self._failed_check_count(item)
        if failed is not None:
            rule_summary = f"{failed} rule(s) failed ({rule_name})"
        else:
            rule_summary = f"{rule_name} scored {item.score_percent:.0f}%"
        link = f"/data-contracts/{contract_id}"
        description = (
            f"Quality enforcement ({item.source}) recorded a failure on contract "
            f"'{contract_name}': {rule_summary}. Review the contract and downstream impact."
        )

        from src.controller.notifications_manager import NotificationsManager  # noqa: F401
        from src.models.notifications import Notification, NotificationType
        import uuid
        from datetime import datetime

        created = 0
        for recipient in recipients:
            try:
                notification = Notification(
                    id=str(uuid.uuid4()),
                    type=NotificationType.WARNING,
                    title=f"Quality failure: {contract_name}",
                    subtitle=rule_summary,
                    description=description,
                    link=link,
                    recipient=recipient,
                    created_at=datetime.utcnow(),
                    read=False,
                    can_delete=True,
                )
                self._notifications_manager.create_notification(notification, db)
                created += 1
            except Exception:
                logger.exception("Failed creating quality-failure notification for %s", recipient)
        db.commit()
        logger.info(
            "Quality-failure trust loop: contract=%s recipients=%d notifications=%d",
            contract_id, len(recipients), created,
        )
        return created

    def list(self, db: Session, *, entity_type: str, entity_id: str, limit: Optional[int] = None) -> List[QualityItem]:
        rows = self._repo.list_for_entity(db, entity_type=entity_type, entity_id=entity_id, limit=limit)
        return [QualityItem.model_validate(r, from_attributes=True) for r in rows]

    def update(self, db: Session, *, id: str, data: QualityItemUpdate, user_email: Optional[str]) -> Optional[QualityItem]:
        db_obj = self._repo.get(db, id=id)
        if not db_obj:
            return None
        updated = self._repo.update(db, db_obj=db_obj, obj_in=data)
        db.commit()
        db.refresh(updated)
        self._log_change(db, entity_type=updated.entity_type, entity_id=updated.entity_id, action="UPDATE", username=user_email)
        return QualityItem.model_validate(updated, from_attributes=True)

    def delete(self, db: Session, *, id: str, user_email: Optional[str]) -> bool:
        db_obj = self._repo.get(db, id=id)
        if not db_obj:
            return False
        entity_type, entity_id = db_obj.entity_type, db_obj.entity_id
        removed = self._repo.remove(db, id=id)
        if removed:
            db.commit()
            self._log_change(db, entity_type=entity_type, entity_id=entity_id, action="DELETE", username=user_email)
            return True
        return False

    # ── summaries ────────────────────────────────────────────────────────

    def summarize(self, db: Session, *, entity_type: str, entity_id: str) -> QualitySummary:
        overall, count, by_dim, by_src, latest_ts = self._repo.summarize_for_entity(
            db, entity_type=entity_type, entity_id=entity_id
        )
        return QualitySummary(
            overall_score_percent=overall,
            items_count=count,
            by_dimension=by_dim,
            by_source=by_src,
            measured_at=latest_ts,
        )

    def aggregate_for_product(
        self,
        db: Session,
        *,
        product_id: str,
        data_products_manager: "DataProductsManager",
    ) -> QualitySummary:
        """Roll up quality from direct product items + child contract items."""
        contract_ids = data_products_manager.get_contracts_for_product(product_id)

        # Gather all relevant quality items
        direct_items = self._repo.list_for_entity(db, entity_type="data_product", entity_id=product_id)
        child_items = self._repo.list_for_entities(db, entity_type="data_contract", entity_ids=contract_ids) if contract_ids else []
        all_items = direct_items + child_items

        if not all_items:
            return QualitySummary(overall_score_percent=0.0, items_count=0, by_dimension={}, by_source={}, measured_at=None)

        # Deduplicate: keep latest per (entity_type, entity_id, dimension)
        latest_map: Dict[tuple, object] = {}
        for item in all_items:
            key = (item.entity_type, item.entity_id, item.dimension)
            existing = latest_map.get(key)
            if existing is None or item.measured_at > existing.measured_at:
                latest_map[key] = item

        latest = list(latest_map.values())

        by_dimension: Dict[str, float] = {}
        dim_counts: Dict[str, int] = {}
        by_source: Dict[str, float] = {}
        source_counts: Dict[str, int] = {}
        latest_ts = None

        for item in latest:
            by_dimension[item.dimension] = by_dimension.get(item.dimension, 0.0) + item.score_percent
            dim_counts[item.dimension] = dim_counts.get(item.dimension, 0) + 1
            by_source[item.source] = by_source.get(item.source, 0.0) + item.score_percent
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
            if latest_ts is None or item.measured_at > latest_ts:
                latest_ts = item.measured_at

        for dim in by_dimension:
            by_dimension[dim] = round(by_dimension[dim] / dim_counts[dim], 2)
        for src in by_source:
            by_source[src] = round(by_source[src] / source_counts[src], 2)

        overall = round(sum(by_dimension.values()) / len(by_dimension), 2)

        return QualitySummary(
            overall_score_percent=overall,
            items_count=len(all_items),
            by_dimension=by_dimension,
            by_source=by_source,
            measured_at=latest_ts,
        )
