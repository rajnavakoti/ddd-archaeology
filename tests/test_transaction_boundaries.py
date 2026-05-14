"""Tests for Exhibit C: Transaction Boundary Analysis."""

import json
from pathlib import Path

from ddd_archaeology.phases.transaction_boundaries import analyze_transactions


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "database"


def _load_clusters():
    return json.loads((EXAMPLES_DIR / "transaction_clusters.json").read_text())


def test_classifies_clean_aggregate():
    result = analyze_transactions(_load_clusters())
    order_agg = next(
        (c for c in result.clusters if "orders" in c.tables and "order_lines" in c.tables and "order_audit" in c.tables),
        None,
    )
    assert order_agg is not None
    assert order_agg.classification == "clean_aggregate"


def test_classifies_cross_context():
    result = analyze_transactions(_load_clusters())
    cross = next(
        (c for c in result.clusters if set(c.tables) == {"orders", "shipments"}),
        None,
    )
    assert cross is not None
    assert cross.classification in ("cross_context", "distributed_concern")


def test_classifies_orm_artifact():
    result = analyze_transactions(_load_clusters())
    orm = next(
        (c for c in result.clusters if c.occurrence_count < 100),
        None,
    )
    assert orm is not None
    assert orm.classification == "orm_artifact"


def test_identifies_root_table():
    result = analyze_transactions(_load_clusters())
    order_agg = next(
        (c for c in result.clusters if "orders" in c.tables and "order_lines" in c.tables and "order_audit" in c.tables),
        None,
    )
    assert order_agg is not None
    assert order_agg.root_table == "orders"


def test_identifies_shipment_aggregate():
    result = analyze_transactions(_load_clusters())
    ship_agg = next(
        (c for c in result.clusters if set(c.tables) == {"shipments", "tracking_events"}),
        None,
    )
    assert ship_agg is not None
    assert ship_agg.classification == "clean_aggregate"
    assert ship_agg.root_table == "shipments"


def test_builds_aggregate_candidates():
    result = analyze_transactions(_load_clusters())
    assert len(result.aggregates) >= 3
    roots = {a.root for a in result.aggregates}
    assert "orders" in roots
    assert "shipments" in roots


def test_extraction_readiness_generated():
    result = analyze_transactions(_load_clusters())
    assert len(result.extraction_readiness) >= 2
    services = {er.service for er in result.extraction_readiness}
    assert "Shipment Service" in services


def test_shipment_service_not_ready():
    """Shipment Service has cross-context writes — should not be 'ready'."""
    result = analyze_transactions(_load_clusters())
    shipment = next(er for er in result.extraction_readiness if er.service == "Shipment Service")
    assert shipment.status != "ready"
    assert shipment.cross_context_clusters > 0


def test_carrier_service_clean():
    result = analyze_transactions(_load_clusters())
    carrier = next(
        (er for er in result.extraction_readiness if er.service == "Carrier Integration Service"),
        None,
    )
    assert carrier is not None
    assert carrier.status == "ready"


def test_slow_transaction_detected():
    result = analyze_transactions(_load_clusters())
    slow = [c for c in result.clusters if c.avg_duration_ms > 200]
    assert len(slow) >= 1
