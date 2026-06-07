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
│   ├── chain-of-thought.md             # Full reasoning process (8 phases)
│   ├── exhibit-*-chain-of-thought.md   # Deep reasoning per exhibit (B-H)
│   └── forensic-ddd-checklist.md       # Decision framework
├── examples/
│   └── delivery/                       # Synthetic delivery platform
│       ├── *.openapi.yaml              # 6 OpenAPI specs
│       ├── *.asyncapi.yaml             # 2 AsyncAPI event specs
│       ├── *.graphql                   # 1 GraphQL BFF
│       ├── database/                   # DB schema, access logs, transactions
│       ├── logs/                       # Sample traces, event frequencies
│       ├── incidents/                  # Incident history
│       ├── errors/                     # Error code catalog
│       └── git/                        # Co-change data
├── src/ddd_archaeology/                # CLI tools (all 12 phases)
├── tests/                              # 120 tests
├── .claude/skills/                     # Agent skills (orchestration + interpretation)
└── .claude/rules/                      # DDD reasoning conventions
```

## Quick Start — Your Own System

The toolkit works with **any domain** — the delivery example is just a demonstration. To analyze your own system:

```bash
# 1. Install
pip install -e .

# 2. Point at your contracts (OpenAPI, AsyncAPI, and/or GraphQL files)
python -m ddd_archaeology collect ./path/to/your/specs/ -o output/inventory.json

# 3. Run the pipeline
python -m ddd_archaeology extract-vocab output/inventory.json -o output/vocabulary.json
python -m ddd_archaeology discover-entities output/inventory.json -o output/entities.json
python -m ddd_archaeology compare output/entities.json -o output/comparison.json
python -m ddd_archaeology analyze-coupling output/entities.json -o output/coupling.json --html output/heatmap.html
```

**What you need:** Any combination of OpenAPI (`.yaml`/`.json`), AsyncAPI (`.yaml`), or GraphQL (`.graphql`) spec files. The more services you include, the richer the coupling analysis.

**Extended exhibits (B-H):** If you have database schemas, transaction logs, incident data, error codes, or git history — you can run additional exhibits for deeper analysis. See `examples/delivery/` for the expected data formats.

**No code changes required.** The analysis is structural — it works by comparing schemas, tracing ID references, and measuring coupling patterns regardless of your industry (logistics, healthcare, fintech, e-commerce, etc.).

## Who Is This For?

- Software architects reverse-engineering legacy systems
- DDD practitioners wanting evidence-based domain discovery
- Platform teams assessing API landscape health
- Anyone who suspects their context map doesn't match reality

## Background

This toolkit accompanies the talk "Reverse-Engineering DDD: Discovering Domains in Legacy Systems Without the Textbook" — exploring how to discover domain boundaries from production artifacts rather than whiteboard workshops alone.

## License

MIT
