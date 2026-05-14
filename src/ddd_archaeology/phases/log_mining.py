"""Exhibit D: Log Mining — recover fossilized domain events from production logs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class LogEvent:
    """A single parsed log entry."""

    timestamp: str
    service: str
    message: str
    order_id: str = ""
    event_type: str = ""
    entity: str = ""
    state: str = ""
    level: str = "INFO"


@dataclass
class FlowStep:
    """One step in a traced entity flow."""

    timestamp: str
    service: str
    event: str
    entity: str
    state: str
    delta_ms: float = 0  # time since previous step
    coupling_type: str = ""  # sync (<100ms), async (>5s), ambiguous


@dataclass
class FossilizedEvent:
    """An implicit domain event recovered from logs."""

    event_name: str
    entity: str
    service: str
    daily_count: int
    category: str = ""  # core, secondary, edge_case, error


@dataclass
class LogMiningResult:
    """Full output of Exhibit D analysis."""

    traced_flows: list[list[FlowStep]] = field(default_factory=list)
    event_catalog: list[FossilizedEvent] = field(default_factory=list)
    sync_chains: list[list[str]] = field(default_factory=list)
    async_boundaries: list[dict] = field(default_factory=list)
    silent_participants: list[str] = field(default_factory=list)


def run(args: argparse.Namespace) -> int:
    """Analyze production logs for fossilized domain events."""
    trace_path = Path(args.trace)
    if not trace_path.exists():
        print(f"Error: {trace_path} not found")
        return 1

    trace_data = _load_jsonl(trace_path)

    frequency_data = []
    if args.frequency:
        freq_path = Path(args.frequency)
        if freq_path.exists():
            frequency_data = json.loads(freq_path.read_text())

    result = analyze_logs(trace_data, frequency_data)

    # Print results
    print(f"\n  ═══ LOG MINING RESULTS ═══\n")

    # Traced flows
    for i, flow in enumerate(result.traced_flows):
        entity_id = flow[0].event if flow else "unknown"
        print(f"  Flow {i + 1}: {len(flow)} steps\n")
        rows = []
        for step in flow:
            coupling = f"  ← {step.coupling_type}" if step.coupling_type else ""
            rows.append([step.timestamp, step.service, f"{step.entity} {step.state}", f"{step.delta_ms:.0f}ms{coupling}"])
        print_table(["Timestamp", "Service", "Event", "Delta"], rows)
        print()

    # Sync chains
    if result.sync_chains:
        print("  ═══ SYNCHRONOUS CHAINS ═══\n")
        for chain in result.sync_chains:
            print(f"    → {' → '.join(chain)}")
        print()

    # Async boundaries
    if result.async_boundaries:
        print("  ═══ ASYNC BOUNDARIES ═══\n")
        for boundary in result.async_boundaries:
            print(f"    {boundary['from_service']} →({boundary['gap_seconds']:.0f}s)→ {boundary['to_service']}")
        print()

    # Event catalog
    if result.event_catalog:
        print(f"  ═══ FOSSILIZED EVENT CATALOG ({len(result.event_catalog)} events) ═══\n")
        rows = []
        for ev in sorted(result.event_catalog, key=lambda x: -x.daily_count):
            rows.append([ev.event_name, ev.entity, ev.service, str(ev.daily_count), ev.category])
        print_table(["Event", "Entity", "Service", "Daily Count", "Category"], rows)

    # Silent participants
    if result.silent_participants:
        print(f"\n  ⚠ Silent participants (appear in flows but not in event catalog as state owners):")
        for sp in result.silent_participants:
            print(f"    • {sp}")

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_logs(
    trace_data: list[dict],
    frequency_data: list[dict] | None = None,
) -> LogMiningResult:
    """Analyze log trace data and frequency data."""
    result = LogMiningResult()

    # Phase 2: Trace entity flow
    if trace_data:
        flow = _build_flow(trace_data)
        result.traced_flows.append(flow)

        # Phase 4: Timing analysis
        result.sync_chains, result.async_boundaries = _analyze_timing(flow)

    # Phase 3: Build event catalog from frequency data
    if frequency_data:
        result.event_catalog = _build_event_catalog(frequency_data)

    # Detect silent participants
    if trace_data:
        state_services = {e["service"] for e in trace_data if e.get("event_type") == "state_change"}
        all_services = {e["service"] for e in trace_data}
        result.silent_participants = sorted(all_services - state_services)

    return result


def _build_flow(trace_data: list[dict]) -> list[FlowStep]:
    """Build a chronological flow from trace data."""
    sorted_events = sorted(trace_data, key=lambda x: x["timestamp"])
    flow: list[FlowStep] = []
    prev_time = None

    for event in sorted_events:
        ts = event["timestamp"]
        current_time = _parse_timestamp(ts)

        delta_ms = 0
        if prev_time:
            delta_ms = (current_time - prev_time).total_seconds() * 1000

        coupling = _classify_timing(delta_ms) if prev_time else ""

        flow.append(FlowStep(
            timestamp=ts,
            service=event.get("service", "unknown"),
            event=event.get("message", ""),
            entity=event.get("entity", ""),
            state=event.get("state", ""),
            delta_ms=delta_ms,
            coupling_type=coupling,
        ))
        prev_time = current_time

    return flow


def _analyze_timing(flow: list[FlowStep]) -> tuple[list[list[str]], list[dict]]:
    """Identify synchronous chains and async boundaries from timing."""
    sync_chains: list[list[str]] = []
    async_boundaries: list[dict] = []
    current_chain: list[str] = []

    for i, step in enumerate(flow):
        if i == 0:
            current_chain = [step.service]
            continue

        if step.coupling_type == "sync":
            if step.service not in current_chain:
                current_chain.append(step.service)
        else:
            # End current sync chain
            if len(current_chain) >= 2:
                sync_chains.append(current_chain)

            if step.coupling_type == "async":
                async_boundaries.append({
                    "from_service": flow[i - 1].service,
                    "to_service": step.service,
                    "gap_seconds": step.delta_ms / 1000,
                })

            current_chain = [step.service]

    # Don't forget the last chain
    if len(current_chain) >= 2:
        sync_chains.append(current_chain)

    return sync_chains, async_boundaries


def _build_event_catalog(frequency_data: list[dict]) -> list[FossilizedEvent]:
    """Build fossilized event catalog from frequency data."""
    catalog: list[FossilizedEvent] = []

    for entry in frequency_data:
        daily = entry.get("daily_count", 0)

        if daily >= 5000:
            category = "core"
        elif daily >= 100:
            category = "secondary"
        elif daily >= 10:
            category = "edge_case"
        else:
            category = "rare"

        # Detect error events
        event_name = entry.get("event", "")
        if any(kw in event_name.upper() for kw in ("FAILED", "CANCELLED", "ERROR", "RETRY")):
            category = "error"

        catalog.append(FossilizedEvent(
            event_name=event_name,
            entity=entry.get("entity", ""),
            service=entry.get("service", ""),
            daily_count=daily,
            category=category,
        ))

    return catalog


def _classify_timing(delta_ms: float) -> str:
    """Classify timing gap as sync, ambiguous, or async."""
    if delta_ms < 500:
        return "sync"
    if delta_ms < 5000:
        return "ambiguous"
    return "async"


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    # Handle Z suffix
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file (one JSON object per line)."""
    entries = []
    for line in path.read_text().strip().split("\n"):
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
