"""Tests for Phase 4-5: cross-entity comparison and vocabulary consistency."""

import json
from pathlib import Path

from ddd_archaeology.phases.collect import collect_contracts
from ddd_archaeology.phases.discover_entities import discover_entities
from ddd_archaeology.phases.compare import compare_entities, _deserialize_entities
from ddd_archaeology.output.writer import _to_serializable


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery"


def _get_entities():
    contracts = collect_contracts(EXAMPLES_DIR)
    inventory = json.loads(json.dumps(_to_serializable(contracts)))
    entities = discover_entities(inventory)
    raw = json.loads(json.dumps(_to_serializable(entities)))
    return _deserialize_entities(raw)


def test_finds_shared_concepts():
    result = compare_entities(_get_entities())
    assert len(result.entity_comparisons) > 0


def test_finds_order_in_multiple_services():
    result = compare_entities(_get_entities())
    order_comp = next((c for c in result.entity_comparisons if c.concept_name == "Order"), None)
    assert order_comp is not None
    services = {i.service for i in order_comp.instances}
    assert len(services) >= 2


def test_finds_invoice_in_multiple_services():
    result = compare_entities(_get_entities())
    invoice_comp = next((c for c in result.entity_comparisons if c.concept_name == "Invoice"), None)
    assert invoice_comp is not None
    services = {i.service for i in invoice_comp.instances}
    assert len(services) >= 2


def test_finds_address_cross_service():
    result = compare_entities(_get_entities())
    address_comp = next((c for c in result.entity_comparisons if "Address" in c.concept_name and "cross" in c.concept_name), None)
    assert address_comp is not None
    assert len(address_comp.instances) >= 3


def test_address_has_vocabulary_drift():
    result = compare_entities(_get_entities())
    address_comp = next((c for c in result.entity_comparisons if "Address" in c.concept_name and "cross" in c.concept_name), None)
    assert address_comp is not None
    assert len(address_comp.vocabulary_drift) > 0
    drift_concepts = {d.concept for d in address_comp.vocabulary_drift}
    assert "street_line_1" in drift_concepts or "postal_code" in drift_concepts


def test_person_concept_drift_detected():
    result = compare_entities(_get_entities())
    assert result.person_concept_drift is not None
    names = set(result.person_concept_drift.names_used.values())
    assert len(names) >= 3  # buyer, customer, user, recipient, account


def test_person_concept_has_canonical_owner():
    result = compare_entities(_get_entities())
    assert result.person_concept_drift is not None
    assert result.person_concept_drift.canonical_owner != ""
    assert "Consignee" in result.person_concept_drift.canonical_owner


def test_vocabulary_reports_exist():
    result = compare_entities(_get_entities())
    assert len(result.vocabulary_reports) > 0


def test_field_overlap_calculated():
    result = compare_entities(_get_entities())
    for comp in result.entity_comparisons:
        if comp.concept_name != "Address (cross-service)":
            assert comp.field_overlap >= 0
            assert comp.field_overlap <= 1
