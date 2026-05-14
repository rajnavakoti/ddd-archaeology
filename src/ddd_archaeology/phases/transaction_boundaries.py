"""Exhibit C: Transaction Boundary Analysis — find aggregates from co-write patterns."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class TransactionCluster:
    """A group of tables consistently written together."""

    tables: list[str]
    occurrence_count: int
    service: str
    avg_duration_ms: float = 0
    classification: str = ""  # clean_aggregate, cross_context, distributed_concern, orm_artifact, audit_pattern
    root_table: str = ""
    severity: str = ""


@dataclass
class AggregateCandidate:
    """An inferred aggregate boundary."""

    root: str
    children: list[str]
    service: str
    total_occurrences: int
    confidence: str = ""


@dataclass
class ExtractionReadiness:
    """Extraction readiness for a service."""

    service: str
    status: str  # ready, extractable_with_work, blocked, entangled
    clean_clusters: int = 0
    cross_context_clusters: int = 0
    cross_context_frequency: int = 0
    details: str = ""


@dataclass
class TransactionAnalysisResult:
    """Full output of Exhibit C analysis."""

    clusters: list[TransactionCluster] = field(default_factory=list)
    aggregates: list[AggregateCandidate] = field(default_factory=list)
    extraction_readiness: list[ExtractionReadiness] = field(default_factory=list)


def run(args: argparse.Namespace) -> int:
    """Analyze transaction clusters."""
    clusters_path = Path(args.clusters)
    if not clusters_path.exists():
        print(f"Error: {clusters_path} not found")
        return 1

    raw_clusters = json.loads(clusters_path.read_text())

    # Load table ownership from Exhibit B if available
    table_owners: dict[str, str] = {}
    if args.schema_archaeology:
        schema_path = Path(args.schema_archaeology)
        if schema_path.exists():
            schema_data = json.loads(schema_path.read_text())
            table_owners = _extract_table_owners(schema_data)

    result = analyze_transactions(raw_clusters, table_owners)

    # Print results
    print(f"\n  ═══ TRANSACTION BOUNDARY ANALYSIS ═══\n")

    # Clusters
    print(f"  {len(result.clusters)} transaction clusters analyzed\n")
    rows = []
    for c in result.clusters:
        tables = ", ".join(c.tables)
        duration = f"{c.avg_duration_ms}ms"
        rows.append([tables, str(c.occurrence_count), c.service, duration, c.classification, c.severity])
    print_table(["Tables", "Count", "Service", "Avg Duration", "Classification", "Severity"], rows)

    # Aggregates
    print(f"\n  ═══ INFERRED AGGREGATES ═══\n")
    for agg in result.aggregates:
        children = ", ".join(agg.children) if agg.children else "—"
        print(f"    {agg.root} [{agg.service}] → {children} ({agg.total_occurrences} commits, {agg.confidence})")

    # Extraction readiness
    print(f"\n  ═══ EXTRACTION READINESS ═══\n")
    rows = []
    for er in result.extraction_readiness:
        rows.append([er.service, er.status, str(er.clean_clusters), str(er.cross_context_clusters),
                      str(er.cross_context_frequency), er.details])
    print_table(["Service", "Status", "Clean", "Cross-Context", "Cross-Freq", "Details"], rows)

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_transactions(
    raw_clusters: list[dict],
    table_owners: dict[str, str] | None = None,
) -> TransactionAnalysisResult:
    """Analyze transaction co-write clusters."""
    result = TransactionAnalysisResult()

    if table_owners is None:
        table_owners = {}

    # Phase 2-3: Classify clusters
    for raw in raw_clusters:
        tables = sorted(raw["tables_modified"])
        count = raw["occurrence_count"]
        service = raw["service_name"]
        duration = raw.get("avg_duration_ms", 0)

        cluster = TransactionCluster(
            tables=tables,
            occurrence_count=count,
            service=service,
            avg_duration_ms=duration,
        )

        # Classify
        cluster.classification, cluster.severity = _classify_cluster(
            tables, count, service, duration, table_owners,
        )

        # Identify root table (first table alphabetically that appears most often, or the one without a parent FK pattern)
        cluster.root_table = _identify_root(tables)

        result.clusters.append(cluster)

    # Phase 4: Identify aggregates from clean clusters
    result.aggregates = _build_aggregates(result.clusters)

    # Phase 5: Extraction readiness
    result.extraction_readiness = _assess_extraction(result.clusters)

    return result


def _classify_cluster(
    tables: list[str],
    count: int,
    service: str,
    duration_ms: float,
    table_owners: dict[str, str],
) -> tuple[str, str]:
    """Classify a transaction cluster."""
    # ORM artifact: low frequency, doesn't make semantic sense
    if count < 100:
        return "orm_artifact", "low"

    # Check if tables belong to different services
    owning_services = set()
    for t in tables:
        owner = table_owners.get(t)
        if owner:
            owning_services.add(owner)

    # Audit pattern: domain table + audit/log table
    audit_suffixes = ("_audit", "_log", "_history")
    non_audit = [t for t in tables if not any(t.endswith(s) for s in audit_suffixes)]
    audit = [t for t in tables if any(t.endswith(s) for s in audit_suffixes)]
    if len(non_audit) == 1 and audit:
        return "audit_pattern", "low"

    # Cross-context: tables from different services
    if len(owning_services) > 1:
        severity = "critical" if count > 1000 else "high" if count > 100 else "medium"
        return "cross_context", severity

    # Without table ownership data, use naming heuristics to detect cross-context writes.
    # Key insight: if all tables share a common naming root, they're likely the same context.
    # If tables have clearly different roots (orders vs shipments, orders vs inventory), it's cross-context.
    domain_roots = set()
    child_suffixes_all = ("_lines", "_items", "_events", "_audit", "_history", "_log",
                          "_status", "_reserved", "_levels", "_ledger")
    for t in tables:
        root = t
        for suffix in child_suffixes_all:
            if root.endswith(suffix):
                root = root[:-len(suffix)]
                break
        # Normalize: strip trailing 's' for basic depluralization
        if root.endswith("s") and len(root) > 3:
            root = root[:-1]
        domain_roots.add(root)

    # Check if roots share a common ancestor: if any root is a prefix of another,
    # or if they share 4+ character prefix, treat as same domain
    independent_roots = _find_independent_roots(domain_roots)

    if len(independent_roots) > 1 and len(tables) > 1:
        # High-frequency co-writes (>10K) from the same service are likely intentional aggregates
        # even if naming suggests different domains. The developer chose to commit them together.
        # Only flag as cross-context if frequency is moderate (the boundary violation signal).
        if count >= 10000:
            # Trust the developer's consistency choice at high frequency
            return "clean_aggregate", "low"
        severity = "high" if count > 1000 else "medium"
        return "distributed_concern", severity

    # Duration check
    if duration_ms > 200:
        return "slow_transaction", "high"

    # Clean aggregate: high frequency, single service, related tables
    if count >= 1000:
        return "clean_aggregate", "low"

    return "unclassified", "medium"


def _find_independent_roots(roots: set[str]) -> set[str]:
    """Find truly independent domain roots, collapsing related ones.

    Rules:
    - If one root is a prefix of another, keep only the shorter (parent)
    - If two roots share no meaningful overlap, they're independent
    - Single root = definitely one domain
    """
    if len(roots) <= 1:
        return roots

    sorted_roots = sorted(roots, key=len)
    independent: set[str] = set()

    for root in sorted_roots:
        # Check if this root is already covered by an existing independent root
        covered = False
        for existing in list(independent):
            # One is prefix of the other, or they share significant overlap
            if root.startswith(existing) or existing.startswith(root):
                covered = True
                # Keep the shorter one
                if len(root) < len(existing):
                    independent.discard(existing)
                    independent.add(root)
                break
        if not covered:
            independent.add(root)

    return independent


def _identify_root(tables: list[str]) -> str:
    """Identify the likely aggregate root from a set of tables."""
    # Heuristic: the table without a plural suffix or the shortest name is often the root
    # Or: the table that doesn't look like a child (no _lines, _items, _events, _audit suffix)
    child_suffixes = ("_lines", "_items", "_events", "_audit", "_history", "_log", "_status")
    candidates = [t for t in tables if not any(t.endswith(s) for s in child_suffixes)]
    if candidates:
        return min(candidates, key=len)
    return tables[0]


def _build_aggregates(clusters: list[TransactionCluster]) -> list[AggregateCandidate]:
    """Build aggregate candidates from clean clusters."""
    aggregates: list[AggregateCandidate] = []

    for c in clusters:
        if c.classification not in ("clean_aggregate", "audit_pattern"):
            continue

        children = [t for t in c.tables if t != c.root_table]
        aggregates.append(AggregateCandidate(
            root=c.root_table,
            children=children,
            service=c.service,
            total_occurrences=c.occurrence_count,
            confidence="high" if c.occurrence_count > 10000 else "medium" if c.occurrence_count > 1000 else "low",
        ))

    return aggregates


def _assess_extraction(clusters: list[TransactionCluster]) -> list[ExtractionReadiness]:
    """Assess extraction readiness per service."""
    service_data: dict[str, dict] = defaultdict(lambda: {
        "clean": 0, "cross": 0, "cross_freq": 0, "issues": [],
    })

    for c in clusters:
        if c.classification in ("clean_aggregate", "audit_pattern"):
            service_data[c.service]["clean"] += 1
        elif c.classification in ("cross_context", "distributed_concern"):
            service_data[c.service]["cross"] += 1
            service_data[c.service]["cross_freq"] += c.occurrence_count
            service_data[c.service]["issues"].append(
                f"{','.join(c.tables)} ({c.occurrence_count}/week)"
            )
        elif c.classification == "slow_transaction":
            service_data[c.service]["cross"] += 1
            service_data[c.service]["cross_freq"] += c.occurrence_count
            service_data[c.service]["issues"].append(
                f"{','.join(c.tables)} ({c.occurrence_count}/week, {c.avg_duration_ms}ms)"
            )

    readiness: list[ExtractionReadiness] = []
    for service, data in sorted(service_data.items()):
        if data["cross"] == 0:
            status = "ready"
            details = "All transaction clusters are internal"
        elif data["cross_freq"] < 1000:
            status = "extractable_with_work"
            details = f"Low-frequency cross-context: {'; '.join(data['issues'])}"
        elif data["cross"] <= 2:
            status = "blocked"
            details = f"High-frequency violations: {'; '.join(data['issues'])}"
        else:
            status = "entangled"
            details = f"Multiple violations: {'; '.join(data['issues'])}"

        readiness.append(ExtractionReadiness(
            service=service,
            status=status,
            clean_clusters=data["clean"],
            cross_context_clusters=data["cross"],
            cross_context_frequency=data["cross_freq"],
            details=details,
        ))

    return readiness


def _extract_table_owners(schema_data: dict | list) -> dict[str, str]:
    """Extract table ownership from Exhibit B schema archaeology output."""
    owners: dict[str, str] = {}
    shared_tables = schema_data if isinstance(schema_data, list) else schema_data.get("shared_tables", [])
    for st in shared_tables:
        table = st.get("table", "")
        writers = st.get("writers", [])
        if writers:
            owners[table] = writers[0]  # First writer = primary owner
    return owners
