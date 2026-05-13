"""Tests for Phase 3: entity discovery."""

import json
from pathlib import Path

from ddd_archaeology.models import EntityType
from ddd_archaeology.phases.collect import collect_contracts
from ddd_archaeology.phases.discover_entities import discover_entities
from ddd_archaeology.output.writer import _to_serializable


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "ecommerce"


def _get_inventory() -> list[dict]:
    contracts = collect_contracts(EXAMPLES_DIR)
    return json.loads(json.dumps(_to_serializable(contracts)))


def test_discovers_entities():
    entities = discover_entities(_get_inventory())
    assert len(entities) > 20


def test_finds_order_as_aggregate_root():
    entities = discover_entities(_get_inventory())
    orders = [e for e in entities if e.name == "Order" and "Order Service" in e.owning_service]
    assert len(orders) == 1
    assert orders[0].entity_type == EntityType.AGGREGATE_ROOT


def test_finds_address_in_multiple_services():
    entities = discover_entities(_get_inventory())
    address_entities = [e for e in entities if "address" in e.name.lower()]
    services = {e.owning_service for e in address_entities}
    assert len(services) >= 3  # Address-like schemas in Order, Customer, Shipping, Billing


def test_finds_domain_events():
    entities = discover_entities(_get_inventory())
    events = [e for e in entities if e.entity_type == EntityType.DOMAIN_EVENT]
    event_names = {e.name for e in events}
    assert "OrderPlaced" in event_names
    assert "ShipmentDelivered" in event_names


def test_entities_with_properties_have_fields():
    entities = discover_entities(_get_inventory())
    # Enum schemas (like PaymentMethod, OrderStatus) have no fields — that's expected
    entities_with_fields = [e for e in entities if len(e.fields) > 0]
    assert len(entities_with_fields) > 20


def test_cross_references_populated():
    entities = discover_entities(_get_inventory())
    # Order appears in multiple services (Order Service + GraphQL Storefront at minimum)
    order_entities = [e for e in entities if e.name == "Order"]
    assert len(order_entities) >= 2  # at least Order Service and GraphQL


def test_graphql_entities_discovered():
    entities = discover_entities(_get_inventory())
    gql_entities = [e for e in entities if "Storefront" in e.owning_service]
    assert len(gql_entities) > 5
    # GraphQL types with 'id' should be classified as Entity
    entity_types = [e for e in gql_entities if e.entity_type == EntityType.ENTITY]
    assert len(entity_types) > 0


def test_shipment_found_in_multiple_services():
    """Shipment is owned by Shipping but also appears in Order (as ShipmentInfo)."""
    entities = discover_entities(_get_inventory())
    shipment_like = [e for e in entities if "shipment" in e.name.lower() or "ShipmentInfo" in e.name]
    services = {e.owning_service for e in shipment_like}
    assert len(services) >= 2
