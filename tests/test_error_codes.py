"""Tests for Exhibit G: Error Code Reverse-Engineering."""

import json
from pathlib import Path

from ddd_archaeology.phases.error_codes import analyze_error_codes


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "errors"


def _load_errors():
    return json.loads((EXAMPLES_DIR / "error_codes.json").read_text())


def test_total_error_codes():
    result = analyze_error_codes(_load_errors())
    assert result.total_error_codes == 12


def test_total_occurrences():
    result = analyze_error_codes(_load_errors())
    assert result.total_occurrences > 30000


def test_sorted_by_frequency():
    result = analyze_error_codes(_load_errors())
    for i in range(1, len(result.rules)):
        assert result.rules[i - 1].occurrences >= result.rules[i].occurrences


def test_finds_misplaced_rules():
    result = analyze_error_codes(_load_errors())
    assert len(result.misplaced_rules) >= 1
    misplaced_codes = {r.code for r in result.misplaced_rules}
    assert "DEL-E011" in misplaced_codes


def test_finds_escape_hatches():
    result = analyze_error_codes(_load_errors())
    assert len(result.escape_hatches) >= 1
    hatch_codes = {r.code for r in result.escape_hatches}
    assert "ORD-E099" in hatch_codes


def test_escape_hatch_governance():
    result = analyze_error_codes(_load_errors())
    e099 = next(r for r in result.escape_hatches if r.code == "ORD-E099")
    assert e099.governance == "unlogged"
    assert e099.occurrences == 891


def test_finds_cross_context_rules():
    result = analyze_error_codes(_load_errors())
    assert len(result.cross_context_rules) >= 1
    cross_codes = {r.code for r in result.cross_context_rules}
    assert "ORD-E031" in cross_codes


def test_finds_thresholds():
    result = analyze_error_codes(_load_errors())
    assert len(result.rules_with_thresholds) >= 3
    threshold_codes = {r.code for r in result.rules_with_thresholds}
    assert "ORD-E003" in threshold_codes  # 2%


def test_price_variance_threshold():
    result = analyze_error_codes(_load_errors())
    e003 = next(r for r in result.rules if r.code == "ORD-E003")
    assert e003.threshold == "2%"
    assert e003.occurrences == 4102


def test_prefix_ownership():
    result = analyze_error_codes(_load_errors())
    assert "ORD" in result.prefix_ownership
    assert "DEL" in result.prefix_ownership
    assert "shipment" in result.prefix_ownership["ORD"]
    assert "carrier" in result.prefix_ownership["DEL"]


def test_del_e011_misplacement():
    result = analyze_error_codes(_load_errors())
    del_e011 = next(r for r in result.rules if r.code == "DEL-E011")
    assert del_e011.is_misplaced
    assert "Returns" in del_e011.should_be_in or "Policy" in del_e011.should_be_in
