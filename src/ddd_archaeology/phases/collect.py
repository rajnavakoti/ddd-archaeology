"""Phase 1: Collect contracts and build inventory."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import yaml

from ddd_archaeology.models import Confidence, ContractInfo, ContractType
from ddd_archaeology.output.writer import print_table, write_json
from ddd_archaeology.parsers import asyncapi, openapi
from ddd_archaeology.parsers.graphql_parser import is_graphql, parse_contract_info as parse_gql


def run(args: argparse.Namespace) -> int:
    """Scan directory for contracts and output inventory."""
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        return 1

    contracts = collect_contracts(directory)

    if not contracts:
        print(f"No contracts found in {directory}")
        return 1

    print(f"\n  Found {len(contracts)} contracts in {directory}\n")

    rows = []
    for c in contracts:
        count_label = _count_label(c)
        rows.append([
            c.service_name,
            c.owning_team,
            c.version,
            c.contract_type.value,
            count_label,
            str(c.schema_count),
            c.last_modified or "unknown",
            c.confidence.value,
        ])

    print_table(
        ["Service", "Team", "Version", "Type", "Endpoints/Channels", "Schemas", "Last Modified", "Confidence"],
        rows,
    )

    write_json(contracts, args.output)
    print(f"\n  Inventory written to {args.output}")

    return 0


def collect_contracts(directory: Path) -> list[ContractInfo]:
    """Scan directory for OpenAPI, AsyncAPI, and GraphQL files."""
    contracts: list[ContractInfo] = []

    for file_path in sorted(directory.rglob("*")):
        if file_path.is_dir():
            continue

        contract = _try_parse(file_path)
        if contract:
            contract.last_modified = _get_last_modified(file_path)
            contract.confidence = _score_confidence(contract.last_modified)
            contracts.append(contract)

    return contracts


def _try_parse(file_path: Path) -> ContractInfo | None:
    """Attempt to parse a file as a known contract type."""
    path_str = str(file_path)

    # GraphQL by extension
    if is_graphql(path_str):
        try:
            sdl = file_path.read_text()
            return parse_gql(sdl, path_str)
        except Exception:
            return None

    # YAML/JSON — could be OpenAPI or AsyncAPI
    if file_path.suffix in (".yaml", ".yml", ".json"):
        try:
            data = yaml.safe_load(file_path.read_text())
            if not isinstance(data, dict):
                return None

            if openapi.is_openapi(data):
                return openapi.parse_contract_info(data, path_str)
            if asyncapi.is_asyncapi(data):
                return asyncapi.parse_contract_info(data, path_str)
        except Exception:
            return None

    return None


def _get_last_modified(file_path: Path) -> str | None:
    """Get the last git commit date for a file, or fall back to mtime."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", str(file_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to filesystem mtime
    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _score_confidence(last_modified: str | None) -> Confidence:
    """Score confidence based on how recently the contract was modified."""
    if not last_modified:
        return Confidence.UNKNOWN

    try:
        modified_dt = datetime.fromisoformat(last_modified)
        now = datetime.now(timezone.utc)
        days_ago = (now - modified_dt).days

        if days_ago <= 30:
            return Confidence.HIGH
        if days_ago <= 90:
            return Confidence.MEDIUM
        if days_ago <= 365:
            return Confidence.LOW
        return Confidence.VERY_LOW
    except (ValueError, TypeError):
        return Confidence.UNKNOWN


def _count_label(contract: ContractInfo) -> str:
    """Build a human-readable count label for endpoints/channels/operations."""
    if contract.contract_type == ContractType.OPENAPI:
        return str(contract.endpoint_count)
    if contract.contract_type == ContractType.ASYNCAPI:
        return str(contract.channel_count)
    if contract.contract_type == ContractType.GRAPHQL:
        return str(contract.operation_count)
    return "0"
