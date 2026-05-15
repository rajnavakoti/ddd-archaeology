"""Tests for Exhibit F: Data Lineage Tracing."""

import json
from pathlib import Path

from ddd_archaeology.phases.data_lineage import analyze_lineage


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "database"


def _load_lineage():
    return json.loads((EXAMPLES_DIR / "data_lineage.json").read_text())


def test_identifies_source():
    result = analyze_lineage(_load_lineage())
    assert result.source_service == "Consignee Service"
    assert result.source_table == "customer_addresses"


def test_finds_all_copies():
    result = analyze_lineage(_load_lineage())
    assert len(result.copies) == 4


def test_detects_lossy_format():
    result = analyze_lineage(_load_lineage())
    lossy = [c for c in result.copies if c.is_lossy]
    assert len(lossy) >= 1
    assert any("Invoicing" in c.service for c in lossy)


def test_detects_independent_update():
    result = analyze_lineage(_load_lineage())
    independent = [c for c in result.copies if c.can_update_independently]
    assert len(independent) >= 1
    assert any("Carrier" in c.service for c in independent)


def test_total_mismatches():
    result = analyze_lineage(_load_lineage())
    assert result.total_mismatches == 342


def test_expected_vs_unexpected():
    result = analyze_lineage(_load_lineage())
    assert result.expected_mismatches == 200
    assert result.unexpected_mismatches == 142


def test_missing_events_found():
    result = analyze_lineage(_load_lineage())
    assert len(result.missing_events) >= 2
    event_names = {me.event_name for me in result.missing_events}
    assert "DeliveryAddressChanged" in event_names


def test_context_boundaries_derived():
    result = analyze_lineage(_load_lineage())
    assert len(result.context_boundaries) >= 3
    services = {cb["context"] for cb in result.context_boundaries}
    assert "Invoicing Service" in services  # lossy format
    assert "Carrier Integration Service" in services  # independent update


def test_field_count_comparison():
    result = analyze_lineage(_load_lineage())
    # Invoicing has only 1 field (concatenated) vs source's 9
    invoicing = next(c for c in result.copies if "Invoicing" in c.service)
    assert invoicing.field_count < result.source_field_count
