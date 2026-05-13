"""Shared data models for DDD Archaeology pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContractType(str, Enum):
    OPENAPI = "openapi"
    ASYNCAPI = "asyncapi"
    GRAPHQL = "graphql"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    VERY_LOW = "Very Low"
    UNKNOWN = "Unknown"


class EntityType(str, Enum):
    ENTITY = "Entity"
    VALUE_OBJECT = "Value Object"
    AGGREGATE_ROOT = "Aggregate Root"
    DOMAIN_EVENT = "Domain Event"
    DTO = "DTO"


class CouplingType(str, Enum):
    ID_REFERENCE = "id_reference"
    SCHEMA_DUPLICATION = "schema_duplication"
    EVENT_PUBLISH = "event_publish"
    EVENT_SUBSCRIBE = "event_subscribe"


@dataclass
class ContractInfo:
    """Metadata about a single contract file."""

    file_path: str
    contract_type: ContractType
    service_name: str
    owning_team: str
    version: str
    endpoint_count: int = 0
    channel_count: int = 0
    operation_count: int = 0
    schema_count: int = 0
    last_modified: str | None = None
    confidence: Confidence = Confidence.UNKNOWN
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class VocabularyEntry:
    """A single domain term extracted from a contract."""

    term: str
    source_service: str
    source_file: str
    term_type: str  # schema, field, enum, path_resource, channel, event, query, mutation
    parent_schema: str | None = None
    is_deprecated: bool = False


@dataclass
class EntityInfo:
    """A discovered entity/VO/aggregate from contracts."""

    name: str
    entity_type: EntityType
    owning_service: str
    fields: list[FieldInfo] = field(default_factory=list)
    referenced_by: list[str] = field(default_factory=list)
    source_file: str = ""


@dataclass
class FieldInfo:
    """A field within an entity schema."""

    name: str
    field_type: str
    required: bool = False
    is_deprecated: bool = False
    is_ref: bool = False
    ref_target: str | None = None
    enum_values: list[str] | None = None


@dataclass
class CouplingEdge:
    """A coupling relationship between two services."""

    source_service: str
    target_service: str
    coupling_type: CouplingType
    evidence: str  # e.g., "buyerId field in Order schema"
    field_name: str | None = None
