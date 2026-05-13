"""Parser for GraphQL SDL schema files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graphql import build_schema, parse
from graphql.language.ast import (
    DocumentNode,
    EnumTypeDefinitionNode,
    FieldDefinitionNode,
    InputObjectTypeDefinitionNode,
    ObjectTypeDefinitionNode,
)

from ddd_archaeology.models import ContractInfo, ContractType, FieldInfo


def is_graphql(file_path: str) -> bool:
    """Check if a file is a GraphQL schema by extension."""
    return file_path.endswith(".graphql") or file_path.endswith(".gql")


def parse_contract_info(sdl: str, file_path: str) -> ContractInfo:
    """Extract contract metadata from a GraphQL SDL file."""
    doc = parse(sdl)

    type_count = 0
    query_count = 0
    mutation_count = 0

    for defn in doc.definitions:
        if isinstance(defn, ObjectTypeDefinitionNode):
            if defn.name.value == "Query":
                query_count = len(defn.fields) if defn.fields else 0
            elif defn.name.value == "Mutation":
                mutation_count = len(defn.fields) if defn.fields else 0
            else:
                type_count += 1
        elif isinstance(defn, (InputObjectTypeDefinitionNode, EnumTypeDefinitionNode)):
            type_count += 1

    return ContractInfo(
        file_path=file_path,
        contract_type=ContractType.GRAPHQL,
        service_name=_infer_service_name(file_path),
        owning_team="Unknown",
        version="n/a",
        operation_count=query_count + mutation_count,
        schema_count=type_count,
        raw={"sdl": sdl},
    )


def extract_types(sdl: str) -> dict[str, list[FieldInfo]]:
    """Extract all object types and their fields from GraphQL SDL."""
    doc = parse(sdl)
    types: dict[str, list[FieldInfo]] = {}

    for defn in doc.definitions:
        if isinstance(defn, ObjectTypeDefinitionNode):
            name = defn.name.value
            if name in ("Query", "Mutation", "Subscription"):
                continue
            fields = _extract_fields(defn)
            types[name] = fields

    return types


def extract_queries(sdl: str) -> list[str]:
    """Extract query operation names."""
    doc = parse(sdl)
    for defn in doc.definitions:
        if isinstance(defn, ObjectTypeDefinitionNode) and defn.name.value == "Query":
            return [f.name.value for f in (defn.fields or [])]
    return []


def extract_mutations(sdl: str) -> list[str]:
    """Extract mutation operation names."""
    doc = parse(sdl)
    for defn in doc.definitions:
        if isinstance(defn, ObjectTypeDefinitionNode) and defn.name.value == "Mutation":
            return [f.name.value for f in (defn.fields or [])]
    return []


def extract_enums(sdl: str) -> dict[str, list[str]]:
    """Extract enum types and their values."""
    doc = parse(sdl)
    enums: dict[str, list[str]] = {}
    for defn in doc.definitions:
        if isinstance(defn, EnumTypeDefinitionNode):
            enums[defn.name.value] = [v.name.value for v in (defn.values or [])]
    return enums


def _extract_fields(defn: ObjectTypeDefinitionNode) -> list[FieldInfo]:
    """Extract fields from a GraphQL type definition."""
    fields: list[FieldInfo] = []
    for f in defn.fields or []:
        field_type = _type_to_string(f.type)
        is_required = field_type.endswith("!")
        is_ref = not _is_scalar(field_type.rstrip("!").rstrip("]").lstrip("["))

        fields.append(FieldInfo(
            name=f.name.value,
            field_type=field_type,
            required=is_required,
            is_ref=is_ref,
            ref_target=_extract_type_name(f.type) if is_ref else None,
        ))
    return fields


def _type_to_string(type_node: Any) -> str:
    """Convert a GraphQL type AST node to a string representation."""
    from graphql.language.ast import ListTypeNode, NamedTypeNode, NonNullTypeNode

    if isinstance(type_node, NonNullTypeNode):
        return f"{_type_to_string(type_node.type)}!"
    if isinstance(type_node, ListTypeNode):
        return f"[{_type_to_string(type_node.type)}]"
    if isinstance(type_node, NamedTypeNode):
        return type_node.name.value
    return "Unknown"


def _extract_type_name(type_node: Any) -> str:
    """Extract the base type name from a potentially wrapped type."""
    from graphql.language.ast import ListTypeNode, NamedTypeNode, NonNullTypeNode

    if isinstance(type_node, (NonNullTypeNode, ListTypeNode)):
        return _extract_type_name(type_node.type)
    if isinstance(type_node, NamedTypeNode):
        return type_node.name.value
    return "Unknown"


_SCALARS = {"String", "Int", "Float", "Boolean", "ID", "DateTime", "Date"}


def _is_scalar(type_name: str) -> bool:
    """Check if a type name is a scalar."""
    return type_name in _SCALARS


def _infer_service_name(file_path: str) -> str:
    """Infer a service name from the file name."""
    stem = Path(file_path).stem
    return stem.replace("-", " ").replace("_", " ").title()
