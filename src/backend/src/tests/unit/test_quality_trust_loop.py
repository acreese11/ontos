"""Unit/integration tests for the quality-failure "trust loop".

When a DQX/quality run records a failure against a data contract,
``QualityManager`` fans a notification out to:
  * the contract **owner** (ODCS team member with role == "owner"), and
  * every **subscriber** of any data product whose output port uses that
    contract (product → output-port → contract traversal).

Notifications go through the existing ``NotificationsManager`` —
no new notification system. These tests exercise three things:

  1. A failing contract quality item triggers one notification per
     (owner + each subscriber).
  2. A passing quality item triggers nothing.
  3. ``resolve_failure_recipients`` returns owner + subscribers, deduped.

The collaborators (NotificationsManager, EntitySubscriptionsManager,
DataProductsManager) are real instances bound to the test DB session;
only SettingsManager (unused by ``create_notification``) is mocked.
"""
# Set test environment variables BEFORE any app imports
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.controller.quality_manager import QualityManager
from src.controller.entity_subscriptions_manager import EntitySubscriptionsManager
from src.controller.notifications_manager import NotificationsManager
from src.controller.data_products_manager import DataProductsManager
from src.db_models.data_contracts import DataContractDb, DataContractTeamDb
from src.db_models.data_products import DataProductDb, OutputPortDb
from src.db_models.notifications import NotificationDb
from src.models.entity_subscriptions import EntitySubscriptionCreate
from src.models.quality import QualityItemCreate


OWNER_EMAIL = "ops-lead@safe-skies.demo"
SUBSCRIBER_A = "consumer-a@safe-skies.demo"
SUBSCRIBER_B = "consumer-b@safe-skies.demo"


def _seed_contract_with_owner(db, *, name="global_flight_ops"):
    contract = DataContractDb(name=name, version="1.0.0", status="active")
    db.add(contract)
    db.flush()
    # ODCS team members: an owner + a steward (only owner should be notified).
    db.add(DataContractTeamDb(contract_id=contract.id, name="ops-lead", username=OWNER_EMAIL, role="owner"))
    db.add(DataContractTeamDb(contract_id=contract.id, name="ops-steward", username="steward@safe-skies.demo", role="data-steward"))
    db.flush()
    return contract


def _seed_product_on_contract(db, contract_id, *, name="Global Flight Ops"):
    product = DataProductDb(id=str(uuid4()), status="active", name=name, version="1.0.0")
    db.add(product)
    db.flush()
    db.add(OutputPortDb(product_id=product.id, name="current", version="1.0.0", contract_id=contract_id))
    db.flush()
    return product


def _make_manager(db):
    """QualityManager wired with real collaborators bound to the test session."""
    notifications_manager = NotificationsManager(settings_manager=MagicMock())
    subscriptions_manager = EntitySubscriptionsManager()
    dp_manager = DataProductsManager(db=db)
    return QualityManager(
        notifications_manager=notifications_manager,
        entity_subscriptions_manager=subscriptions_manager,
        data_products_manager=dp_manager,
    )


def _failing_item(contract_id):
    return QualityItemCreate(
        entity_id=contract_id,
        entity_type="data_contract",
        title="not_null_check",
        dimension="completeness",
        source="dqx",
        score_percent=80.0,
        checks_passed=4,
        checks_total=5,
    )


def _passing_item(contract_id):
    return QualityItemCreate(
        entity_id=contract_id,
        entity_type="data_contract",
        title="not_null_check",
        dimension="completeness",
        source="dqx",
        score_percent=100.0,
        checks_passed=5,
        checks_total=5,
    )


def _score_only_failing_item(contract_id):
    """A count-less DQX run: no checks_passed/total, just a sub-100 score.
    Exercises the score-fallback branch of _is_failure + the 'scored N%' summary."""
    return QualityItemCreate(
        entity_id=contract_id,
        entity_type="data_contract",
        title="not_null_check",
        dimension="completeness",
        source="dqx",
        score_percent=75.0,
        checks_passed=None,
        checks_total=None,
    )


def _notifications_for(db, recipient):
    return db.query(NotificationDb).filter(NotificationDb.recipient == recipient).all()


# =========================================================================
# 1. Failure → owner + every subscriber notified
# =========================================================================

class TestFailureTriggersNotifications:
    def test_failure_notifies_owner_and_each_subscriber(self, db_session):
        contract = _seed_contract_with_owner(db_session)
        product = _seed_product_on_contract(db_session, contract.id)
        sub_mgr = EntitySubscriptionsManager()
        for email in (SUBSCRIBER_A, SUBSCRIBER_B):
            sub_mgr.subscribe(
                db_session,
                EntitySubscriptionCreate(
                    entity_type="DataProduct", entity_id=product.id, subscriber_email=email,
                ),
            )
        db_session.flush()

        mgr = _make_manager(db_session)
        mgr.create(db_session, data=_failing_item(contract.id), user_email="dqx@pipeline")

        # Owner + both subscribers each get exactly one notification.
        for email in (OWNER_EMAIL, SUBSCRIBER_A, SUBSCRIBER_B):
            notes = _notifications_for(db_session, email)
            assert len(notes) == 1, f"expected 1 notification for {email}, got {len(notes)}"
            n = notes[0]
            assert n.type == "warning"
            assert n.link == f"/data-contracts/{contract.id}"
            # Payload carries the contract name + the failed rule summary.
            assert "global_flight_ops" in (n.title or "")
            assert "1 rule(s) failed" in (n.subtitle or "")

        # The steward (non-owner team member) is NOT notified.
        assert _notifications_for(db_session, "steward@safe-skies.demo") == []

    def test_failure_with_no_subscribers_still_notifies_owner(self, db_session):
        contract = _seed_contract_with_owner(db_session, name="lonely_contract")
        _seed_product_on_contract(db_session, contract.id, name="Lonely Product")
        db_session.flush()

        mgr = _make_manager(db_session)
        mgr.create(db_session, data=_failing_item(contract.id), user_email="dqx@pipeline")
        assert len(_notifications_for(db_session, OWNER_EMAIL)) == 1

    def test_score_only_failure_notifies_with_score_summary(self, db_session):
        """A count-less run (score < 100, no check counts) still notifies, and the
        subtitle uses the 'scored N%' wording — the _is_failure score fallback."""
        contract = _seed_contract_with_owner(db_session, name="score_only_contract")
        db_session.flush()
        mgr = _make_manager(db_session)
        mgr.create(db_session, data=_score_only_failing_item(contract.id), user_email="dqx@pipeline")
        notes = _notifications_for(db_session, OWNER_EMAIL)
        assert len(notes) == 1
        assert "scored 75%" in (notes[0].subtitle or "")


# =========================================================================
# 2. No failure → no notification
# =========================================================================

class TestPassingDoesNotNotify:
    def test_passing_item_creates_no_notifications(self, db_session):
        contract = _seed_contract_with_owner(db_session)
        product = _seed_product_on_contract(db_session, contract.id)
        EntitySubscriptionsManager().subscribe(
            db_session,
            EntitySubscriptionCreate(
                entity_type="DataProduct", entity_id=product.id, subscriber_email=SUBSCRIBER_A,
            ),
        )
        db_session.flush()

        mgr = _make_manager(db_session)
        mgr.create(db_session, data=_passing_item(contract.id), user_email="dqx@pipeline")

        assert _notifications_for(db_session, OWNER_EMAIL) == []
        assert _notifications_for(db_session, SUBSCRIBER_A) == []

    def test_non_contract_entity_never_notifies(self, db_session):
        """A failing quality item on a data_product (not a contract) must not
        trigger the contract trust loop."""
        mgr = _make_manager(db_session)
        item = QualityItemCreate(
            entity_id=str(uuid4()),
            entity_type="data_product",
            title="row_count",
            dimension="completeness",
            source="dqx",
            score_percent=10.0,
            checks_passed=1,
            checks_total=10,
        )
        mgr.create(db_session, data=item, user_email="dqx@pipeline")
        # No notifications at all.
        assert db_session.query(NotificationDb).count() == 0


# =========================================================================
# 3. Recipient resolution
# =========================================================================

class TestNotificationFailureIsSwallowed:
    def test_notify_error_does_not_break_create(self, db_session):
        """If the fan-out raises, create() still succeeds (the quality row was
        already committed) and no exception propagates to the ingestion caller."""
        contract = _seed_contract_with_owner(db_session, name="resilient_contract")
        db_session.flush()
        mgr = _make_manager(db_session)
        mgr.notify_quality_failure = MagicMock(side_effect=RuntimeError("notify boom"))
        # Must not raise — ingestion is protected from notification errors.
        result = mgr.create(db_session, data=_failing_item(contract.id), user_email="dqx@pipeline")
        assert result is not None
        mgr.notify_quality_failure.assert_called_once()
        # The fan-out blew up before creating anything.
        assert db_session.query(NotificationDb).count() == 0


class TestRecipientResolution:
    def test_resolve_returns_owner_first_then_subscribers_deduped(self, db_session):
        contract = _seed_contract_with_owner(db_session)
        product = _seed_product_on_contract(db_session, contract.id)
        sub_mgr = EntitySubscriptionsManager()
        # Subscribe two distinct consumers; SUBSCRIBER_A twice would conflict,
        # so use distinct emails — dedup is across owner/subscriber overlap.
        for email in (SUBSCRIBER_A, SUBSCRIBER_B):
            sub_mgr.subscribe(
                db_session,
                EntitySubscriptionCreate(
                    entity_type="DataProduct", entity_id=product.id, subscriber_email=email,
                ),
            )
        db_session.flush()

        mgr = _make_manager(db_session)
        recipients = mgr.resolve_failure_recipients(db_session, contract_id=contract.id)

        assert recipients[0] == OWNER_EMAIL
        assert set(recipients) == {OWNER_EMAIL, SUBSCRIBER_A, SUBSCRIBER_B}
        # No duplicates.
        assert len(recipients) == len(set(recipients))

    def test_owner_who_is_also_subscriber_appears_once(self, db_session):
        contract = _seed_contract_with_owner(db_session)
        product = _seed_product_on_contract(db_session, contract.id)
        # Owner also subscribes to the product → must be deduped.
        EntitySubscriptionsManager().subscribe(
            db_session,
            EntitySubscriptionCreate(
                entity_type="DataProduct", entity_id=product.id, subscriber_email=OWNER_EMAIL,
            ),
        )
        db_session.flush()

        mgr = _make_manager(db_session)
        recipients = mgr.resolve_failure_recipients(db_session, contract_id=contract.id)
        assert recipients.count(OWNER_EMAIL) == 1
        assert recipients == [OWNER_EMAIL]
