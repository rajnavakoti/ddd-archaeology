"""Exhibit F: Data Lineage Tracing — trace entity copies and find divergence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class CopyInfo:
    """A copy of a source entity in another service."""

    copy_id: str
    table: str
    service: str
    format: str
    fields: list[str]
    field_count: int
    copied_at: str
    update_policy: str
    notes: str = ""
    is_lossy: bool = False
    can_update_independently: bool = False


@dataclass
class MismatchInfo:
    """A data mismatch between source and copy."""

    mismatch_type: str
    count: int
    between: list[str]
    notes: str = ""


@dataclass
class MissingEvent:
    """An event that should exist based on lineage findings."""

    event_name: str
    reason: str


@dataclass
class DataLineageResult:
    """Full output of Exhibit F analysis."""

    entity: str = ""
    source_service: str = ""
    source_table: str = ""
    source_field_count: int = 0
    copies: list[CopyInfo] = field(default_factory=list)
    total_mismatches: int = 0
    expected_mismatches: int = 0
    unexpected_mismatches: int = 0
    mismatch_details: list[MismatchInfo] = field(default_factory=list)
    missing_events: list[MissingEvent] = field(default_factory=list)
    context_boundaries: list[dict] = field(default_factory=list)


def run(args: argparse.Namespace) -> int:
    """Analyze data lineage for an entity."""
    lineage_path = Path(args.lineage)
    if not lineage_path.exists():
        print(f"Error: {lineage_path} not found")
        return 1

    lineage_data = json.loads(lineage_path.read_text())
    result = analyze_lineage(lineage_data)

    print(f"\n  ═══ DATA LINEAGE: {result.entity.upper()} ═══\n")
    print(f"  Source: {result.source_table} ({result.source_service}, {result.source_field_count} fields)\n")

    # Copies
    print(f"  {len(result.copies)} copies found:\n")
    rows = []
    for c in result.copies:
        flags = []
        if c.is_lossy:
            flags.append("LOSSY")
        if c.can_update_independently:
            flags.append("INDEPENDENT UPDATE")
        flag_str = " | ".join(flags) if flags else "—"
        rows.append([c.table, c.service, c.format, str(c.field_count), c.update_policy, flag_str])
    print_table(["Table", "Service", "Format", "Fields", "Update Policy", "Flags"], rows)

    # Mismatches
    if result.total_mismatches > 0:
        print(f"\n  ═══ CONSISTENCY CHECK ═══\n")
        print(f"  Total mismatches: {result.total_mismatches}")
        print(f"    Expected (snapshot divergence): {result.expected_mismatches}")
        print(f"    Unexpected (missing propagation): {result.unexpected_mismatches}\n")
        for m in result.mismatch_details:
            between = " ↔ ".join(m.between)
            notes = f" ({m.notes})" if m.notes else ""
            print(f"    • {m.mismatch_type}: {m.count} [{between}]{notes}")

    # Missing events
    if result.missing_events:
        print(f"\n  ═══ MISSING EVENTS ═══\n")
        for me in result.missing_events:
            print(f"    • {me.event_name}: {me.reason}")

    # Context boundaries
    if result.context_boundaries:
        print(f"\n  ═══ CONTEXT BOUNDARY SIGNALS ═══\n")
        rows = []
        for cb in result.context_boundaries:
            rows.append([cb["copy"], cb["context"], cb["reason"]])
        print_table(["Copy", "Context", "Why It's Different"], rows)

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_lineage(lineage_data: dict) -> DataLineageResult:
    """Analyze data lineage from structured input."""
    result = DataLineageResult()

    result.entity = lineage_data.get("entity", "unknown")
    source = lineage_data.get("source", {})
    result.source_service = source.get("service", "unknown")
    result.source_table = source.get("table", "unknown")
    result.source_field_count = source.get("field_count", len(source.get("fields", [])))

    # Parse copies
    for copy in lineage_data.get("copies", []):
        copy_info = CopyInfo(
            copy_id=copy.get("id", ""),
            table=copy.get("table", ""),
            service=copy.get("service", ""),
            format=copy.get("format", ""),
            fields=copy.get("fields", []),
            field_count=copy.get("field_count", len(copy.get("fields", []))),
            copied_at=copy.get("copied_at", ""),
            update_policy=copy.get("update_policy", ""),
            notes=copy.get("notes", ""),
        )

        # Detect lossy formats
        copy_info.is_lossy = copy_info.format in ("concatenated_text", "single_string", "binary")

        # Detect independent update capability
        copy_info.can_update_independently = "mutable" in copy_info.update_policy.lower() or "independent" in copy_info.notes.lower()

        result.copies.append(copy_info)

    # Parse consistency check
    consistency = lineage_data.get("consistency_check", {})
    mismatches = consistency.get("mismatches", {})
    result.total_mismatches = mismatches.get("total", 0)
    result.expected_mismatches = mismatches.get("expected_snapshot_divergence", 0)
    result.unexpected_mismatches = mismatches.get("unexpected_missing_propagation", 0)

    for detail in mismatches.get("details", []):
        result.mismatch_details.append(MismatchInfo(
            mismatch_type=detail.get("type", ""),
            count=detail.get("count", 0),
            between=detail.get("between", []),
            notes=detail.get("notes", ""),
        ))

    # Parse missing events
    for me in lineage_data.get("missing_events", []):
        result.missing_events.append(MissingEvent(
            event_name=me.get("event", ""),
            reason=me.get("reason", ""),
        ))

    # Derive context boundaries
    result.context_boundaries = _derive_context_boundaries(result)

    return result


def _derive_context_boundaries(result: DataLineageResult) -> list[dict]:
    """Derive context boundary signals from copy analysis."""
    boundaries: list[dict] = []

    for copy in result.copies:
        reasons = []

        if copy.format != "normalized_columns":
            reasons.append(f"different format ({copy.format})")
        if copy.update_policy == "never":
            reasons.append("immutable snapshot")
        if copy.can_update_independently:
            reasons.append("can update independently of source")
        if copy.is_lossy:
            reasons.append("lossy transformation — unreconstructable")
        if copy.field_count != result.source_field_count:
            reasons.append(f"different field count ({copy.field_count} vs {result.source_field_count})")

        if reasons:
            boundaries.append({
                "copy": copy.table,
                "context": copy.service,
                "reason": "; ".join(reasons),
            })

    return boundaries
