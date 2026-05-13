# DDD Archaeology

Reverse-engineer domain boundaries from existing API contracts — without reading source code or running workshops.

## What Is This?

A toolkit for discovering bounded contexts, entity relationships, vocabulary alignment, and coupling patterns from the contracts your teams already produce: OpenAPI specs, AsyncAPI event contracts, and GraphQL schemas.

**The premise:** Your API contracts are the implementation's confession. They can't hide what the code actually does. By systematically analyzing them, you can infer the actual domain architecture — and compare it to the intended one.

## The Process

Contract Archaeology follows an 8-phase chain of thought:

1. **Collect & Inventory** — Parse all contract files, normalize
2. **Vocabulary Extraction** — Pull every domain term from schemas, events, types
3. **Entity Discovery** — Identify entities, value objects, aggregates
4. **Cross-Entity Comparison** — Same concept across services? Compare field-by-field
5. **Vocabulary Consistency** — How aligned is the ubiquitous language?
6. **Coupling Analysis** — Trace cross-service references, build coupling heatmap
7. **Boundary Inference** — Group findings into candidate bounded contexts
8. **Gap Analysis** — Compare inferred map vs documented architecture

Phases 1-6 are automatable (scripts). Phases 7-8 need human judgment or AI assistance (agent skills).

See [docs/chain-of-thought.md](docs/chain-of-thought.md) for the full reasoning process behind each phase.

## Examples

The `examples/delivery/` directory contains a synthetic delivery platform domain with deliberate architectural signals:

- **6 OpenAPI specs** — Shipment, Consignee, Inventory, Carrier Integration, Invoicing, Tracking Notifications
- **2 AsyncAPI specs** — Shipment and Carrier domain events
- **1 GraphQL schema** — Tracking Portal BFF aggregating multiple backends

### Signals embedded in the example:

| Signal | Where |
|--------|-------|
| Vocabulary drift | 6 names for the same person: buyer, customer, user, recipient, account |
| God entity | Shipment schema coupled to 4 other contexts |
| Hidden coupling | Shipment → Carrier/Invoicing/Inventory data embedded |
| Dead boundary | Shipment + Carrier tightly intertwined |
| Duplicate ownership | Shipment and Invoice owned by two services each |
| Same name, different concept | Address in 4 services with 4 different shapes |
| Infrastructure as domain | Tracking Notifications coupled to everything |
| Event naming patterns | Channel prefixes reveal context boundaries |

## Structure

```
ddd-archaeology/
├── docs/
│   ├── chain-of-thought.md       # Full reasoning process
│   └── exhibit-a-qa-draft.md     # 35 battle-tested Q&A answers
├── examples/
│   └── delivery/                 # Synthetic contracts with embedded signals
│       ├── shipment-service.openapi.yaml
│       ├── consignee-service.openapi.yaml
│       ├── inventory-service.openapi.yaml
│       ├── carrier-service.openapi.yaml
│       ├── invoicing-service.openapi.yaml
│       ├── tracking-notifications.openapi.yaml
│       ├── shipment-events.asyncapi.yaml
│       ├── carrier-events.asyncapi.yaml
│       └── tracking-portal.graphql
├── src/ddd_archaeology/          # Automation scripts (Phases 1-6)
├── .claude/skills/               # Agent skills (Phases 7-8)
└── .claude/rules/                # DDD reasoning conventions
```

## Who Is This For?

- Software architects reverse-engineering legacy systems
- DDD practitioners wanting evidence-based domain discovery
- Platform teams assessing API landscape health
- Anyone who suspects their context map doesn't match reality

## Background

This toolkit accompanies the talk "Reverse-Engineering DDD: Discovering Domains in Legacy Systems Without the Textbook" — exploring how to discover domain boundaries from production artifacts rather than whiteboard workshops alone.

## License

MIT
