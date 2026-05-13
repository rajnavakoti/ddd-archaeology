"""Phase 6: Coupling analysis with dual heatmap and Mermaid context map."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ddd_archaeology.models import ContractType, CouplingEdge, CouplingType, EntityInfo, EntityType, FieldInfo
from ddd_archaeology.output.writer import print_table, write_json
from ddd_archaeology.parsers import asyncapi
from ddd_archaeology.parsers.graphql_parser import extract_mutations


def run(args: argparse.Namespace) -> int:
    """Analyze coupling between services."""
    entities_path = Path(args.entities)
    if not entities_path.exists():
        print(f"Error: {entities_path} not found")
        return 1

    raw = json.loads(entities_path.read_text())
    entities = _deserialize_entities(raw)
    result = analyze_coupling(entities)

    # Print coupling edges
    print(f"\n  Found {len(result.edges)} coupling relationships\n")

    # Coupling matrix
    services = sorted(result.service_list)
    print("  ═══ API COUPLING MATRIX (synchronous) ═══\n")
    api_edges = [e for e in result.edges if e.coupling_type in (CouplingType.ID_REFERENCE, CouplingType.SCHEMA_DUPLICATION)]
    _print_matrix(services, api_edges)

    print("\n  ═══ EVENT COUPLING (asynchronous) ═══\n")
    event_edges = [e for e in result.edges if e.coupling_type in (CouplingType.EVENT_PUBLISH,)]
    if event_edges:
        for e in event_edges:
            print(f"    {e.source_service} publishes → {e.evidence}")
    else:
        print("    No event coupling detected")

    # Services with no events
    if result.silent_services:
        print(f"\n  ⚠ Services publishing NO events (synchronous bottlenecks):")
        for svc in sorted(result.silent_services):
            print(f"    • {svc}")

    # Hub analysis
    print(f"\n  ═══ SERVICE ROLES ═══\n")
    for svc in services:
        inbound = sum(1 for e in api_edges if e.target_service == svc)
        outbound = sum(1 for e in api_edges if e.source_service == svc)
        role = _classify_role(inbound, outbound)
        print(f"    {svc}: {role} (in:{inbound}, out:{outbound})")

    # Circular dependencies
    if result.circular_deps:
        print(f"\n  ⚠ CIRCULAR DEPENDENCIES:")
        for pair in result.circular_deps:
            print(f"    ↔ {pair[0]} ←→ {pair[1]}")

    # Mermaid diagram
    mermaid = _generate_mermaid(services, result.edges, result.silent_services)
    mermaid_path = Path(args.output).parent / "context-map.mmd"
    mermaid_path.write_text(mermaid)
    print(f"\n  Mermaid diagram written to {mermaid_path}")

    # HTML heatmap
    html = _generate_heatmap_html(services, result.edges)
    html_path = Path(args.html)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)
    print(f"  Heatmap written to {html_path}")

    write_json(result.edges, args.output)
    print(f"  Coupling data written to {args.output}")

    return 0


@dataclass
class CouplingResult:
    edges: list[CouplingEdge] = field(default_factory=list)
    service_list: list[str] = field(default_factory=list)
    silent_services: list[str] = field(default_factory=list)
    circular_deps: list[tuple[str, str]] = field(default_factory=list)


def analyze_coupling(entities: list[EntityInfo]) -> CouplingResult:
    """Analyze coupling from entity data."""
    result = CouplingResult()

    # Get unique services (exclude GraphQL BFF from domain coupling — it's a consumer layer)
    all_services = sorted({e.owning_service for e in entities})
    result.service_list = all_services

    # Build service → entities map
    service_entities: dict[str, list[EntityInfo]] = defaultdict(list)
    for e in entities:
        service_entities[e.owning_service].append(e)

    # Build entity name → owning services map
    entity_owners: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        entity_owners[e.name].append(e.owning_service)

    # 1. ID reference coupling: trace fields ending in 'Id' that reference other services
    for svc, svc_entities in service_entities.items():
        for entity in svc_entities:
            for f in entity.fields:
                target_svc = _resolve_id_reference(f.name, svc, entity_owners, all_services)
                if target_svc and target_svc != svc:
                    result.edges.append(CouplingEdge(
                        source_service=svc,
                        target_service=target_svc,
                        coupling_type=CouplingType.ID_REFERENCE,
                        evidence=f"{f.name} in {entity.name}",
                        field_name=f.name,
                    ))

    # 2. Schema duplication: same entity name in multiple services
    for name, owners in entity_owners.items():
        unique = list(set(owners))
        if len(unique) >= 2:
            for i, svc_a in enumerate(unique):
                for svc_b in unique[i + 1:]:
                    result.edges.append(CouplingEdge(
                        source_service=svc_a,
                        target_service=svc_b,
                        coupling_type=CouplingType.SCHEMA_DUPLICATION,
                        evidence=f"Schema '{name}' exists in both services",
                    ))

    # 3. Event publishing: services that publish events
    publishing_services: set[str] = set()
    for e in entities:
        if e.entity_type == EntityType.DOMAIN_EVENT:
            publishing_services.add(e.owning_service)
            result.edges.append(CouplingEdge(
                source_service=e.owning_service,
                target_service="(event bus)",
                coupling_type=CouplingType.EVENT_PUBLISH,
                evidence=f"Publishes {e.name}",
            ))

    # 4. Silent services: no events published
    openapi_services = {
        svc for svc in all_services
        if not any(
            e.entity_type == EntityType.DOMAIN_EVENT
            for e in service_entities.get(svc, [])
        )
        and svc not in ("(event bus)",)
    }
    result.silent_services = sorted(openapi_services - publishing_services)

    # 5. Circular dependencies
    api_edges = [e for e in result.edges if e.coupling_type == CouplingType.ID_REFERENCE]
    outbound: dict[str, set[str]] = defaultdict(set)
    for e in api_edges:
        outbound[e.source_service].add(e.target_service)

    seen_pairs: set[tuple[str, str]] = set()
    for svc_a, targets in outbound.items():
        for svc_b in targets:
            if svc_a in outbound.get(svc_b, set()):
                pair = tuple(sorted([svc_a, svc_b]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    result.circular_deps.append(pair)

    # Deduplicate edges
    result.edges = _deduplicate_edges(result.edges)

    return result


# Known ID field → likely service mappings
_ID_SERVICE_HINTS: dict[str, list[str]] = {
    "buyerId": ["Consignee", "Customer", "customer"],
    "customerId": ["Consignee", "Customer", "customer"],
    "userId": ["Consignee", "Customer", "customer", "User"],
    "recipientId": ["Consignee", "Customer", "customer"],
    "accountId": ["Consignee", "Customer", "customer", "Invoicing", "Billing", "Account"],
    "orderId": ["Shipment", "Order"],
    "warehouseId": ["Inventory", "Warehouse"],
    "carrierId": ["Carrier", "Shipping", "Delivery"],
    "shipmentId": ["Carrier", "Shipping", "Shipment", "Delivery"],
    "trackingNumber": ["Carrier", "Shipping", "Delivery"],
    "invoiceId": ["Invoicing", "Billing", "Invoice"],
    "paymentId": ["Invoicing", "Billing", "Payment"],
    "productId": ["Inventory", "Product", "Catalog"],
    "reservationId": ["Inventory", "Reservation"],
}


def _resolve_id_reference(
    field_name: str,
    source_service: str,
    entity_owners: dict[str, list[str]],
    all_services: list[str],
) -> str | None:
    """Try to resolve which service an ID field references."""
    if not field_name.endswith("Id"):
        return None

    # Check hints — prefer API services over event services
    hints = _ID_SERVICE_HINTS.get(field_name, [])
    candidates: list[str] = []
    for hint in hints:
        for svc in all_services:
            if hint.lower() in svc.lower() and svc != source_service:
                candidates.append(svc)

    if not candidates:
        return None

    # Prefer services with "API" or "Service" in name (REST) over "Events"
    api_candidates = [c for c in candidates if "event" not in c.lower()]
    if api_candidates:
        return api_candidates[0]
    return candidates[0]


def _classify_role(inbound: int, outbound: int) -> str:
    """Classify a service's role based on coupling direction."""
    if outbound >= 3:
        return "GOD SERVICE (high outbound coupling)"
    if inbound >= 3 and outbound == 0:
        return "UPSTREAM (published language / open host)"
    if inbound >= 3:
        return "HUB (high inbound, potential bottleneck)"
    if inbound == 0 and outbound == 0:
        return "ISOLATED"
    if outbound > inbound:
        return "CONSUMER (more outbound than inbound)"
    return "BALANCED"


def _deduplicate_edges(edges: list[CouplingEdge]) -> list[CouplingEdge]:
    """Remove duplicate edges (same source, target, type)."""
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[CouplingEdge] = []
    for e in edges:
        key = (e.source_service, e.target_service, e.coupling_type.value, e.evidence)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def _print_matrix(services: list[str], edges: list[CouplingEdge]) -> None:
    """Print a coupling matrix to stdout."""
    # Abbreviate service names
    abbrev = {s: s.split()[0][:8] for s in services}

    # Build matrix
    matrix: dict[str, dict[str, int]] = {s: {t: 0 for t in services} for s in services}
    for e in edges:
        if e.source_service in matrix and e.target_service in matrix[e.source_service]:
            matrix[e.source_service][e.target_service] += 1

    headers = ["From \\ To"] + [abbrev[s] for s in services]
    rows = []
    for s in services:
        row = [abbrev[s]]
        for t in services:
            if s == t:
                row.append("—")
            elif matrix[s][t] > 0:
                row.append(str(matrix[s][t]))
            else:
                row.append("·")
        rows.append(row)
    print_table(headers, rows)


def _generate_mermaid(
    services: list[str],
    edges: list[CouplingEdge],
    silent_services: list[str],
) -> str:
    """Generate a Mermaid diagram for the context map."""
    lines = ["graph LR"]

    # Service nodes
    abbrevs: dict[str, str] = {}
    for i, svc in enumerate(services):
        abbr = f"S{i}"
        abbrevs[svc] = abbr
        label = svc.replace(" API", "").replace(" Service", "")
        if svc in silent_services:
            lines.append(f'    {abbr}["{label}<br/>⚠ No events"]')
        else:
            lines.append(f'    {abbr}["{label}"]')

    lines.append("")

    # Edges
    seen_edges: set[str] = set()
    for e in edges:
        if e.target_service == "(event bus)":
            continue
        src = abbrevs.get(e.source_service)
        tgt = abbrevs.get(e.target_service)
        if not src or not tgt:
            continue

        key = f"{src}-{tgt}-{e.coupling_type.value}"
        if key in seen_edges:
            continue
        seen_edges.add(key)

        if e.coupling_type == CouplingType.ID_REFERENCE:
            lines.append(f"    {src} -->|references| {tgt}")
        elif e.coupling_type == CouplingType.SCHEMA_DUPLICATION:
            lines.append(f"    {src} -.->|shared schema| {tgt}")

    return "\n".join(lines) + "\n"


def _generate_heatmap_html(services: list[str], edges: list[CouplingEdge]) -> str:
    """Generate a neo-brutalist HTML heatmap for coupling visualization."""
    # Build matrix counts
    api_edges = [e for e in edges if e.coupling_type in (CouplingType.ID_REFERENCE, CouplingType.SCHEMA_DUPLICATION)]
    matrix: dict[str, dict[str, int]] = {s: {t: 0 for t in services} for s in services}
    for e in api_edges:
        if e.source_service in matrix and e.target_service in matrix.get(e.source_service, {}):
            matrix[e.source_service][e.target_service] += 1

    # Short names
    short = {s: s.replace(" Service API", "").replace(" & ", "/").replace(" Domain Events", " Events") for s in services}

    # Build table rows
    header_cells = "".join(f'<th class="col-header">{short[s]}</th>' for s in services)
    body_rows = ""
    for s in services:
        cells = ""
        for t in services:
            if s == t:
                cells += '<td class="self">—</td>'
            elif matrix[s][t] > 0:
                intensity = min(matrix[s][t] * 25, 100)
                cells += f'<td class="coupled" style="--intensity: {intensity}%">{matrix[s][t]}</td>'
            else:
                cells += '<td class="none">·</td>'
        body_rows += f'<tr><th class="row-header">{short[s]}</th>{cells}</tr>\n'

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<title>DDD Archaeology — Coupling Heatmap</title>
<style>
:root {{
    --bg: #1A1A1A;
    --bg-surface: #222;
    --text: #E0E0E0;
    --text-dim: #999;
    --border: #444;
    --accent: #C0A050;
    --coupled-bg: #553322;
    --self-bg: #2A2A2A;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'JetBrains Mono', monospace;
    background: var(--bg);
    color: var(--text);
    padding: 32px;
}}
h1 {{
    font-size: 24px;
    margin-bottom: 8px;
    border-bottom: 3px solid var(--border);
    padding-bottom: 8px;
}}
.subtitle {{
    color: var(--text-dim);
    margin-bottom: 32px;
    font-size: 14px;
}}
table {{
    border-collapse: collapse;
    border: 2px solid var(--border);
}}
th, td {{
    border: 1px solid var(--border);
    padding: 8px 12px;
    text-align: center;
    font-size: 13px;
}}
.col-header {{
    background: var(--bg-surface);
    writing-mode: vertical-rl;
    text-orientation: mixed;
    padding: 12px 8px;
    font-weight: bold;
    min-height: 120px;
}}
.row-header {{
    background: var(--bg-surface);
    text-align: left;
    font-weight: bold;
    white-space: nowrap;
}}
.self {{
    background: var(--self-bg);
    color: var(--text-dim);
}}
.none {{
    color: var(--text-dim);
}}
.coupled {{
    background: color-mix(in srgb, var(--coupled-bg) var(--intensity), var(--bg));
    color: var(--accent);
    font-weight: bold;
}}
.legend {{
    margin-top: 24px;
    font-size: 13px;
    color: var(--text-dim);
}}
</style>
</head>
<body>
<h1>Coupling Heatmap</h1>
<p class="subtitle">DDD Archaeology — Contract-based coupling analysis</p>
<table>
<thead>
<tr><th></th>{header_cells}</tr>
</thead>
<tbody>
{body_rows}
</tbody>
</table>
<div class="legend">
<p>Rows = source service (references). Columns = target service (referenced by).</p>
<p>Numbers = coupling edges (ID references + schema duplication). Higher = more coupled.</p>
</div>
</body>
</html>
"""


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
        entity_type_str = r.get("entity_type", "Entity")
        try:
            entity_type = EntityType(entity_type_str)
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
