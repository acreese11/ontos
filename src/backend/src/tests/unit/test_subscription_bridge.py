"""The Subscribe button must reach the trust loop's recipient set.

Bug: the data-product Subscribe button wrote only `data_product_subscriptions`, but the
quality/drift trust loop resolves recipients from `entity_subscriptions`
(`QualityManager.resolve_failure_recipients` → `get_subscribers(entity_type="DataProduct")`).
The two tables were unbridged, so UI subscribers were never notified. `subscribe()` now
mirrors the subscription into `entity_subscriptions`; these tests pin that bridge.
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from uuid import uuid4

from src.controller.data_products_manager import DataProductsManager
from src.controller.entity_subscriptions_manager import EntitySubscriptionsManager


def _trust_loop_subscribers(db, product_id):
    """Emails the trust loop would resolve for this product (reads entity_subscriptions)."""
    summary = EntitySubscriptionsManager().get_subscribers(db, entity_type="DataProduct", entity_id=product_id)
    return [s.subscriber_email for s in summary.subscribers]


class TestSubscriptionBridge:
    def test_ensure_puts_subscriber_where_trust_loop_reads(self, db_session):
        mgr = DataProductsManager(db=db_session)
        pid, email = str(uuid4()), "consumer@safe-skies.demo"
        assert email not in _trust_loop_subscribers(db_session, pid)
        mgr._ensure_entity_subscription(db_session, product_id=pid, subscriber_email=email)
        db_session.flush()
        assert email in _trust_loop_subscribers(db_session, pid)  # now reachable by the trust loop

    def test_ensure_is_idempotent(self, db_session):
        mgr = DataProductsManager(db=db_session)
        pid, email = str(uuid4()), "c@x.demo"
        mgr._ensure_entity_subscription(db_session, product_id=pid, subscriber_email=email)
        mgr._ensure_entity_subscription(db_session, product_id=pid, subscriber_email=email)  # no raise, no dup
        db_session.flush()
        assert _trust_loop_subscribers(db_session, pid).count(email) == 1

    def test_remove_unbridges(self, db_session):
        mgr = DataProductsManager(db=db_session)
        pid, email = str(uuid4()), "c2@x.demo"
        mgr._ensure_entity_subscription(db_session, product_id=pid, subscriber_email=email)
        db_session.flush()
        assert email in _trust_loop_subscribers(db_session, pid)
        mgr._remove_entity_subscription(db_session, product_id=pid, subscriber_email=email)
        db_session.flush()
        assert email not in _trust_loop_subscribers(db_session, pid)

    def test_remove_when_absent_is_noop(self, db_session):
        mgr = DataProductsManager(db=db_session)
        # must not raise even when nothing was bridged
        mgr._remove_entity_subscription(db_session, product_id=str(uuid4()), subscriber_email="nope@x.demo")
