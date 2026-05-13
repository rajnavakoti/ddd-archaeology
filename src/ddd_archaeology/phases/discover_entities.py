"""Phase 3: Entity discovery and mapping."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ddd_archaeology.models import ContractType, EntityInfo, EntityType, FieldInfo
from ddd_archaeology.output.writer import print_table, write_json
from ddd_archaeology.parsers import asyncapi, openapi
from ddd_archaeology.parsers.graphql_parser import extract_types


def run(args: argparse.Namespace) -> int:
    """Discover entities from parsed contracts."""
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"Error: {inventory_path} not found")
        return 1

    inventory = json.loads(inventory_path.read_text())
    entities = discover_entities(inventory)

    if not entities:
        print("No entities discovered")
        return 1

    # Summary
    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e.entity_type.value] = by_type.get(e.entity_type.value, 0) + 1

    print(f"\n  Discovered {len(entities)} entities\n")

    print("  By type:")
    rows = [[t, str(c)] for t, c in sorted(by_type.items())]
    print_table(["Type", "Count"], rows)

    # Entity map: who owns what, who references what
    print("\n  Entity map:")
    entity_rows = []
    for e in sorted(entities, key=lambda x: x.name):
        refs = ", ".join(e.referenced_by) if e.referenced_by else "—"
        entity_rows.append([e.name, e.entity_type.value, e.owning_service, str(len(e.fields)), refs])
    print_table(["Entity", "Type", "Owner", "Fields", "Referenced By"], entity_rows)

    # HTTP method distribution per service
    print("\n  HTTP method distribution:")
    method_dist = _get_method_distribution(inventory)
    method_rows = []
    for svc, dist in sorted(method_dist.items()):
        methods = ", ".join(f"{m}:{c}" for m, c in sorted(dist.items()))
        is_read_only = set(dist.keys()) <= {"get", "head", "options"}
        flag = " ← READ-ONLY (not a domain service)" if is_read_only else ""
        method_rows.append([svc, methods + flag])
    print_table(["Service", "Methods"], method_rows)

    write_json(entities, args.output)
    print(f"\n  Entities written to {args.output}")

    return 0


def discover_entities(inventory: list[dict]) -> list[EntityInfo]:
    """Discover entities across all contracts in the inventory."""
    entities: list[EntityInfo] = []
    # Track which entity names appear in which services
    entity_services: dict[str, list[str]] = {}

    for contract in inventory:
        file_path = contract["file_path"]
        service = contract["service_name"]
        contract_type = contract["contract_type"]

        if contract_type == ContractType.OPENAPI.value:
            found = _discover_openapi_entities(file_path, service)
        elif contract_type == ContractType.ASYNCAPI.value:
            found = _discover_asyncapi_entities(file_path, service)
        elif contract_type == ContractType.GRAPHQL.value:
            found = _discover_graphql_entities(file_path, service)
        else:
            continue

        for entity in found:
            entities.append(entity)
            if entity.name not in entity_services:
                entity_services[entity.name] = []
            entity_services[entity.name].append(service)

    # Cross-reference: mark which services reference each entity
    for entity in entities:
        all_services = entity_services.get(entity.name, [])
        entity.referenced_by = [s for s in all_services if s != entity.owning_service]

    return entities


def _discover_openapi_entities(file_path: str, service: str) -> list[EntityInfo]:
    """Discover entities from an OpenAPI spec."""
    data = yaml.safe_load(Path(file_path).read_text())
    entities: list[EntityInfo] = []

    schemas = openapi.extract_schemas(data)
    for name, schema in schemas.items():
        entity_type = openapi.classify_entity_type(name, data)
        fields = openapi.extract_fields(schema)

        entities.append(EntityInfo(
            name=name,
            entity_type=entity_type,
            owning_service=service,
            fields=fields,
            source_file=file_path,
        ))

    return entities


def _discover_asyncapi_entities(file_path: str, service: str) -> list[EntityInfo]:
    """Discover domain events and schemas from AsyncAPI."""
    data = yaml.safe_load(Path(file_path).read_text())
    entities: list[EntityInfo] = []

    messages = data.get("components", {}).get("messages", {})
    for msg_name, msg in messages.items():
        fields = asyncapi.extract_event_payload_fields(msg)
        entities.append(EntityInfo(
            name=msg_name,
            entity_type=EntityType.DOMAIN_EVENT,
            owning_service=service,
            fields=fields,
            source_file=file_path,
        ))

    # Non-message schemas
    raw_schemas = data.get("components", {}).get("schemas", {})
    for name, schema in raw_schemas.items():
        fields_data = schema.get("properties", {})
        fields = [
            FieldInfo(
                name=fn,
                field_type=fp.get("type", "object"),
                required=fn in schema.get("required", []),
            )
            for fn, fp in fields_data.items()
        ]
        entities.append(EntityInfo(
            name=name,
            entity_type=EntityType.VALUE_OBJECT,
            owning_service=service,
            fields=fields,
            source_file=file_path,
        ))

    return entities


def _discover_graphql_entities(file_path: str, service: str) -> list[EntityInfo]:
    """Discover entities from GraphQL SDL."""
    sdl = Path(file_path).read_text()
    entities: list[EntityInfo] = []

    types = extract_types(sdl)
    for type_name, fields in types.items():
        # Simple heuristic: types with an 'id' field are likely Entities
        has_id = any(f.name == "id" for f in fields)
        entity_type = EntityType.ENTITY if has_id else EntityType.VALUE_OBJECT

        entities.append(EntityInfo(
            name=type_name,
            entity_type=entity_type,
            owning_service=service,
            fields=fields,
            source_file=file_path,
        ))

    return entities


def _get_method_distribution(inventory: list[dict]) -> dict[str, dict[str, int]]:
    """Get HTTP method distribution per service from OpenAPI specs."""
    dist: dict[str, dict[str, int]] = {}

    for contract in inventory:
        if contract["contract_type"] != ContractType.OPENAPI.value:
            continue

        data = yaml.safe_load(Path(contract["file_path"]).read_text())
        methods = openapi.get_http_method_distribution(data)
        if methods:
            dist[contract["service_name"]] = methods

    return dist
