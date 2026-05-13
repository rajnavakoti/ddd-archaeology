"""Tests for Exhibit B: Schema Archaeology."""

import json
from pathlib import Path

from ddd_archaeology.phases.schema_archaeology import analyze_schema, analyze_ddl


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "database"


def _load_test_data():
    access_log = json.loads((EXAMPLES_DIR / "access_log.json").read_text())
    service_users = json.loads((EXAMPLES_DIR / "service_users.json").read_text())
    return access_log, service_users


def test_finds_shared_tables():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    assert len(result.shared_tables) > 0


def test_orders_is_shared():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    orders = next((t for t in result.shared_tables if t.table == "orders"), None)
    assert orders is not None
    assert orders.service_count >= 4


def test_inventory_reserved_has_two_writers():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    inv = next((t for t in result.shared_tables if t.table == "inventory_reserved"), None)
    assert inv is not None
    assert len(inv.writers) == 2
    assert inv.classification == "multi_writer"
    assert inv.severity == "critical"


def test_customer_addresses_read_by_multiple():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    addr = next((t for t in result.shared_tables if t.table == "customer_addresses"), None)
    assert addr is not None
    assert len(addr.readers) >= 2


def test_shipment_status_shared():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    ss = next((t for t in result.shared_tables if t.table == "shipment_status"), None)
    assert ss is not None
    assert "Carrier Integration Service" in ss.writers


def test_payment_ledger_clean_boundary():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    pl = next((t for t in result.shared_tables if t.table == "payment_ledger"), None)
    assert pl is not None
    assert pl.classification == "single_writer_multi_reader"
    assert len(pl.writers) == 1


def test_ghost_users_detected():
    access_log, service_users = _load_test_data()
    result = analyze_schema(access_log, service_users)
    assert len(result.ghost_users) == 2
    assert "svc_etl_legacy" in result.ghost_users
    assert "svc_vendor_sync" in result.ghost_users


def test_ddl_finds_fat_table():
    ddl = (EXAMPLES_DIR / "schema.sql").read_text()
    signals = analyze_ddl(ddl)
    fat = [s for s in signals if s.signal_type == "fat_table"]
    assert len(fat) >= 1
    assert any("orders" in s.table for s in fat)


def test_ddl_finds_lifecycle_timestamps():
    ddl = (EXAMPLES_DIR / "schema.sql").read_text()
    signals = analyze_ddl(ddl)
    lifecycle = [s for s in signals if s.signal_type == "lifecycle_timestamps"]
    assert len(lifecycle) >= 1
    assert any("orders" in s.table for s in lifecycle)


def test_ddl_finds_cross_boundary_fks():
    ddl = (EXAMPLES_DIR / "schema.sql").read_text()
    signals = analyze_ddl(ddl)
    cross_fk = [s for s in signals if s.signal_type == "cross_boundary_fk"]
    assert len(cross_fk) >= 3  # orders.buyer_id, orders.warehouse_id, etc.


def test_ddl_finds_index_fossils():
    ddl = (EXAMPLES_DIR / "schema.sql").read_text()
    signals = analyze_ddl(ddl)
    fossils = [s for s in signals if s.signal_type == "index_fossil"]
    assert len(fossils) >= 1
    assert any("orders" in s.table for s in fossils)
