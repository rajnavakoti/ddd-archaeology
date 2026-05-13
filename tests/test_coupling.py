"""Tests for Phase 6: coupling analysis."""

import json
from pathlib import Path

from ddd_archaeology.models import CouplingType
from ddd_archaeology.phases.collect import collect_contracts
from ddd_archaeology.phases.discover_entities import discover_entities
from ddd_archaeology.phases.analyze_coupling import analyze_coupling, _deserialize_entities
from ddd_archaeology.output.writer import _to_serializable


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery"


def _get_entities():
    contracts = collect_contracts(EXAMPLES_DIR)
    inventory = json.loads(json.dumps(_to_serializable(contracts)))
    entities = discover_entities(inventory)
    raw = json.loads(json.dumps(_to_serializable(entities)))
    return _deserialize_entities(raw)


def test_finds_coupling_edges():
    result = analyze_coupling(_get_entities())
    assert len(result.edges) > 5


def test_order_references_customer():
    result = analyze_coupling(_get_entities())
    id_refs = [e for e in result.edges if e.coupling_type == CouplingType.ID_REFERENCE]
    order_to_customer = [
        e for e in id_refs
        if "Shipment" in e.source_service and "Consignee" in e.target_service
    ]
    assert len(order_to_customer) > 0


def test_order_references_inventory():
    result = analyze_coupling(_get_entities())
    id_refs = [e for e in result.edges if e.coupling_type == CouplingType.ID_REFERENCE]
    order_to_inventory = [
        e for e in id_refs
        if "Shipment" in e.source_service and "Inventory" in e.target_service
    ]
    assert len(order_to_inventory) > 0


def test_finds_schema_duplication():
    result = analyze_coupling(_get_entities())
    schema_dups = [e for e in result.edges if e.coupling_type == CouplingType.SCHEMA_DUPLICATION]
    assert len(schema_dups) > 0
    # Invoice should be duplicated between Order and Billing
    invoice_dup = [e for e in schema_dups if "Invoice" in e.evidence]
    assert len(invoice_dup) > 0


def test_finds_event_publishing():
    result = analyze_coupling(_get_entities())
    event_pubs = [e for e in result.edges if e.coupling_type == CouplingType.EVENT_PUBLISH]
    assert len(event_pubs) > 0
    publishers = {e.source_service for e in event_pubs}
    assert any("Shipment" in p for p in publishers)
    assert any("Carrier" in p for p in publishers)


def test_identifies_silent_services():
    result = analyze_coupling(_get_entities())
    assert len(result.silent_services) > 0
    # Consignee and Invoicing publish no events
    silent_names = " ".join(result.silent_services)
    assert "Consignee" in silent_names
    assert "Invoicing" in silent_names


def test_detects_circular_dependencies():
    result = analyze_coupling(_get_entities())
    # Shipment and Carrier have circular coupling
    found_circular = False
    for pair in result.circular_deps:
        combined = pair[0] + pair[1]
        if "Shipment" in combined and "Carrier" in combined:
            found_circular = True
    assert found_circular, f"Expected Shipment-Carrier circular dep, got: {result.circular_deps}"


def test_service_list_populated():
    result = analyze_coupling(_get_entities())
    assert len(result.service_list) >= 6
