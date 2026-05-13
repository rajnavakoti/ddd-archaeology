"""Parser for AsyncAPI 2.x specs."""

from __future__ import annotations

from typing import Any

from ddd_archaeology.models import ContractInfo, ContractType, FieldInfo


def is_asyncapi(data: dict[str, Any]) -> bool:
    """Check if a parsed YAML/JSON document is an AsyncAPI spec."""
    return "asyncapi" in data and data.get("asyncapi", "").startswith("2.")


def parse_contract_info(data: dict[str, Any], file_path: str) -> ContractInfo:
    """Extract contract metadata from an AsyncAPI spec."""
    info = data.get("info", {})
    contact = info.get("contact", {})
    channels = data.get("channels", {})

    schema_count = len(data.get("components", {}).get("schemas", {}))
    schema_count += len(data.get("components", {}).get("messages", {}))

    return ContractInfo(
        file_path=file_path,
        contract_type=ContractType.ASYNCAPI,
        service_name=info.get("title", "Unknown"),
        owning_team=contact.get("name", "Unknown"),
        version=info.get("version", "0.0.0"),
        channel_count=len(channels),
        schema_count=schema_count,
        raw=data,
    )


def extract_channels(data: dict[str, Any]) -> list[str]:
    """Extract channel/topic names."""
    return list(data.get("channels", {}).keys())


def extract_channel_prefixes(data: dict[str, Any]) -> list[str]:
    """Extract unique channel prefixes (candidate bounded contexts)."""
    prefixes: set[str] = set()
    for channel in data.get("channels", {}):
        parts = channel.split(".")
        if parts:
            prefixes.add(parts[0])
    return sorted(prefixes)


def extract_event_names(data: dict[str, Any]) -> list[str]:
    """Extract event type names from messages."""
    names: list[str] = []
    messages = data.get("components", {}).get("messages", {})
    for msg_name in messages:
        names.append(msg_name)
    return names


def extract_event_payload_fields(
    message: dict[str, Any],
) -> list[FieldInfo]:
    """Extract fields from an event message payload."""
    payload = message.get("payload", {})
    props = payload.get("properties", {})
    required_fields = set(payload.get("required", []))
    fields: list[FieldInfo] = []

    for name, prop in props.items():
        is_ref = "$ref" in prop
        ref_target = None
        if is_ref:
            ref_target = prop["$ref"].split("/")[-1]

        field_type = prop.get("type", "object")
        if is_ref:
            field_type = ref_target or "object"

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


def extract_schemas(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract component schemas and message payloads."""
    schemas = dict(data.get("components", {}).get("schemas", {}))
    for msg_name, msg in data.get("components", {}).get("messages", {}).items():
        if "payload" in msg:
            schemas[msg_name] = msg["payload"]
    return schemas
