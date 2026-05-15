"""CLI entry point for ddd-archaeology: python -m ddd_archaeology <command>."""

import argparse
import sys

from ddd_archaeology.phases.collect import run as run_collect
from ddd_archaeology.phases.extract_vocab import run as run_extract_vocab
from ddd_archaeology.phases.discover_entities import run as run_discover_entities
from ddd_archaeology.phases.compare import run as run_compare
from ddd_archaeology.phases.analyze_coupling import run as run_coupling
from ddd_archaeology.phases.schema_archaeology import run as run_schema
from ddd_archaeology.phases.transaction_boundaries import run as run_transactions
from ddd_archaeology.phases.log_mining import run as run_logs
from ddd_archaeology.phases.incident_clustering import run as run_incidents
from ddd_archaeology.phases.data_lineage import run as run_lineage
from ddd_archaeology.phases.error_codes import run as run_errors


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ddd-archaeology",
        description="Reverse-engineer DDD bounded contexts from API contracts",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Phase 1: collect
    p_collect = sub.add_parser("collect", help="Phase 1 — scan directory for contracts, build inventory")
    p_collect.add_argument("directory", help="Directory containing contract files")
    p_collect.add_argument("--output", "-o", default="output/inventory.json", help="Output path for inventory JSON")

    # Phase 2: extract-vocab
    p_vocab = sub.add_parser("extract-vocab", help="Phase 2 — extract domain vocabulary from contracts")
    p_vocab.add_argument("inventory", help="Path to inventory.json from Phase 1")
    p_vocab.add_argument("--output", "-o", default="output/vocabulary.json", help="Output path for vocabulary JSON")

    # Phase 3: discover-entities
    p_entities = sub.add_parser("discover-entities", help="Phase 3 — identify entities, VOs, aggregates")
    p_entities.add_argument("inventory", help="Path to inventory.json from Phase 1")
    p_entities.add_argument("--output", "-o", default="output/entities.json", help="Output path for entities JSON")

    # Phase 4-5: compare
    p_compare = sub.add_parser("compare", help="Phase 4-5 — cross-entity comparison and vocabulary consistency")
    p_compare.add_argument("entities", help="Path to entities.json from Phase 3")
    p_compare.add_argument("--output", "-o", default="output/comparison.json", help="Output path for comparison JSON")

    # Phase 6: analyze-coupling
    p_coupling = sub.add_parser("analyze-coupling", help="Phase 6 — coupling analysis with heatmap")
    p_coupling.add_argument("entities", help="Path to entities.json from Phase 3")
    p_coupling.add_argument("--output", "-o", default="output/coupling.json", help="Output path for coupling JSON")
    p_coupling.add_argument("--html", default="output/heatmap.html", help="Output path for heatmap HTML")

    # Exhibit B: schema-archaeology
    p_schema = sub.add_parser("schema-archaeology", help="Exhibit B — analyze database schema and access patterns")
    p_schema.add_argument("access_log", help="Path to access_log.json (table access patterns)")
    p_schema.add_argument("service_users", help="Path to service_users.json (db user → service mapping)")
    p_schema.add_argument("--schema-sql", default=None, help="Path to schema.sql for DDL analysis")
    p_schema.add_argument("--output", "-o", default="output/schema_archaeology.json", help="Output path")

    # Exhibit C: transaction-boundaries
    p_txn = sub.add_parser("transaction-boundaries", help="Exhibit C — analyze transaction co-write patterns")
    p_txn.add_argument("clusters", help="Path to transaction_clusters.json")
    p_txn.add_argument("--schema-archaeology", default=None, help="Path to schema_archaeology.json for table ownership")
    p_txn.add_argument("--output", "-o", default="output/transaction_boundaries.json", help="Output path")

    # Exhibit D: log-mining
    p_logs = sub.add_parser("log-mining", help="Exhibit D — recover fossilized domain events from logs")
    p_logs.add_argument("trace", help="Path to trace JSONL file (single entity flow)")
    p_logs.add_argument("--frequency", default=None, help="Path to event_frequency.json")
    p_logs.add_argument("--output", "-o", default="output/log_mining.json", help="Output path")

    # Exhibit G: error-codes
    p_errors = sub.add_parser("error-codes", help="Exhibit G — decode error codes into business rules")
    p_errors.add_argument("errors", help="Path to error_codes.json")
    p_errors.add_argument("--output", "-o", default="output/error_codes.json", help="Output path")

    # Exhibit F: data-lineage
    p_lineage = sub.add_parser("data-lineage", help="Exhibit F — trace entity copies and find divergence")
    p_lineage.add_argument("lineage", help="Path to data_lineage.json")
    p_lineage.add_argument("--output", "-o", default="output/data_lineage.json", help="Output path")

    # Exhibit E: incident-clustering
    p_inc = sub.add_parser("incident-clustering", help="Exhibit E — analyze incident patterns at boundaries")
    p_inc.add_argument("incidents", help="Path to incidents.json")
    p_inc.add_argument("--output", "-o", default="output/incident_clustering.json", help="Output path")

    args = parser.parse_args()

    commands = {
        "collect": run_collect,
        "extract-vocab": run_extract_vocab,
        "discover-entities": run_discover_entities,
        "compare": run_compare,
        "analyze-coupling": run_coupling,
        "schema-archaeology": run_schema,
        "transaction-boundaries": run_transactions,
        "log-mining": run_logs,
        "incident-clustering": run_incidents,
        "data-lineage": run_lineage,
        "error-codes": run_errors,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
