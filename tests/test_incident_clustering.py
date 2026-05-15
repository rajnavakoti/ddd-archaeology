"""Tests for Exhibit E: Incident Clustering."""

import json
from pathlib import Path

from ddd_archaeology.phases.incident_clustering import analyze_incidents


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "incidents"


def _load_incidents():
    return json.loads((EXAMPLES_DIR / "incidents.json").read_text())


def test_total_incidents():
    result = analyze_incidents(_load_incidents())
    assert result.total_incidents == 83


def test_cross_boundary_percentage():
    result = analyze_incidents(_load_incidents())
    assert result.cross_boundary_pct > 75  # ~77%


def test_shipment_inventory_top_cluster():
    result = analyze_incidents(_load_incidents())
    cross = [bc for bc in result.boundary_clusters if not bc.is_internal]
    assert cross[0].boundary == "Shipment ↔ Inventory"
    assert cross[0].total_incidents == 23


def test_shipment_inventory_sev1_count():
    result = analyze_incidents(_load_incidents())
    si = next(bc for bc in result.boundary_clusters if bc.boundary == "Shipment ↔ Inventory")
    assert si.sev1 == 4


def test_carrier_integration_cluster():
    result = analyze_incidents(_load_incidents())
    sc = next(bc for bc in result.boundary_clusters if "Carrier" in bc.boundary)
    assert sc.total_incidents == 17


def test_invoicing_cluster():
    result = analyze_incidents(_load_incidents())
    inv = next(bc for bc in result.boundary_clusters if "Invoicing" in bc.boundary)
    assert inv.total_incidents == 14


def test_internal_incidents_separated():
    result = analyze_incidents(_load_incidents())
    internal = [bc for bc in result.boundary_clusters if bc.is_internal]
    assert len(internal) == 1
    assert internal[0].total_incidents == 19


def test_weighted_score_ordering():
    result = analyze_incidents(_load_incidents())
    cross = [bc for bc in result.boundary_clusters if not bc.is_internal]
    # Should be sorted by weighted score descending
    for i in range(1, len(cross)):
        assert cross[i - 1].weighted_score >= cross[i].weighted_score


def test_pattern_taxonomy():
    result = analyze_incidents(_load_incidents())
    pattern_names = {p.pattern for p in result.top_patterns}
    assert "race_condition" in pattern_names
    assert "timeout" in pattern_names
    assert "orphaned_state" in pattern_names


def test_patterns_have_architectural_categories():
    result = analyze_incidents(_load_incidents())
    for p in result.top_patterns:
        assert p.architectural_category != "", f"Pattern {p.pattern} has no category"


def test_race_condition_is_boundary_violation():
    result = analyze_incidents(_load_incidents())
    rc = next(p for p in result.top_patterns if p.pattern == "race_condition")
    assert rc.architectural_category == "boundary_violation"
