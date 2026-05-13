"""Parser for OpenAPI 3.x specs."""

from __future__ import annotations

from typing import Any

from ddd_archaeology.models import ContractInfo, ContractType, EntityType, FieldInfo


def is_openapi(data: dict[str, Any]) -> bool:
    """Check if a parsed YAML/JSON document is an OpenAPI spec."""
    return "openapi" in data and data.get("openapi", "").startswith("3.")


def parse_contract_info(data: dict[str, Any], file_path: str) -> ContractInfo:
    """Extract contract metadata from an OpenAPI spec."""
    info = data.get("info", {})
    contact = info.get("contact", {})
    paths = data.get("paths", {})

    endpoint_count = 0
    for path_methods in paths.values():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method in path_methods:
                endpoint_count += 1

    schemas = data.get("components", {}).get("schemas", {})

    return ContractInfo(
        file_path=file_path,
        contract_type=ContractType.OPENAPI,
        service_name=info.get("title", "Unknown"),
        owning_team=contact.get("name", "Unknown"),
        version=info.get("version", "0.0.0"),
        endpoint_count=endpoint_count,
        schema_count=len(schemas),
        raw=data,
    )


def extract_path_resources(data: dict[str, Any]) -> list[str]:
    """Extract resource names from API path segments."""
    resources: list[str] = []
    for path in data.get("paths", {}):
        segments = [s for s in path.split("/") if s and not s.startswith("{") and s != "api" and not s.startswith("v")]
        resources.extend(segments)
    return list(set(resources))


def extract_schemas(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract all component schemas."""
    return data.get("components", {}).get("schemas", {})


def extract_fields(schema: dict[str, Any]) -> list[FieldInfo]:
    """Extract fields from an OpenAPI schema object."""
    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    fields: list[FieldInfo] = []

    for name, prop in props.items():
        is_ref = "$ref" in prop
        ref_target = None
        if is_ref:
            ref_target = prop["$ref"].split("/")[-1]

        field_type = prop.get("type", "object")
        if is_ref:
            field_type = ref_target or "object"
        elif prop.get("type") == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                ref_target = items["$ref"].split("/")[-1]
                field_type = f"array<{ref_target}>"
                is_ref = True
            else:
                field_type = f"array<{items.get('type', 'object')}>"

        fields.append(FieldInfo(
            name=name,
            field_type=field_type,
            required=name in required_fields,
            is_deprecated=prop.get("deprecated", False),
            is_ref=is_ref,
            ref_target=ref_target,
            enum_values=prop.get("enum"),
        ))

    return fields


def classify_entity_type(
    schema_name: str,
    data: dict[str, Any],
) -> EntityType:
    """Classify a schema as Entity, VO, or Aggregate Root based on path patterns."""
    paths = data.get("paths", {})

    has_crud = False
    has_sub_resources = False

    for path in paths:
        segments = path.rstrip("/").split("/")
        resource_segments = [s for s in segments if not s.startswith("{") and s != "api" and not s.startswith("v") and s]

        if not resource_segments:
            continue

        # Check if this schema's name (lowered) matches a path resource
        schema_lower = schema_name.lower()
        for seg in resource_segments:
            if schema_lower in seg.lower() or seg.lower() in schema_lower:
                has_crud = True

        # Check for sub-resources like /orders/{id}/lines
        if len(resource_segments) >= 2:
            for i, seg in enumerate(resource_segments[:-1]):
                if schema_lower in seg.lower():
                    has_sub_resources = True

    if has_sub_resources:
        return EntityType.AGGREGATE_ROOT
    if has_crud:
        return EntityType.ENTITY
    return EntityType.VALUE_OBJECT


def get_http_method_distribution(data: dict[str, Any]) -> dict[str, int]:
    """Count HTTP methods across all endpoints."""
    distribution: dict[str, int] = {}
    for path_methods in data.get("paths", {}).values():
        for method in ("get", "post", "put", "patch", "delete"):
            if method in path_methods:
                distribution[method] = distribution.get(method, 0) + 1
    return distribution
