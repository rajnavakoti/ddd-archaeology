"""Phase 4-5: Cross-entity comparison and vocabulary consistency analysis."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.models import EntityInfo, EntityType, FieldInfo
from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class EntityComparison:
    """Comparison of the same concept across multiple services."""

    concept_name: str
    instances: list[EntityInstance] = field(default_factory=list)
    field_overlap: float = 0.0
    vocabulary_drift: list[FieldDrift] = field(default_factory=list)
    assessment: str = ""


@dataclass
class EntityInstance:
    """One instance of a concept in a specific service."""

    entity_name: str
    service: str
    field_count: int
    field_names: list[str]
    entity_type: str


@dataclass
class FieldDrift:
    """A specific field naming inconsistency across services."""

    concept: str
    variations: dict[str, str] = field(default_factory=dict)  # service → field name


@dataclass
class VocabConsistencyReport:
    """Overall vocabulary consistency assessment."""

    concept: str
    names_used: dict[str, str] = field(default_factory=dict)  # service → name used
    canonical_owner: str = ""
    canonical_name: str = ""
    richest_field_count: int = 0
    consistency_score: float = 0.0  # 0-1, 1 = all services use same name


@dataclass
class ComparisonResult:
    """Full output of Phase 4-5."""

    entity_comparisons: list[EntityComparison] = field(default_factory=list)
    vocabulary_reports: list[VocabConsistencyReport] = field(default_factory=list)
    person_concept_drift: VocabConsistencyReport | None = None


def run(args: argparse.Namespace) -> int:
    """Compare entities across services and assess vocabulary consistency."""
    entities_path = Path(args.entities)
    if not entities_path.exists():
        print(f"Error: {entities_path} not found")
        return 1

    raw = json.loads(entities_path.read_text())
    entities = _deserialize_entities(raw)
    result = compare_entities(entities)

    # Print entity comparisons
    print(f"\n  Found {len(result.entity_comparisons)} shared concepts across services\n")

    for comp in result.entity_comparisons:
        services = [f"{i.service} ({i.entity_name}, {i.field_count} fields)" for i in comp.instances]
        print(f"  {comp.concept_name}:")
        for s in services:
            print(f"    • {s}")
        print(f"    Overlap: {comp.field_overlap:.0%} | {comp.assessment}")
        if comp.vocabulary_drift:
            for drift in comp.vocabulary_drift:
                variations = ", ".join(f"{svc}: {name}" for svc, name in drift.variations.items())
                print(f"    ⚠ Drift [{drift.concept}]: {variations}")
        print()

    # Print person concept analysis
    if result.person_concept_drift:
        pc = result.person_concept_drift
        print("  ═══ PERSON CONCEPT ANALYSIS ═══")
        print(f"  Canonical owner: {pc.canonical_owner} ({pc.canonical_name})")
        print(f"  Consistency: {pc.consistency_score:.0%}")
        print("  Names used:")
        for svc, name in sorted(pc.names_used.items()):
            marker = "✓" if name == pc.canonical_name else "✗"
            print(f"    {marker} {svc}: {name}")
        print()

    # Print vocabulary consistency
    print("  ═══ VOCABULARY CONSISTENCY ═══\n")
    rows = []
    for vc in sorted(result.vocabulary_reports, key=lambda x: x.consistency_score):
        names = ", ".join(f"{n}" for n in set(vc.names_used.values()))
        rows.append([vc.concept, names, vc.canonical_owner, f"{vc.consistency_score:.0%}"])
    print_table(["Concept", "Names Used", "Canonical Owner", "Consistency"], rows)

    write_json(result, args.output)
    print(f"\n  Comparison written to {args.output}")
    return 0


def compare_entities(entities: list[EntityInfo]) -> ComparisonResult:
    """Run full Phase 4-5 comparison."""
    result = ComparisonResult()

    # Phase 4: Find shared concepts (same entity name in multiple services)
    by_name: dict[str, list[EntityInfo]] = defaultdict(list)
    for e in entities:
        by_name[e.name].append(e)

    for name, instances in sorted(by_name.items()):
        unique_services = {e.owning_service for e in instances}
        if len(unique_services) < 2:
            continue

        comparison = _compare_entity_group(name, instances)
        result.entity_comparisons.append(comparison)

    # Phase 4b: Find address-like schemas (different names, similar purpose)
    address_comparison = _compare_address_schemas(entities)
    if address_comparison:
        result.entity_comparisons.append(address_comparison)

    # Phase 5: Person concept vocabulary drift
    result.person_concept_drift = _analyze_person_concept(entities)

    # Phase 5b: Vocabulary consistency for key concepts
    result.vocabulary_reports = _build_vocab_reports(entities, by_name)

    return result


def _compare_entity_group(concept: str, entities: list[EntityInfo]) -> EntityComparison:
    """Compare instances of the same entity across services."""
    comp = EntityComparison(concept_name=concept)

    for e in entities:
        field_names = [f.name for f in e.fields]
        comp.instances.append(EntityInstance(
            entity_name=e.name,
            service=e.owning_service,
            field_count=len(e.fields),
            field_names=field_names,
            entity_type=e.entity_type.value if isinstance(e.entity_type, EntityType) else e.entity_type,
        ))

    # Calculate field overlap
    if len(comp.instances) >= 2:
        all_field_sets = [set(i.field_names) for i in comp.instances if i.field_names]
        if all_field_sets:
            intersection = set.intersection(*all_field_sets)
            union = set.union(*all_field_sets)
            comp.field_overlap = len(intersection) / len(union) if union else 0

    # Assess
    if comp.field_overlap > 0.8:
        comp.assessment = "High overlap — likely accidental duplication or ungoverned shared kernel"
    elif comp.field_overlap > 0.4:
        comp.assessment = "Moderate overlap — possibly intentional but worth investigating"
    elif comp.field_overlap > 0:
        comp.assessment = "Low overlap — context-appropriate divergence (correct DDD)"
    else:
        comp.assessment = "No field overlap — same name, completely different concepts"

    return comp


def _compare_address_schemas(entities: list[EntityInfo]) -> EntityComparison | None:
    """Special comparison for address-like schemas across services."""
    address_entities = [
        e for e in entities
        if "address" in e.name.lower() and len(e.fields) > 0
    ]

    unique_services = {e.owning_service for e in address_entities}
    if len(unique_services) < 2:
        return None

    comp = EntityComparison(concept_name="Address (cross-service)")

    for e in address_entities:
        field_names = [f.name for f in e.fields]
        comp.instances.append(EntityInstance(
            entity_name=e.name,
            service=e.owning_service,
            field_count=len(e.fields),
            field_names=field_names,
            entity_type=e.entity_type.value if isinstance(e.entity_type, EntityType) else e.entity_type,
        ))

    # Find field naming drift for the same concept
    street_fields: dict[str, str] = {}
    postal_fields: dict[str, str] = {}
    country_fields: dict[str, str] = {}

    for e in address_entities:
        svc = e.owning_service
        for f in e.fields:
            fl = f.name.lower()
            if any(s in fl for s in ["line1", "street", "addr"]) and "2" not in fl:
                street_fields[svc] = f.name
            if any(p in fl for p in ["postal", "zip", "postcode"]):
                postal_fields[svc] = f.name
            if any(c in fl for c in ["country", "countrycode"]):
                country_fields[svc] = f.name

    if len(set(street_fields.values())) > 1:
        comp.vocabulary_drift.append(FieldDrift(concept="street_line_1", variations=street_fields))
    if len(set(postal_fields.values())) > 1:
        comp.vocabulary_drift.append(FieldDrift(concept="postal_code", variations=postal_fields))
    if len(set(country_fields.values())) > 1:
        comp.vocabulary_drift.append(FieldDrift(concept="country", variations=country_fields))

    comp.assessment = (
        f"{len(unique_services)} services, {len(address_entities)} schemas, "
        f"{len(comp.vocabulary_drift)} field naming inconsistencies — "
        "each context should own its own Address Value Object"
    )

    return comp


# Known ID field patterns for person concept detection
_PERSON_ID_PATTERNS = {
    "buyerId": "buyer",
    "customerId": "customer",
    "userId": "user",
    "recipientId": "recipient",
    "accountId": "account",
}


def _analyze_person_concept(entities: list[EntityInfo]) -> VocabConsistencyReport | None:
    """Detect vocabulary drift in the 'person' concept across services."""
    report = VocabConsistencyReport(concept="Person (buyer/customer/user/recipient/account)")

    for e in entities:
        if e.entity_type in (EntityType.DOMAIN_EVENT, "Domain Event"):
            continue

        for f in e.fields:
            if f.name in _PERSON_ID_PATTERNS:
                label = _PERSON_ID_PATTERNS[f.name]
                if e.owning_service not in report.names_used:
                    report.names_used[e.owning_service] = label

    if len(report.names_used) < 2:
        return None

    # Find canonical owner (the service with the richest person model)
    person_entities = [
        e for e in entities
        if e.name.lower() in ("customer", "user", "account", "buyer")
        and len(e.fields) > 5
    ]
    if person_entities:
        richest = max(person_entities, key=lambda e: len(e.fields))
        report.canonical_owner = richest.owning_service
        report.canonical_name = richest.name.lower()
        report.richest_field_count = len(richest.fields)

    # Consistency score
    names = list(report.names_used.values())
    if names:
        most_common = max(set(names), key=names.count)
        report.consistency_score = names.count(most_common) / len(names)

    return report


def _build_vocab_reports(
    entities: list[EntityInfo],
    by_name: dict[str, list[EntityInfo]],
) -> list[VocabConsistencyReport]:
    """Build vocabulary consistency reports for shared concepts."""
    reports: list[VocabConsistencyReport] = []

    for name, instances in sorted(by_name.items()):
        unique_services = {e.owning_service for e in instances}
        if len(unique_services) < 2:
            continue

        report = VocabConsistencyReport(concept=name)
        for e in instances:
            report.names_used[e.owning_service] = e.name

        # Find richest instance
        with_fields = [e for e in instances if len(e.fields) > 0]
        if with_fields:
            richest = max(with_fields, key=lambda e: len(e.fields))
            report.canonical_owner = richest.owning_service
            report.canonical_name = richest.name
            report.richest_field_count = len(richest.fields)

        # All instances share the same name by definition (grouped by name)
        # so consistency for same-name entities is 100%
        report.consistency_score = 1.0

        reports.append(report)

    return reports


def _deserialize_entities(raw: list[dict]) -> list[EntityInfo]:
    """Deserialize entity JSON back into EntityInfo objects."""
    entities: list[EntityInfo] = []
    for r in raw:
        fields = [
            FieldInfo(
                name=f["name"],
                field_type=f["field_type"],
                required=f.get("required", False),
                is_deprecated=f.get("is_deprecated", False),
                is_ref=f.get("is_ref", False),
                ref_target=f.get("ref_target"),
                enum_values=f.get("enum_values"),
            )
            for f in r.get("fields", [])
        ]

        entity_type = r.get("entity_type", "Entity")
        try:
            entity_type = EntityType(entity_type)
        except ValueError:
            entity_type = EntityType.ENTITY

        entities.append(EntityInfo(
            name=r["name"],
            entity_type=entity_type,
            owning_service=r["owning_service"],
            fields=fields,
            referenced_by=r.get("referenced_by", []),
            source_file=r.get("source_file", ""),
        ))
    return entities
