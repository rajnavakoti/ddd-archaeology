# Contract Archaeology — Chain of Thought Process

## What Is This?

A systematic reverse-engineering process to discover domain boundaries (bounded contexts), entity relationships, vocabulary alignment, and coupling patterns from existing API contracts — without reading source code or running workshops.

**Input:** OpenAPI specs, AsyncAPI event contracts, GraphQL schemas
**Output:** Inferred context map, entity map, vocabulary report, coupling heatmap, gap analysis

This process can be applied manually by an architect, automated via scripts (Phases 1-6), or assisted by AI agents (Phases 7-8).

---

## Phase 1: Collect & Inventory

**Goal:** Know what you have before analyzing anything.

**Process:**
1. Gather all contract files within the domain scope (OpenAPI YAML/JSON, AsyncAPI YAML, GraphQL SDL files)
2. Parse and normalize into a common inventory
3. Record: service name, owning team, version, contract type, endpoint/channel/operation count, schema count

**Thought process:**
- Which services are on higher API versions? (v2, v3 = more redesigns = more churn = potential complexity hotspot)
- Which services have the most schemas? (More schemas ≠ more complex domain, but it's a signal)
- Are there services without contracts? (Undocumented services = hidden dependencies)
- What mix of contract types do we see? (REST-only = request-driven architecture. Events present = some event-driven patterns exist)

**Output:** Contract inventory table — service, team, version, type, counts

---

## Phase 2: Vocabulary Extraction

**Goal:** Build the raw domain vocabulary from what teams actually named things.

**Process:**
1. From OpenAPI: extract resource names from paths, schema names, field names, enum values
2. From AsyncAPI: extract channel names, event type names, payload field names
3. From GraphQL: extract type names, field names, enum values, query/mutation names
4. Compile into a unified vocabulary list grouped by concept

**Thought process for REST APIs:**
- Path segments are resource candidates: `/orders`, `/customers`, `/warehouses`
- Schema names are entity candidates: `Order`, `Customer`, `Address`
- Field names reveal relationships: `buyerId` in Order → references Customer context
- Enum values reveal domain lifecycle: `OrderStatus: [draft, placed, confirmed, shipped, delivered, cancelled]`
- Required fields reveal core vs optional concepts

**Thought process for Events (AsyncAPI):**
- Channel/topic names reveal domain boundaries: `orders.placed`, `shipments.delivered`
- The topic prefix IS the candidate bounded context: `orders.*` = Order context, `shipments.*` = Shipping context
- Event names follow past tense = domain events (DDD concept): `OrderPlaced`, `ShipmentDelivered`
- Event names reveal what the service considers important enough to announce — this is closer to true domain behavior than API endpoints
- Event payload fields reveal what data flows between contexts (the integration contract)
- Events that a service publishes = its outbound language. Events it subscribes to = its dependencies
- **Key difference from APIs:** APIs are pulled (consumer asks), events are pushed (producer announces). What a service announces tells you what it thinks its core responsibility is

**Thought process for GraphQL:**
- GraphQL types are the frontend's view of the domain — shaped by UI needs, not backend boundaries
- A GraphQL `Order` type that includes `payment`, `shipment`, `product` inline reveals what the frontend considers "one thing" — which may aggregate multiple backend contexts
- Mutations reveal use cases: `placeOrder`, `cancelOrder`, `requestRefund` = the actual user journeys
- Query names reveal what consumers actually need vs what APIs expose
- GraphQL often acts as a BFF (Backend for Frontend) — it's a translation layer. Comparing GraphQL types to backend OpenAPI schemas reveals where the frontend model diverges from the backend model

**Output:** Unified vocabulary list — every domain term, where it appears, what type (entity, field, enum, event)

---

## Phase 3: Entity Discovery

**Goal:** Identify the real domain entities, value objects, and aggregates hiding in the contracts.

**Process:**
1. Top-level schemas (OpenAPI) and types (GraphQL) = candidate entities
2. Nested/inline objects = candidate value objects or child entities
3. Shared `$ref` definitions = candidate shared kernel concepts
4. Event payloads = candidate domain events
5. Map which entities appear in which services

**Thought process:**
- If a schema appears as a top-level resource with its own CRUD endpoints → likely an Entity (has identity, lifecycle)
- If a schema only appears nested inside another → likely a Value Object (no independent identity)
- If the same schema name appears in multiple services → either shared kernel (intentional) or coupling (accidental)
- If an event payload contains fields from multiple entities → the event is a boundary-crossing integration point
- **Aggregate hint:** If an entity has sub-resources in the API path (e.g., `/orders/{id}/lines`, `/orders/{id}/shipment`) → the parent is likely an Aggregate Root containing child entities

**Output:** Entity map — entities, their owning service, which other services reference them, entity type (Entity/VO/Aggregate Root)

---

## Phase 4: Cross-Entity Comparison

**Goal:** Find same-concept-different-shapes and same-name-different-concepts across services.

**Process:**
1. Group entities by semantic concept (e.g., all address-like schemas)
2. Compare field-by-field: names, types, required vs optional, field count
3. Flag: same concept, different field names (vocabulary drift)
4. Flag: same concept, different field sets (context-specific value objects — this is CORRECT DDD)
5. Flag: same concept, same fields everywhere (shared kernel or unintentional coupling)

**Thought process:**
- Same concept, different names (e.g., `postalCode` vs `zipCode` vs `postal`) → vocabulary not aligned. The ubiquitous language has fractured across team boundaries
- Same concept, different fields (e.g., Address with `deliveryInstructions` in Shipping vs `vatNumber` in Billing) → this is CORRECT. Each bounded context should have its own representation of a concept tailored to its needs. This is NOT a problem to fix — it's a boundary to recognize
- Same concept, identical everywhere → suspicious. Either it's a legitimate shared kernel (intentional, governed) or it's copy-paste coupling (accidental, ungoverned). Check: is there a shared library? A shared schema repo? If not, it's accidental
- Event payload vs API schema for same concept → events should carry LESS data than API responses. If an event carries the full entity, it's leaking internal state across boundaries

**Output:** Comparison matrix — entity × service, with field-level diff highlighting drift and divergence

---

## Phase 5: Vocabulary Consistency Analysis

**Goal:** Assess how aligned the ubiquitous language is across the domain.

**Process:**
1. For each core concept (Customer, Order, Product, Address), list all names used across services
2. Cluster synonyms: `buyer` ≈ `customer` ≈ `user` ≈ `account` ≈ `recipient`
3. Score consistency: how many services use the same term?
4. Identify the "canonical" owner — which service has the richest model of this concept?

**Thought process:**
- If everyone uses different names for the same person → no ubiquitous language exists for this concept. This is a governance gap, not just a naming issue
- The service with the richest model IS the system of record for that concept. If Customer Service has segments, loyalty, preferences, and 15 fields — but Order Service calls them "buyer" with 3 fields — Customer Service owns the concept
- Event names are often MORE aligned than API names because event naming conventions are typically enforced at the platform level (e.g., `domain.past_tense_verb`). If event names are consistent but API names aren't, the event bus has better governance than the API layer
- GraphQL type names represent the consumer's vocabulary. If the GraphQL `User` type maps to backend `Customer`, that's a translation — the frontend has its own ubiquitous language

**Output:** Vocabulary consistency report — concept, all names used, canonical owner, consistency score

---

## Phase 6: Coupling Analysis

**Goal:** Map dependencies between services based on what their contracts reveal.

**Process:**
1. Trace ID references: `buyerId` in Order → references Customer. `warehouseId` in Order → references Inventory
2. Trace duplicated schemas: Order has `ShipmentInfo`, Shipping has `Shipment` → duplicate ownership
3. Trace event subscriptions: who publishes what, who needs to listen
4. Count references per service → coupling heatmap
5. Identify: hub services (referenced by many), leaf services (reference nobody), circular dependencies

**Thought process:**
- A service that includes IDs from 4 other services in its main entity → god entity, coupled to everything. This is the biggest architectural risk
- A service that is referenced by everyone but references nobody → healthy upstream service. In DDD terms: Published Language or Open Host Service
- Two services that reference each other → circular dependency. Either they're actually one bounded context, or they need an Anticorruption Layer
- A service whose event payloads include data from multiple other services → integration/orchestration service, not a domain service. (e.g., Notification Service)
- Event coupling is looser than API coupling. If Service A calls Service B's API → temporal coupling (A waits for B). If Service A listens to Service B's events → eventual consistency (A doesn't wait). The type of coupling matters for boundary decisions

**Coupling classification (DDD Context Mapping):**
- Service references another's ID only → Customer-Supplier relationship
- Service duplicates another's schema → Conformist or Shared Kernel
- Service translates another's data into its own model → Anticorruption Layer
- Service exposes a simplified API for others → Open Host Service
- Two services tightly intertwined → Partnership (or accidental coupling)

**Output:** Coupling matrix, heatmap, DDD context map relationship annotations

---

## Phase 7: Boundary Inference (Human / AI-Assisted)

**Goal:** Derive the actual bounded context map from the evidence gathered in Phases 1-6.

**Process:**
1. Group entities by service ownership → candidate bounded contexts
2. Merge services that share 80%+ schemas or have circular dependencies → likely one context
3. Split services that contain unrelated entity clusters → likely multiple contexts in one service
4. Cross-reference with team ownership (Conway's Law) — do team boundaries match inferred context boundaries?
5. Identify services that are infrastructure, not domain (e.g., Notification, API Gateway)

**Thought process:**
- Start with: one service = one candidate bounded context. Then adjust
- Merge signal: two services always called together, share schemas, reference each other → one context
- Split signal: one service has two distinct sets of endpoints with no shared schemas → two contexts
- Conway's Law check: if a context spans two teams → either align teams or split the context. If two contexts are in one team → that's fine if the team is small enough
- Infrastructure vs domain: if a service has no domain logic but touches data from many contexts → it's infrastructure (Notification, Search, Analytics). Don't model it as a bounded context

**Output:** Inferred context map — bounded contexts, their boundaries, relationships (Shared Kernel, Customer-Supplier, ACL, etc.)

---

## Phase 8: Gap Analysis (Human / AI-Assisted)

**Goal:** Compare the inferred (actual) context map with the intended (documented) architecture.

**Process:**
1. Get the existing architecture docs: context map, event storming output, architecture decision records
2. Compare: intended boundaries vs inferred boundaries
3. Flag gaps:
   - **Dead boundaries:** documented as separate, but contracts show they're one
   - **Missing boundaries:** no documentation, but contracts show distinct contexts
   - **Coupling violations:** documented as independent, but contracts show tight coupling
   - **Vocabulary gaps:** documented ubiquitous language vs actual naming in contracts
   - **Ownership disputes:** two services both claim the same entity

**Thought process:**
- The intended architecture represents aspirations. The inferred architecture represents reality. Neither is "right" — the gap between them is what needs attention
- Some gaps are intentional (we know Order is a monolith, we're working on it). Some are unknown (nobody realized Shipping and Order are the same context). The unknown gaps are the value
- Priority order: coupling violations > ownership disputes > dead boundaries > vocabulary gaps > missing boundaries
- For each gap, the question is: do we fix the code to match the architecture, or update the architecture to match the code? The answer depends on which direction the system is evolving

**Output:** Gap report — gap type, evidence from contracts, severity, recommended action

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Collect & Inventory | 100% — parse files | — |
| 2. Vocabulary Extraction | 100% — extract nouns | — |
| 3. Entity Discovery | 80% — parse + group | Is this an entity or just a DTO? |
| 4. Cross-Entity Comparison | 90% — field-level diff | Are these the same concept? |
| 5. Vocabulary Consistency | 70% — fuzzy matching | Are `buyer` and `customer` the same? |
| 6. Coupling Analysis | 90% — trace refs | Is this coupling intentional? |
| 7. Boundary Inference | 30% — heuristics | What should be a bounded context? |
| 8. Gap Analysis | 20% — diff against docs | What does the gap mean? |

**Scripts handle Phases 1-6. Agent skills handle Phases 7-8. Humans review everything.**
