"""Tests for Exhibit H: Change Velocity Clustering."""

import json
from pathlib import Path

from ddd_archaeology.phases.change_velocity import analyze_change_velocity


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "git"


def _load_data():
    return json.loads((EXAMPLES_DIR / "co_changes.json").read_text())


def test_finds_co_change_pairs():
    result = analyze_change_velocity(_load_data())
    assert len(result.co_change_pairs) == 12


def test_finds_cross_service_pairs():
    result = analyze_change_velocity(_load_data())
    assert len(result.cross_service_pairs) >= 3


def test_order_shipment_high_coupling():
    result = analyze_change_velocity(_load_data())
    pair = next(
        (p for p in result.cross_service_pairs
         if "OrderController" in p.file_a and "ShipmentService" in p.file_b),
        None,
    )
    assert pair is not None
    assert pair.co_change_pct > 70


def test_delivery_inventory_coupling():
    result = analyze_change_velocity(_load_data())
    pair = next(
        (p for p in result.cross_service_pairs
         if "DeliveryScheduler" in p.file_a and "InventoryChecker" in p.file_b),
        None,
    )
    assert pair is not None
    assert pair.co_change_pct > 60


def test_service_level_coupling():
    result = analyze_change_velocity(_load_data())
    assert len(result.service_couplings) >= 2
    # Shipment ↔ Carrier should be the highest
    top = result.service_couplings[0]
    assert "shipment" in top.service_a or "carrier" in top.service_a


def test_coupling_strength_classification():
    result = analyze_change_velocity(_load_data())
    for p in result.cross_service_pairs:
        assert p.coupling_strength in (
            "effectively_one_unit", "tightly_coupled", "moderately_coupled",
            "loosely_coupled", "well_separated",
        )


def test_encapsulation_scores():
    result = analyze_change_velocity(_load_data())
    assert len(result.encapsulation_scores) >= 4
    # Consignee should have high encapsulation
    consignee = next(
        (es for es in result.encapsulation_scores if "consignee" in es.service),
        None,
    )
    assert consignee is not None
    assert consignee.encapsulation_pct > 50


def test_extraction_overrides_generated():
    result = analyze_change_velocity(_load_data())
    assert len(result.extraction_overrides) >= 1
    # Should flag high co-change as override
    override_text = " ".join(str(ov) for ov in result.extraction_overrides)
    assert "NOT READY" in override_text


def test_co_change_normalized_by_min():
    result = analyze_change_velocity(_load_data())
    # Verify normalization: co_changes / min(total_a, total_b) * 100
    for p in result.co_change_pairs:
        expected = p.co_changes / min(p.total_a, p.total_b) * 100
        assert abs(p.co_change_pct - expected) < 0.1


def test_cross_service_sorted_descending():
    result = analyze_change_velocity(_load_data())
    for i in range(1, len(result.cross_service_pairs)):
        assert result.cross_service_pairs[i - 1].co_change_pct >= result.cross_service_pairs[i].co_change_pct
