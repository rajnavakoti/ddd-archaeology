"""Exhibit H: Change Velocity Clustering — find development coupling from git co-changes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class CoChangePair:
    """A pair of files that co-change in git commits."""

    file_a: str
    file_b: str
    service_a: str
    service_b: str
    co_changes: int
    total_a: int
    total_b: int
    co_change_pct: float = 0.0
    is_cross_service: bool = False
    coupling_strength: str = ""


@dataclass
class ServiceCoupling:
    """Aggregate coupling between two services."""

    service_a: str
    service_b: str
    avg_co_change_pct: float = 0.0
    max_co_change_pct: float = 0.0
    pair_count: int = 0
    coupling_strength: str = ""


@dataclass
class EncapsulationScore:
    """How well-encapsulated a service's files are."""

    service: str
    total_files: int = 0
    solo_change_files: int = 0
    encapsulation_pct: float = 0.0


@dataclass
class ChangeVelocityResult:
    """Full output of Exhibit H analysis."""

    co_change_pairs: list[CoChangePair] = field(default_factory=list)
    cross_service_pairs: list[CoChangePair] = field(default_factory=list)
    service_couplings: list[ServiceCoupling] = field(default_factory=list)
    encapsulation_scores: list[EncapsulationScore] = field(default_factory=list)
    extraction_overrides: list[dict] = field(default_factory=list)


def run(args: argparse.Namespace) -> int:
    """Analyze git co-change patterns."""
    co_changes_path = Path(args.co_changes)
    if not co_changes_path.exists():
        print(f"Error: {co_changes_path} not found")
        return 1

    co_change_data = json.loads(co_changes_path.read_text())
    result = analyze_change_velocity(co_change_data)

    print(f"\n  ═══ CHANGE VELOCITY CLUSTERING ═══\n")

    # Cross-service pairs
    print(f"  Cross-service co-change pairs ({len(result.cross_service_pairs)}):\n")
    rows = []
    for p in result.cross_service_pairs:
        fa = p.file_a.split("/")[-1]
        fb = p.file_b.split("/")[-1]
        rows.append([f"{fa} + {fb}", f"{p.co_change_pct:.0f}%", p.service_a, p.service_b, p.coupling_strength])
    print_table(["File Pair", "Co-Change %", "Service A", "Service B", "Coupling"], rows)

    # Service-level coupling
    if result.service_couplings:
        print(f"\n  ═══ SERVICE-LEVEL COUPLING ═══\n")
        rows = []
        for sc in result.service_couplings:
            rows.append([f"{sc.service_a} ↔ {sc.service_b}", f"{sc.avg_co_change_pct:.0f}%",
                        f"{sc.max_co_change_pct:.0f}%", str(sc.pair_count), sc.coupling_strength])
        print_table(["Boundary", "Avg Co-Change", "Max Co-Change", "Pairs", "Strength"], rows)

    # Encapsulation scores
    if result.encapsulation_scores:
        print(f"\n  ═══ SERVICE ENCAPSULATION ═══\n")
        rows = []
        for es in sorted(result.encapsulation_scores, key=lambda x: -x.encapsulation_pct):
            rows.append([es.service, str(es.total_files), str(es.solo_change_files), f"{es.encapsulation_pct:.0f}%"])
        print_table(["Service", "Total Files", "Solo-Change Files", "Encapsulation %"], rows)

    # Extraction overrides
    if result.extraction_overrides:
        print(f"\n  ═══ EXTRACTION READINESS OVERRIDES ═══\n")
        for ov in result.extraction_overrides:
            print(f"    {ov['service']}: {ov['previous_status']} → {ov['override_status']} ({ov['reason']})")

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_change_velocity(co_change_data: list[dict]) -> ChangeVelocityResult:
    """Analyze co-change patterns from git data."""
    result = ChangeVelocityResult()

    # Parse pairs and calculate percentages
    for entry in co_change_data:
        total_min = min(entry["total_a"], entry["total_b"])
        pct = (entry["co_changes"] / total_min * 100) if total_min > 0 else 0

        pair = CoChangePair(
            file_a=entry["file_a"],
            file_b=entry["file_b"],
            service_a=entry["service_a"],
            service_b=entry["service_b"],
            co_changes=entry["co_changes"],
            total_a=entry["total_a"],
            total_b=entry["total_b"],
            co_change_pct=pct,
            is_cross_service=entry["service_a"] != entry["service_b"],
            coupling_strength=_classify_coupling(pct),
        )
        result.co_change_pairs.append(pair)

        if pair.is_cross_service:
            result.cross_service_pairs.append(pair)

    # Sort cross-service by co-change percentage
    result.cross_service_pairs.sort(key=lambda p: -p.co_change_pct)

    # Aggregate to service level
    service_pairs: dict[tuple[str, str], list[float]] = defaultdict(list)
    for p in result.cross_service_pairs:
        key = tuple(sorted([p.service_a, p.service_b]))
        service_pairs[key].append(p.co_change_pct)

    for (sa, sb), pcts in sorted(service_pairs.items(), key=lambda x: -max(x[1])):
        avg_pct = sum(pcts) / len(pcts)
        max_pct = max(pcts)
        result.service_couplings.append(ServiceCoupling(
            service_a=sa,
            service_b=sb,
            avg_co_change_pct=avg_pct,
            max_co_change_pct=max_pct,
            pair_count=len(pcts),
            coupling_strength=_classify_coupling(max_pct),
        ))

    # Encapsulation scores per service
    service_files: dict[str, set[str]] = defaultdict(set)
    service_cross_files: dict[str, set[str]] = defaultdict(set)

    for p in result.co_change_pairs:
        service_files[p.service_a].add(p.file_a)
        service_files[p.service_b].add(p.file_b)
        if p.is_cross_service:
            service_cross_files[p.service_a].add(p.file_a)
            service_cross_files[p.service_b].add(p.file_b)

    for service, files in sorted(service_files.items()):
        cross = service_cross_files.get(service, set())
        solo = files - cross
        result.encapsulation_scores.append(EncapsulationScore(
            service=service,
            total_files=len(files),
            solo_change_files=len(solo),
            encapsulation_pct=(len(solo) / len(files) * 100) if files else 0,
        ))

    # Extraction overrides
    for sc in result.service_couplings:
        if sc.max_co_change_pct > 60:
            result.extraction_overrides.append({
                "service": f"{sc.service_a} ↔ {sc.service_b}",
                "previous_status": "may appear ready from transaction analysis",
                "override_status": "NOT READY — development coupling too high",
                "reason": f"{sc.max_co_change_pct:.0f}% max co-change rate",
            })

    return result


def _classify_coupling(pct: float) -> str:
    """Classify coupling strength from co-change percentage."""
    if pct > 70:
        return "effectively_one_unit"
    if pct > 50:
        return "tightly_coupled"
    if pct > 30:
        return "moderately_coupled"
    if pct > 10:
        return "loosely_coupled"
    return "well_separated"
