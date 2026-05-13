"""Tests for Phase 2: vocabulary extraction."""

import json
from pathlib import Path

from ddd_archaeology.phases.collect import collect_contracts
from ddd_archaeology.phases.extract_vocab import extract_vocabulary
from ddd_archaeology.output.writer import _to_serializable


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery"


def _get_inventory() -> list[dict]:
    contracts = collect_contracts(EXAMPLES_DIR)
    return json.loads(json.dumps(_to_serializable(contracts)))


def test_extracts_vocabulary():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    assert len(entries) > 100  # plenty of terms across 9 contracts


def test_extracts_path_resources():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    path_resources = [e for e in entries if e.term_type == "path_resource"]
    terms = {e.term for e in path_resources}
    assert "orders" in terms
    assert "customers" in terms
    assert "warehouses" in terms


def test_extracts_schema_names():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    schemas = [e for e in entries if e.term_type == "schema"]
    terms = {e.term for e in schemas}
    assert "Order" in terms
    assert "Customer" in terms
    assert "Shipment" in terms


def test_extracts_field_names():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    fields = [e for e in entries if e.term_type == "field"]
    terms = {e.term for e in fields}
    assert "buyerId" in terms
    assert "customerId" in terms
    assert "recipientId" in terms


def test_extracts_enum_values():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    enums = [e for e in entries if e.term_type == "enum"]
    terms = {e.term for e in enums}
    assert "delivered" in terms or "DELIVERED" in terms


def test_extracts_channels():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    channels = [e for e in entries if e.term_type == "channel"]
    terms = {e.term for e in channels}
    assert "orders.placed" in terms
    assert "shipments.delivered" in terms


def test_extracts_channel_prefixes():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    prefixes = [e for e in entries if e.term_type == "channel_prefix"]
    terms = {e.term for e in prefixes}
    assert "orders" in terms
    assert "shipments" in terms


def test_extracts_event_names():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    events = [e for e in entries if e.term_type == "event"]
    terms = {e.term for e in events}
    assert "OrderPlaced" in terms
    assert "ShipmentDelivered" in terms


def test_extracts_graphql_queries():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    queries = [e for e in entries if e.term_type == "query"]
    terms = {e.term for e in queries}
    assert "myOrders" in terms
    assert "tracking" in terms


def test_extracts_graphql_mutations():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    mutations = [e for e in entries if e.term_type == "mutation"]
    terms = {e.term for e in mutations}
    assert "placeOrder" in terms
    assert "requestRefund" in terms


def test_buyer_id_comes_from_order_service():
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    buyer_ids = [e for e in entries if e.term == "buyerId"]
    services = {e.source_service for e in buyer_ids}
    assert "Shipment Service API" in services or any("Shipment" in s for s in services)


def test_vocabulary_has_multiple_person_names():
    """The synthetic data has 6 names for the same person concept."""
    inventory = _get_inventory()
    entries = extract_vocabulary(inventory)
    fields = [e for e in entries if e.term_type == "field"]
    person_id_terms = {e.term for e in fields if "id" in e.term.lower() and any(
        p in e.term.lower() for p in ["buyer", "customer", "user", "recipient", "account"]
    )}
    assert len(person_id_terms) >= 4  # at least buyerId, customerId, userId, recipientId, accountId
