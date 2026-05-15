# Data Lineage Tracing — Chain of Thought Process

## What Is This?

A process for discovering data ownership, copy proliferation, format divergence, and propagation gaps by tracing a single domain entity through every place it's stored in the system. While previous exhibits map coupling at the API, schema, transaction, and behavioral levels, Data Lineage Tracing maps coupling at the data instance level — where specific values live, how they got there, and whether they still match.

**Input:** Database schemas (from Exhibit B), production data access, ETL/pipeline configurations, data warehouse schemas
**Output:** Entity lineage map, copy inventory, format comparison, consistency report, missing event catalog, context boundary recommendations

---

## Why Data Lineage Matters

In legacy systems, data doesn't live in one place. Every service that needs an entity copies it — at a different time, in a different format, with a different update policy. Over 12 years, these copies accumulate silently. Nobody notices the divergence because each service is correct in its own context.

Data lineage reveals:
- **Who the real source of truth is** — which copy is authoritative
- **Where copies have drifted** — how many mismatches exist in production
- **What events are missing** — each independent update without propagation is a missing domain event
- **Where format divergence prevents reconciliation** — lossy transformations that can't be reversed
- **Where the real context boundaries are** — each copy with different rules IS a bounded context

---

## Phase 1: Select Target Entities

**Goal:** Choose the entities most likely to reveal data ownership problems.

**Process:**
1. From Exhibit B, identify entities that appear in multiple services' schemas
2. From Exhibit A, identify entities with vocabulary drift (different names for the same concept)
3. Prioritize entities that are: (a) referenced by 3+ services, (b) have different field shapes across services, (c) are involved in incident clusters (Exhibit E)

**Good lineage targets in a delivery platform:**
- **Customer/consignee address** — stored everywhere, different formats, different update policies
- **Order total/amount** — calculated differently in Order, Invoice, Payment
- **Product/SKU information** — copied from catalog to order to shipment to invoice
- **Shipment status** — maintained independently by Shipment Service and Carrier Integration

**Thought process:**
- Start with the entity that caused the most confusion in previous exhibits. For our delivery platform, that's the address — 4 different schemas in Exhibit A, read by 3 services in Exhibit B, zero incidents but a ticking clock
- One entity traced thoroughly reveals more than five entities traced superficially. Depth over breadth
- The entity should cross at least 3 service boundaries to be a useful lineage target

**Output:** Selected entity list with rationale for each

---

## Phase 2: Map All Storage Locations

**Goal:** Find every place the selected entity is stored in the system.

**Process:**
1. Query each service's database for tables/columns containing the entity
2. Check data warehouse for dimensional tables or staging tables
3. Check caches (Redis, Memcached) for cached copies
4. Check search indexes (Elasticsearch) for indexed copies
5. Check message queues for in-flight copies (Kafka topics, dead letter queues)

**For each storage location, document:**
- Table/collection/key name
- Owning service
- Format (normalized columns, JSON blob, concatenated text, binary)
- Fields included (does it have all fields or a subset?)
- When it was created (at what event in the entity's lifecycle)
- Update policy (never updated, event-driven updates, manual updates, ETL sync)

**Thought process:**
- **Operational databases** are the primary target — these are the copies that services use for real-time operations
- **Data warehouses** often have the most complete picture because ETL captures changes that operational services miss. The warehouse may be an accidental source of truth for historical data
- **Caches** are often overlooked. A Redis cache with a 24-hour TTL holding a customer address means that for 24 hours after an address change, the cache returns the old address. That's a data lineage node with its own update policy (time-based expiration)
- **Search indexes** have their own replication lag and format. Elasticsearch may store the address as a flattened text field for full-text search — another lossy transformation
- **Don't forget logs.** Exhibit D's log lines contain entity data. If a log line records `"Order ORD-123 created, shipping_address=123 Main St"`, that's a copy — immutable, unstructured, but present

**Output:** Complete storage location map for each entity — location, service, format, fields, update policy

---

## Phase 3: Trace Copy Events

**Goal:** Understand when and how each copy is created and updated.

**Process:**
1. For each copy, identify the triggering event: API call, database trigger, ETL job, message consumer
2. Map the copy chain: Source → Copy 1 → Copy 2 (is Copy 2 copied from Source or from Copy 1?)
3. Identify update propagation: when the source changes, which copies are updated and when?
4. Identify independent updates: can any copy change without updating the source?

**Thought process:**
- **Snapshot copies** (copied once, never updated) are the most common in legacy systems. They were created because "we need the address at order time." They're not wrong — an order's shipping address SHOULD be a snapshot. But the team may not realize it's a snapshot, and support agents may trust it as "the current address"
- **Event-driven copies** are rare in legacy systems (that's why Exhibit A found missing events). When they exist, they're the most reliable copies
- **ETL copies** (nightly batch sync) introduce guaranteed staleness. The warehouse is always at least 1 day behind. For analytics, this is fine. For operational decisions, it's dangerous
- **Independent updates** (a copy can change without the source knowing) are the most dangerous pattern. They create divergence that no reconciliation job can fix without business rules about which version wins
- **Copy chain depth matters.** If Copy 2 is copied from Copy 1 (not from Source), errors compound. Each hop adds latency and potential transformation errors. Map the actual chain, not the assumed one

**Output:** Copy event timeline — source → copy chain, triggering events, update propagation paths

---

## Phase 4: Run Consistency Check

**Goal:** Find actual data mismatches between the source and its copies in production.

**Process:**
1. For each copy, query the source and the copy for the same entity set (e.g., all orders from the last 90 days)
2. Compare field-by-field where format allows
3. Count mismatches and categorize: (a) expected divergence (snapshot vs current), (b) unexpected divergence (should match, doesn't)
4. For format-incompatible copies (e.g., concatenated text), document the format loss

**SQL pattern:**
```sql
SELECT
    o.order_id,
    o.shipping_address->>'postcode' AS order_postcode,
    s.postal AS shipment_postcode,
    CASE WHEN o.shipping_address->>'postcode' != s.postal
         THEN 'MISMATCH' ELSE 'OK' END AS status
FROM orders o
JOIN shipments s ON o.order_id = s.order_id
WHERE o.created_at > NOW() - INTERVAL '90 days'
    AND o.shipping_address->>'postcode' != s.postal;
```

**Thought process:**
- **Expected mismatches** (snapshot divergence) are architecturally correct but operationally confusing. Document them and ensure the team knows which copy is the "truth" for which use case
- **Unexpected mismatches** are bugs or missing propagation. These become the missing events from Finding 3 — each unexpected mismatch points to a domain event that should exist but doesn't
- **The mismatch count is a KPI.** 342 mismatches in 90 days is a concrete, measurable signal. You can track it over time: are mismatches increasing (divergence growing) or decreasing (propagation improving)?
- **Format-incompatible copies can't be checked.** If the invoice stores the address as `"John Smith, 123 Main St, Amsterdam, 1012AB, NL"`, you can't compare the postcode field-by-field. That format loss IS the finding — the copy is unreconstructable

**Output:** Consistency report — entity, source value, copy value, match/mismatch status, category

---

## Phase 5: Identify Missing Events and ACLs

**Goal:** From the lineage findings, determine what events and transformations should exist.

**Process:**
1. For each independent update path → a missing domain event (e.g., `DeliveryAddressChanged`)
2. For each format divergence → a missing or inadequate ACL (the transformation should be explicit, documented, and reversible where possible)
3. For each stale copy → evaluate whether event-driven propagation or acceptable staleness
4. Map each missing event to the aggregate that should publish it

**Thought process:**
- **Each independent update without propagation IS a missing event.** The customer calls carrier to change the delivery address → that's a `DeliveryAddressChanged` event that the Shipment Service and Consignee Service need to know about
- **Lossy format transformations need explicit ACLs.** The invoice's concatenated address is a transformation. If it's intentional (legal requirement: address must be a single string), document it as an ACL. If it's accidental (developer shortcut), fix it
- **Not every copy needs real-time sync.** The data warehouse with nightly ETL is fine for analytics. The order's snapshot address is fine for "address at time of order." The question is: does the team KNOW it's a snapshot, or do they think it's current?
- **The event catalog from Exhibit D gets extended here.** The fossilized events from Exhibit D covered state transitions. Data lineage adds data-change events: `AddressUpdated`, `PriceChanged`, `StatusCorrected`. These are a different category of events that DDD calls "domain events about entity attribute changes"

**Output:** Missing event catalog, ACL requirements, propagation design recommendations

---

## Phase 6: Map to Context Boundaries

**Goal:** Use data lineage to confirm or refine bounded context boundaries.

**Process:**
1. Each copy with different rules (different format, different update policy, different field set) = a context boundary signal
2. Group copies by their usage context: operational vs analytical vs legal vs customer-facing
3. Cross-reference with Exhibit A's contract boundaries and Exhibit C's transaction boundaries
4. Confirm: do the data lineage boundaries match the API boundaries and the transaction boundaries?

**Thought process:**
- **If data boundaries match API boundaries match transaction boundaries → the context boundary is well-defined.** All three evidence sources agree
- **If data boundaries don't match API boundaries → the API is lying.** The service exposes a clean API but internally stores data in someone else's format or reads from someone else's table
- **The "every copy is its own context" rule has limits.** A cache copy with a 5-minute TTL is not a bounded context — it's infrastructure. A data warehouse copy is analytics infrastructure, not a domain context. Apply judgment: the copy needs different BUSINESS RULES for it to be a context, not just different technology

**Output:** Context boundary recommendations informed by data lineage, cross-referenced with all previous exhibits

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Select target entities | 60% — rank by cross-service appearance | Which entity is most revealing? |
| 2. Map storage locations | 70% — schema search for matching columns | Identify caches, queues, search indexes |
| 3. Trace copy events | 40% — code analysis for write patterns | Identify independent update paths |
| 4. Consistency check | 90% — SQL comparison queries | Expected vs unexpected mismatch |
| 5. Missing events/ACLs | 30% — template from mismatches | Which events should exist? |
| 6. Map to boundaries | 20% — cross-reference matching | Architectural judgment |

---

## Technique Limitations

- **Requires production database access for consistency checks.** Schema analysis alone (Phase 2) works without production data, but the consistency check (Phase 4) needs real queries against real data
- **Format-incompatible copies can't be compared field-by-field.** Lossy transformations (concatenated strings, truncated fields) prevent automated reconciliation. The format loss itself is the finding, but you can't quantify the mismatch rate
- **Copy chains can be deep.** In a system with 4+ hops (Source → Service A → Service B → Warehouse → Report), tracing the full chain requires understanding every transformation. Each hop may introduce format changes, field drops, or timing delays
- **Caches and in-memory copies are ephemeral.** You can document that a cache exists, but you can't query its contents historically. The lineage for cached data is a point-in-time observation
- **This technique traces one entity at a time.** Tracing the address gives you one lineage. The order total may have a completely different lineage pattern. Plan to trace 3-5 core entities for a comprehensive picture
- **GDPR/privacy constraints may limit production queries.** Querying customer addresses in production for reconciliation may require anonymization or approval. Work with your DPO to define acceptable analysis patterns
