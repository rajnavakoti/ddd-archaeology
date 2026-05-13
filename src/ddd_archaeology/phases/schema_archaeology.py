"""Exhibit B: Schema Archaeology — find shared tables and boundary violations."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class TableAccess:
    """Access pattern for a single table by a single service."""

    table: str
    service: str
    db_user: str
    access_type: str  # READ or WRITE
    daily_queries: int = 0


@dataclass
class SharedTable:
    """A table accessed by multiple services."""

    table: str
    service_count: int
    readers: list[str] = field(default_factory=list)
    writers: list[str] = field(default_factory=list)
    total_daily_queries: int = 0
    classification: str = ""  # single_writer_multi_reader, multi_writer, all_readers
    severity: str = ""  # critical, high, medium, low


@dataclass
class SchemaSignal:
    """A signal found in the DDL analysis."""

    signal_type: str  # fat_table, cross_boundary_fk, lifecycle_timestamps, namespace_violation, index_fossil, ghost_user
    table: str
    detail: str
    severity: str = "medium"


@dataclass
class SchemaArchaeologyResult:
    """Full output of Exhibit B analysis."""

    shared_tables: list[SharedTable] = field(default_factory=list)
    schema_signals: list[SchemaSignal] = field(default_factory=list)
    ghost_users: list[str] = field(default_factory=list)
    service_user_map: dict[str, str] = field(default_factory=dict)


def run(args: argparse.Namespace) -> int:
    """Analyze database schema and access patterns."""
    access_log_path = Path(args.access_log)
    service_users_path = Path(args.service_users)

    if not access_log_path.exists():
        print(f"Error: {access_log_path} not found")
        return 1
    if not service_users_path.exists():
        print(f"Error: {service_users_path} not found")
        return 1

    access_log = json.loads(access_log_path.read_text())
    service_users = json.loads(service_users_path.read_text())

    result = analyze_schema(access_log, service_users)

    # Optional: DDL analysis
    if args.schema_sql:
        schema_path = Path(args.schema_sql)
        if schema_path.exists():
            ddl = schema_path.read_text()
            ddl_signals = analyze_ddl(ddl)
            result.schema_signals.extend(ddl_signals)

    # Print results
    print(f"\n  ═══ SCHEMA ARCHAEOLOGY RESULTS ═══\n")

    # Ghost users
    if result.ghost_users:
        print(f"  ⚠ Ghost database users (no known service):")
        for gu in result.ghost_users:
            print(f"    • {gu}")
        print()

    # Shared tables
    print(f"  Found {len(result.shared_tables)} shared tables\n")
    rows = []
    for st in sorted(result.shared_tables, key=lambda x: (-len(x.writers), -x.service_count)):
        writers = ", ".join(st.writers) if st.writers else "—"
        readers = ", ".join(st.readers) if st.readers else "—"
        rows.append([st.table, str(st.service_count), writers, readers, st.classification, st.severity])
    print_table(["Table", "Services", "Writers", "Readers", "Pattern", "Severity"], rows)

    # Schema signals
    if result.schema_signals:
        print(f"\n  Schema signals ({len(result.schema_signals)}):\n")
        for sig in result.schema_signals:
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(sig.severity, "·")
            print(f"    {icon} [{sig.signal_type}] {sig.table}: {sig.detail}")

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_schema(
    access_log: list[dict],
    service_users: dict[str, dict],
) -> SchemaArchaeologyResult:
    """Analyze access patterns to find shared tables and boundary violations."""
    result = SchemaArchaeologyResult()

    # Build service user map
    user_to_service: dict[str, str] = {}
    for db_user, info in service_users.items():
        user_to_service[db_user] = info.get("service", db_user)
        result.service_user_map[db_user] = info.get("service", db_user)
        if info.get("status") == "ghost":
            result.ghost_users.append(db_user)

    # Parse access log into structured data
    accesses: list[TableAccess] = []
    for entry in access_log:
        service = user_to_service.get(entry["db_user"], entry["db_user"])
        accesses.append(TableAccess(
            table=entry["table"],
            service=service,
            db_user=entry["db_user"],
            access_type=entry["access_type"],
            daily_queries=entry.get("daily_queries", 0),
        ))

    # Group by table
    table_services: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"readers": set(), "writers": set()})
    table_queries: dict[str, int] = defaultdict(int)

    for a in accesses:
        if a.access_type == "READ":
            table_services[a.table]["readers"].add(a.service)
        elif a.access_type == "WRITE":
            table_services[a.table]["writers"].add(a.service)
        table_queries[a.table] += a.daily_queries

    # Find shared tables (2+ distinct services)
    for table, services in sorted(table_services.items()):
        all_services = services["readers"] | services["writers"]
        if len(all_services) < 2:
            continue

        writers = sorted(services["writers"])
        readers = sorted(services["readers"] - services["writers"])

        # Classify
        if len(writers) >= 2:
            classification = "multi_writer"
            severity = "critical"
        elif len(writers) == 1 and readers:
            classification = "single_writer_multi_reader"
            severity = "high" if len(readers) >= 2 else "medium"
        elif len(writers) == 0:
            classification = "all_readers"
            severity = "low"
        else:
            classification = "single_service"
            severity = "low"

        result.shared_tables.append(SharedTable(
            table=table,
            service_count=len(all_services),
            readers=readers,
            writers=writers,
            total_daily_queries=table_queries[table],
            classification=classification,
            severity=severity,
        ))

    return result


def analyze_ddl(ddl: str) -> list[SchemaSignal]:
    """Analyze DDL for domain signals."""
    signals: list[SchemaSignal] = []

    # Find CREATE TABLE blocks
    table_blocks = re.findall(
        r'CREATE TABLE\s+(\w+)\s*\((.*?)\);',
        ddl,
        re.DOTALL | re.IGNORECASE,
    )

    for table_name, body in table_blocks:
        # Split on newlines, not commas — SQL columns span lines with comments
        columns = [line.strip().rstrip(",") for line in body.split("\n") if line.strip() and not line.strip().startswith("--")]

        # Fat table detection (count actual columns, not constraints)
        col_count = sum(
            1 for c in columns
            if not c.upper().startswith(("PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN KEY", "CONSTRAINT"))
        )
        if col_count >= 25:
            signals.append(SchemaSignal(
                signal_type="fat_table",
                table=table_name,
                detail=f"{col_count} columns — god entity at persistence layer, never properly decomposed",
                severity="high",
            ))

        # Lifecycle timestamp detection
        timestamp_cols = [
            c.split()[0] for c in columns
            if re.search(r'\w+_at\b', c.split()[0] if c.split() else "", re.IGNORECASE)
            and c.split()[0].lower() not in ("created_at", "updated_at")
        ]
        if len(timestamp_cols) >= 2:
            signals.append(SchemaSignal(
                signal_type="lifecycle_timestamps",
                table=table_name,
                detail=f"Implicit domain events: {', '.join(timestamp_cols)} — state changes tracked but not announced",
                severity="medium",
            ))

        # Cross-boundary FK detection (comments indicating cross-boundary)
        for col_line in columns:
            if "cross-boundary" in col_line.lower():
                col_name = col_line.strip().split()[0]
                signals.append(SchemaSignal(
                    signal_type="cross_boundary_fk",
                    table=table_name,
                    detail=f"Column {col_name} references another service's table",
                    severity="high",
                ))

    # Index fossil detection
    index_matches = re.findall(
        r'CREATE INDEX\s+(\w+)\s+ON\s+(\w+)\((\w+)\)',
        ddl,
        re.IGNORECASE,
    )
    # Group indexes by table
    table_indexes: dict[str, list[str]] = defaultdict(list)
    for idx_name, table, column in index_matches:
        table_indexes[table].append(column)

    for table, columns in table_indexes.items():
        id_columns = [c for c in columns if c.endswith("_id") and c not in ("order_id",)]
        if len(id_columns) >= 3:
            signals.append(SchemaSignal(
                signal_type="index_fossil",
                table=table,
                detail=f"Indexes on {', '.join(id_columns)} — fossils of cross-service query patterns",
                severity="medium",
            ))

    return signals
