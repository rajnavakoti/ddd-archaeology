"""Exhibit E: Incident Clustering — find boundary failures from production incidents."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


SEV_WEIGHTS = {"SEV1": 10, "SEV2": 3, "SEV3": 1}


@dataclass
class BoundaryCluster:
    """Incident cluster at a specific service boundary."""

    boundary: str
    total_incidents: int
    sev1: int = 0
    sev2: int = 0
    sev3: int = 0
    weighted_score: int = 0
    patterns: dict[str, int] = field(default_factory=dict)
    is_internal: bool = False


@dataclass
class IncidentPattern:
    """A specific failure pattern within a boundary cluster."""

    pattern: str
    count: int
    root_causes: list[str] = field(default_factory=list)
    architectural_category: str = ""  # boundary_violation, sync_coupling, missing_compensation, contract_drift


@dataclass
class IncidentClusteringResult:
    """Full output of Exhibit E analysis."""

    total_incidents: int = 0
    cross_boundary_count: int = 0
    cross_boundary_pct: float = 0
    boundary_clusters: list[BoundaryCluster] = field(default_factory=list)
    top_patterns: list[IncidentPattern] = field(default_factory=list)


def run(args: argparse.Namespace) -> int:
    """Analyze incidents for boundary clustering."""
    incidents_path = Path(args.incidents)
    if not incidents_path.exists():
        print(f"Error: {incidents_path} not found")
        return 1

    incidents = json.loads(incidents_path.read_text())
    result = analyze_incidents(incidents)

    print(f"\n  ═══ INCIDENT CLUSTERING RESULTS ═══\n")
    print(f"  Total incidents: {result.total_incidents}")
    print(f"  Cross-boundary: {result.cross_boundary_count} ({result.cross_boundary_pct:.0f}%)")
    print()

    # Boundary clusters
    print("  ═══ BOUNDARY INCIDENT MAP ═══\n")
    rows = []
    for bc in result.boundary_clusters:
        if bc.is_internal:
            continue
        rows.append([bc.boundary, str(bc.total_incidents), str(bc.sev1), str(bc.sev2), str(bc.sev3), str(bc.weighted_score)])
    print_table(["Boundary", "Total", "SEV1", "SEV2", "SEV3", "Weighted Score"], rows)

    # Internal
    internal = [bc for bc in result.boundary_clusters if bc.is_internal]
    if internal:
        print(f"\n  Internal (single-service) incidents:")
        for bc in internal:
            print(f"    {bc.boundary}: {bc.total_incidents} (SEV1:{bc.sev1}, SEV2:{bc.sev2}, SEV3:{bc.sev3})")

    # Top patterns
    if result.top_patterns:
        print(f"\n  ═══ TOP INCIDENT PATTERNS ═══\n")
        rows = []
        for p in result.top_patterns:
            rows.append([p.pattern, str(p.count), p.architectural_category])
        print_table(["Pattern", "Count", "Architectural Category"], rows)

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_incidents(incidents: list[dict]) -> IncidentClusteringResult:
    """Analyze incidents for boundary clustering patterns."""
    result = IncidentClusteringResult()
    result.total_incidents = len(incidents)

    # Group by boundary
    boundary_groups: dict[str, list[dict]] = defaultdict(list)
    for inc in incidents:
        boundary = inc.get("boundary", "unknown")
        boundary_groups[boundary].append(inc)

    # Build clusters
    for boundary, incs in sorted(boundary_groups.items(), key=lambda x: -len(x[1])):
        is_internal = boundary == "internal"
        sev_counts = {"SEV1": 0, "SEV2": 0, "SEV3": 0}
        patterns: dict[str, int] = defaultdict(int)

        for inc in incs:
            sev = inc.get("severity", "SEV3")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            pattern = inc.get("pattern", "unknown")
            patterns[pattern] += 1

        weighted = sum(sev_counts.get(s, 0) * w for s, w in SEV_WEIGHTS.items())

        cluster = BoundaryCluster(
            boundary=boundary,
            total_incidents=len(incs),
            sev1=sev_counts["SEV1"],
            sev2=sev_counts["SEV2"],
            sev3=sev_counts["SEV3"],
            weighted_score=weighted,
            patterns=dict(patterns),
            is_internal=is_internal,
        )
        result.boundary_clusters.append(cluster)

        if not is_internal:
            result.cross_boundary_count += len(incs)

    result.cross_boundary_pct = (
        (result.cross_boundary_count / result.total_incidents * 100)
        if result.total_incidents > 0
        else 0
    )

    # Build pattern taxonomy across all cross-boundary incidents
    pattern_counts: dict[str, int] = defaultdict(int)
    pattern_causes: dict[str, list[str]] = defaultdict(list)
    for inc in incidents:
        if inc.get("boundary") == "internal":
            continue
        pattern = inc.get("pattern", "unknown")
        pattern_counts[pattern] += 1
        rc = inc.get("root_cause", "")
        if rc and rc not in pattern_causes[pattern]:
            pattern_causes[pattern].append(rc)

    # Map patterns to architectural categories
    arch_categories = {
        "race_condition": "boundary_violation",
        "timeout": "sync_coupling",
        "stale_read": "read_consistency",
        "orphaned_state": "missing_compensation",
        "data_inconsistency": "data_ownership",
        "contract_violation": "contract_drift",
        "cascading_failure": "sync_coupling",
    }

    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        result.top_patterns.append(IncidentPattern(
            pattern=pattern,
            count=count,
            root_causes=pattern_causes.get(pattern, [])[:3],
            architectural_category=arch_categories.get(pattern, "other"),
        ))

    # Sort clusters by weighted score
    result.boundary_clusters.sort(key=lambda x: (-x.weighted_score if not x.is_internal else 0))

    return result
