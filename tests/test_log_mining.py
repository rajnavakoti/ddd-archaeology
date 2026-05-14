"""Tests for Exhibit D: Log Mining."""

import json
from pathlib import Path

from ddd_archaeology.phases.log_mining import analyze_logs, _load_jsonl


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "delivery" / "logs"


def _load_test_data():
    trace = _load_jsonl(EXAMPLES_DIR / "sample_trace.jsonl")
    frequency = json.loads((EXAMPLES_DIR / "event_frequency.json").read_text())
    return trace, frequency


def test_builds_flow():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    assert len(result.traced_flows) == 1
    assert len(result.traced_flows[0]) == 11  # 11 log entries


def test_flow_is_chronological():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    flow = result.traced_flows[0]
    for i in range(1, len(flow)):
        assert flow[i].timestamp >= flow[i - 1].timestamp


def test_detects_sync_chain():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    assert len(result.sync_chains) >= 1
    # The first sync chain should include shipment-service and inventory-service
    all_services_in_chains = set()
    for chain in result.sync_chains:
        all_services_in_chains.update(chain)
    assert "shipment-service" in all_services_in_chains


def test_detects_async_boundary():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    assert len(result.async_boundaries) >= 1
    # Should detect the 87-second gap to carrier-integration
    carrier_boundary = [b for b in result.async_boundaries if "carrier" in b["to_service"]]
    assert len(carrier_boundary) >= 1


def test_builds_event_catalog():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    assert len(result.event_catalog) == 18  # 18 events in frequency data


def test_categorizes_core_events():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    core = [e for e in result.event_catalog if e.category == "core"]
    assert len(core) >= 5  # Several high-frequency events


def test_categorizes_error_events():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    errors = [e for e in result.event_catalog if e.category == "error"]
    assert len(errors) >= 2  # FAILED, CANCELLED, RETRY events
    error_names = {e.event_name for e in errors}
    assert any("FAILED" in n for n in error_names)


def test_detects_silent_participants():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    # tracking-notifications only sends emails, doesn't own state changes
    assert "tracking-notifications" in result.silent_participants


def test_timing_classification():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    flow = result.traced_flows[0]
    # First few steps should be sync (within milliseconds)
    sync_steps = [s for s in flow if s.coupling_type == "sync"]
    assert len(sync_steps) >= 3


def test_order_created_is_first_event():
    trace, freq = _load_test_data()
    result = analyze_logs(trace, freq)
    flow = result.traced_flows[0]
    assert "DRAFT" in flow[0].state or "created" in flow[0].event.lower()
