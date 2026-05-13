"""Phase 2: Extract domain vocabulary from contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ddd_archaeology.models import ContractType, VocabularyEntry
from ddd_archaeology.output.writer import print_table, write_json
from ddd_archaeology.parsers import asyncapi, openapi
from ddd_archaeology.parsers.graphql_parser import (
    extract_enums,
    extract_mutations,
    extract_queries,
    extract_types,
)


def run(args: argparse.Namespace) -> int:
    """Extract vocabulary from inventory."""
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"Error: {inventory_path} not found")
        return 1

    inventory = json.loads(inventory_path.read_text())
    entries = extract_vocabulary(inventory)

    if not entries:
        print("No vocabulary extracted")
        return 1

    # Summary by service
    by_service: dict[str, int] = {}
    by_type: dict[str, int] = {}
    deprecated_count = 0

    for e in entries:
        by_service[e.source_service] = by_service.get(e.source_service, 0) + 1
        by_type[e.term_type] = by_type.get(e.term_type, 0) + 1
        if e.is_deprecated:
            deprecated_count += 1

    print(f"\n  Extracted {len(entries)} vocabulary terms ({deprecated_count} deprecated)\n")

    print("  By service:")
    rows = [[svc, str(count)] for svc, count in sorted(by_service.items())]
    print_table(["Service", "Terms"], rows)

    print("\n  By type:")
    rows = [[t, str(count)] for t, count in sorted(by_type.items())]
    print_table(["Type", "Count"], rows)

    write_json(entries, args.output)
    print(f"\n  Vocabulary written to {args.output}")

    return 0


def extract_vocabulary(inventory: list[dict]) -> list[VocabularyEntry]:
    """Extract all vocabulary from an inventory of contracts."""
    entries: list[VocabularyEntry] = []

    for contract in inventory:
        file_path = contract["file_path"]
        service = contract["service_name"]
        contract_type = contract["contract_type"]

        if contract_type == ContractType.OPENAPI.value:
            entries.extend(_extract_openapi_vocab(file_path, service))
        elif contract_type == ContractType.ASYNCAPI.value:
            entries.extend(_extract_asyncapi_vocab(file_path, service))
        elif contract_type == ContractType.GRAPHQL.value:
            entries.extend(_extract_graphql_vocab(file_path, service))

    return entries


def _extract_openapi_vocab(file_path: str, service: str) -> list[VocabularyEntry]:
    """Extract vocabulary from an OpenAPI spec."""
    data = yaml.safe_load(Path(file_path).read_text())
    entries: list[VocabularyEntry] = []

    # Path resources
    for resource in openapi.extract_path_resources(data):
        entries.append(VocabularyEntry(
            term=resource,
            source_service=service,
            source_file=file_path,
            term_type="path_resource",
        ))

    # Schemas and their fields
    schemas = openapi.extract_schemas(data)
    for schema_name, schema in schemas.items():
        entries.append(VocabularyEntry(
            term=schema_name,
            source_service=service,
            source_file=file_path,
            term_type="schema",
        ))

        fields = openapi.extract_fields(schema)
        for field in fields:
            entries.append(VocabularyEntry(
                term=field.name,
                source_service=service,
                source_file=file_path,
                term_type="field",
                parent_schema=schema_name,
                is_deprecated=field.is_deprecated,
            ))

            if field.enum_values:
                for val in field.enum_values:
                    entries.append(VocabularyEntry(
                        term=val,
                        source_service=service,
                        source_file=file_path,
                        term_type="enum",
                        parent_schema=schema_name,
                    ))

    return entries


def _extract_asyncapi_vocab(file_path: str, service: str) -> list[VocabularyEntry]:
    """Extract vocabulary from an AsyncAPI spec."""
    data = yaml.safe_load(Path(file_path).read_text())
    entries: list[VocabularyEntry] = []

    # Channels
    for channel in asyncapi.extract_channels(data):
        entries.append(VocabularyEntry(
            term=channel,
            source_service=service,
            source_file=file_path,
            term_type="channel",
        ))

    # Channel prefixes (bounded context candidates)
    for prefix in asyncapi.extract_channel_prefixes(data):
        entries.append(VocabularyEntry(
            term=prefix,
            source_service=service,
            source_file=file_path,
            term_type="channel_prefix",
        ))

    # Event names
    for event in asyncapi.extract_event_names(data):
        entries.append(VocabularyEntry(
            term=event,
            source_service=service,
            source_file=file_path,
            term_type="event",
        ))

    # Event payload fields
    messages = data.get("components", {}).get("messages", {})
    for msg_name, msg in messages.items():
        fields = asyncapi.extract_event_payload_fields(msg)
        for field in fields:
            entries.append(VocabularyEntry(
                term=field.name,
                source_service=service,
                source_file=file_path,
                term_type="field",
                parent_schema=msg_name,
                is_deprecated=field.is_deprecated,
            ))

            if field.enum_values:
                for val in field.enum_values:
                    entries.append(VocabularyEntry(
                        term=val,
                        source_service=service,
                        source_file=file_path,
                        term_type="enum",
                        parent_schema=msg_name,
                    ))

    # Schemas
    schemas = asyncapi.extract_schemas(data)
    for schema_name, schema in schemas.items():
        # Skip messages already processed above
        if schema_name in messages:
            continue
        entries.append(VocabularyEntry(
            term=schema_name,
            source_service=service,
            source_file=file_path,
            term_type="schema",
        ))

    return entries


def _extract_graphql_vocab(file_path: str, service: str) -> list[VocabularyEntry]:
    """Extract vocabulary from a GraphQL SDL file."""
    sdl = Path(file_path).read_text()
    entries: list[VocabularyEntry] = []

    # Types and their fields
    types = extract_types(sdl)
    for type_name, fields in types.items():
        entries.append(VocabularyEntry(
            term=type_name,
            source_service=service,
            source_file=file_path,
            term_type="schema",
        ))

        for field in fields:
            entries.append(VocabularyEntry(
                term=field.name,
                source_service=service,
                source_file=file_path,
                term_type="field",
                parent_schema=type_name,
            ))

    # Queries
    for query in extract_queries(sdl):
        entries.append(VocabularyEntry(
            term=query,
            source_service=service,
            source_file=file_path,
            term_type="query",
        ))

    # Mutations
    for mutation in extract_mutations(sdl):
        entries.append(VocabularyEntry(
            term=mutation,
            source_service=service,
            source_file=file_path,
            term_type="mutation",
        ))

    # Enums
    enums = extract_enums(sdl)
    for enum_name, values in enums.items():
        entries.append(VocabularyEntry(
            term=enum_name,
            source_service=service,
            source_file=file_path,
            term_type="schema",
        ))
        for val in values:
            entries.append(VocabularyEntry(
                term=val,
                source_service=service,
                source_file=file_path,
                term_type="enum",
                parent_schema=enum_name,
            ))

    return entries
