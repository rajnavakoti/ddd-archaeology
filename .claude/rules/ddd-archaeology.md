# DDD Archaeology Reasoning Conventions

Apply when interpreting contract archaeology outputs (entity maps, coupling matrices, vocabulary reports) to infer domain boundaries.

## Core Principle
The contracts are the implementation's confession. They reveal what the code actually does, not what the architecture documents say it should do.

## Boundary Signals

### Merge Signals (two services → one context)
- Circular ID references between two services
- 80%+ schema field overlap for shared entities
- Same entity name with nearly identical schemas in both
- Services always called together in the same flows
- Frame as diagnosis: "the boundary is currently fictional" — not prescription

### Split Signals (one service → two contexts)
- Service has two distinct endpoint clusters with no shared schemas
- HTTP method distribution shows mixed patterns (some CRUD, some query-only)
- Entity names that don't relate to each other within the service

### Infrastructure vs Domain
- GET-only service = read model / projection, not a bounded context
- Service coupled to everything but owning no domain logic = infrastructure (Notification, Search, Analytics)
- Service with no domain events = synchronous utility

## Coupling Interpretation
- ID reference only = Customer-Supplier (healthy, expected)
- Duplicated schema, diverging fields = Conformist going stale
- Duplicated schema, identical = Shared Kernel or copy-paste coupling. Check: shared library?
- Translated/simplified schema (e.g., GraphQL BFF) = Anticorruption Layer
- Two services referencing each other = Partnership or accidental coupling

## Vocabulary Assessment
- Different names, same fields = cosmetic drift (naming governance gap)
- Different names, different fields = semantic divergence (correct DDD, each context owns its model)
- Same name, different fields = context-appropriate Value Objects (e.g., Address)
- Richest model = canonical owner / system of record for that concept

## Confidence Scoring
- High: contract modified within 30 days
- Medium: 30-90 days
- Low: 90-365 days
- Very Low: >365 days
- Low-confidence findings are hypotheses, not facts. Recommend validation with log mining

## Framing
- Always frame findings as diagnoses, not prescriptions
- "The contracts suggest X" not "You should do X"
- Acknowledge technique limitations: undocumented services are blind spots
- Reference other exhibits for follow-up when the technique can't answer
