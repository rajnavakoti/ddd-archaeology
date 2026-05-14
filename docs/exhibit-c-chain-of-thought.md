# Transaction Boundary Analysis — Chain of Thought Process

## What Is This?

A process for discovering aggregate boundaries by analyzing which database tables are consistently written together in the same transaction. While Schema Archaeology (Exhibit B) reveals who accesses what, Transaction Boundary Analysis reveals what must be consistent with what — the deepest coupling signal.

**Input:** APM trace data (Datadog, New Relic, Jaeger spans), database transaction logs, or slow query logs with transaction markers
**Output:** Transaction cluster map, aggregate candidates, boundary violation report, extraction readiness assessment

---

## Why Transactions Matter

Aggregates are consistency boundaries. In DDD, an aggregate is a cluster of domain objects that are treated as a single unit for data changes. The database already enforces this: everything committed in a single `BEGIN...COMMIT` block must succeed or fail together.

In a legacy system where nobody explicitly designed aggregates, the transaction patterns ARE the aggregate design. Every co-write that was ever coded — deliberately or under deadline pressure — persists in the transaction log. These implicit aggregates determine what you can and can't extract when decomposing the system.

**Key principle:** If two tables are always written in the same transaction, they belong to the same aggregate. If two tables from different services are written in the same transaction, that's a boundary violation that blocks service extraction.

---

## Phase 1: Collect Transaction Data

**Goal:** Get write co-occurrence data — which tables are modified together in the same transaction.

**Process:**
1. **APM traces (preferred):** Query your APM tool for database spans with write operations (INSERT, UPDATE, DELETE) grouped by trace/transaction ID
2. **PostgreSQL query log:** Parse `log_statement = 'all'` output for BEGIN...COMMIT blocks, extract table names from write statements
3. **pg_stat_activity snapshots:** If you have periodic snapshots, correlate concurrent writes from the same backend PID
4. **Application-level logging:** If ORM logs are available, extract transaction boundaries from the application's unit-of-work pattern

4. **Static analysis (if source access available):** `@Transactional` annotations (Spring/Java), `atomic` blocks (Django), `using transaction.atomic()` (Python), `DbContext.SaveChanges()` scope (Entity Framework) — these are the developer's declared transaction boundaries. Static analysis of these annotations + the repository calls within them gives you the transaction clusters without any runtime data. This is the most reliable source when you have code access — it shows intent, not just behavior

**Data needed per transaction:**
- Transaction/trace ID
- Service name (from APM service tag or database user)
- List of tables modified (INSERT, UPDATE, DELETE targets)
- Timestamp
- Duration (optional but useful for identifying slow cross-boundary transactions)

**Thought process:**
- 7 days of data is usually sufficient for pattern detection — captures daily and weekly cycles
- Filter out read-only transactions — only writes reveal aggregate boundaries
- Filter out DDL statements (CREATE, ALTER, DROP) — these are schema changes, not domain transactions
- Watch for **ORM artifacts:** ORMs like Hibernate/SQLAlchemy may batch writes that aren't semantically part of the same aggregate. A lazy-loaded collection flush is not the same as a designed consistency boundary. Cross-reference with high frequency: if the co-write happens 80,000+ times, it's intentional. If it happens 50 times, it might be an ORM accident

**Output:** Raw transaction data — list of (transaction_id, service, [tables_modified], timestamp)

---

## Phase 2: Cluster Co-Occurring Writes

**Goal:** Group tables that consistently appear together in transactions.

**Process:**
1. For each transaction, create a sorted set of modified tables
2. Group identical sets and count occurrences
3. Sort by frequency — highest count first
4. Tag each cluster with the service that executed it

**SQL pattern (against APM data):**
```sql
SELECT
    tables_modified,
    COUNT(*) AS occurrence_count,
    service_name
FROM (
    SELECT
        transaction_id,
        ARRAY_AGG(DISTINCT db_table ORDER BY db_table) AS tables_modified,
        service_name
    FROM apm_spans
    WHERE db_operation IN ('INSERT', 'UPDATE', 'DELETE')
        AND start_time > NOW() - INTERVAL '7 days'
    GROUP BY transaction_id, service_name
    HAVING COUNT(DISTINCT db_table) > 1
) grouped
GROUP BY tables_modified, service_name
ORDER BY occurrence_count DESC;
```

**Thought process:**
- Clusters with 10,000+ occurrences = strong aggregate candidates. These are not accidental
- Clusters with 100-1,000 occurrences = investigate. Could be legitimate but less common flows, or could be batch operations
- Clusters with <100 occurrences = possible ORM artifacts, one-time migrations, or developer mistakes. Low signal, high noise. Don't ignore them but don't prioritize them
- **Single-table transactions** are also informative: if a table is almost always written alone, it's likely its own aggregate root. If it's sometimes written alone and sometimes with others, the "with others" pattern needs investigation

**Output:** Frequency-sorted transaction cluster table — [table set, count, service, classification]

---

## Phase 3: Classify Transaction Clusters

**Goal:** Determine which clusters are legitimate aggregates and which are boundary violations.

**Classification rules:**

### Clean Aggregate
- All tables in the cluster belong to the same service
- High frequency (10,000+ per week)
- Tables have clear parent-child relationship (e.g., `orders` + `order_lines`)
- **Assessment:** This is a well-defined aggregate. No action needed.

### Cross-Context Transaction
- Tables in the cluster span two or more services (based on Exhibit B's ownership data)
- Any frequency is concerning, but higher frequency = higher priority
- **Assessment:** Boundary violation. This transaction couples two contexts at the deepest level — the consistency guarantee. Must be refactored before service extraction.

### Distributed Concern Handled Locally
- A service writes to its own table AND a table owned by another service in the same transaction
- Common pattern: order creation + inventory reservation, payment + invoice generation
- **Assessment:** Works in a monolith. Breaks the moment you extract either service. This becomes a saga or eventual consistency pattern during decomposition.

### Surprising Co-Write
- Tables that semantically don't belong together appear in the same transaction
- Low frequency, often a legacy code path nobody remembers
- **Assessment:** Investigate. This is either a bug, a legacy workaround, or a business rule nobody documented. Talk to the team.

### Audit/Logging Co-Write
- A domain table + an audit/log table committed together
- Very high frequency, expected pattern
- **Assessment:** Clean. The audit table is part of the aggregate's write concern, not a separate context. Don't flag as a violation.

**Thought process:**
- Use Exhibit B's shared table ownership to determine which service "owns" each table
- If a transaction writes to tables owned by two different services → cross-context violation
- If a transaction writes to a table + its audit/history table → clean aggregate pattern, not a violation
- **The count matters:** 84,000 co-writes = this is the system's core operation. 2,100 co-writes = this is a secondary flow, possibly a coupling leak. 50 co-writes = noise or edge case

**Output:** Classified transaction clusters with assessment and priority

---

## Phase 4: Identify Aggregate Boundaries

**Goal:** From the classified clusters, draw the actual aggregate boundaries.

**Process:**
1. Each "clean aggregate" cluster = one aggregate boundary
2. Name the aggregate after the root table (the table that appears in the most clusters, or the table with the primary identity)
3. Map child tables to their aggregate root
4. Identify tables that appear in multiple clusters = shared between aggregates (potential extraction complication)

**Thought process:**
- The table that gives identity to the cluster is the aggregate root: `orders` is the root, `order_lines` and `order_audit` are children
- If a table appears in two different clean clusters from the same service, it might be part of two aggregates — or the service has two aggregates that share a table (unusual but possible)
- **Cross-reference with Exhibit A:** Do the aggregate boundaries match the API's entity structure? If the API has `Order` as an aggregate root with `/orders/{id}/lines` as a sub-resource, and the transaction log shows `{orders, order_lines}` as a cluster — the API and the transactions agree. If they don't agree, investigate why
- **Cross-reference with Exhibit B:** Do the aggregate tables match the service's owned tables? If a clean aggregate writes to a table that Exhibit B flagged as "owned by another service" — the ownership is wrong, or the transaction is a violation

**Output:** Aggregate boundary map — aggregate root, child tables, owning service, confidence level

---

## Phase 5: Assess Extraction Readiness

**Goal:** For each service/context, determine if it can be safely extracted into an independent service.

**Process:**
1. List all transaction clusters involving this service's tables
2. Separate clean (internal) clusters from cross-context clusters
3. For each cross-context cluster, assess:
   - Frequency (how often does this coupling execute?)
   - Direction (which service initiates the transaction?)
   - Refactoring difficulty (can this become a saga? An event? A synchronous API call?)

**Extraction readiness classification:**

| Status | Criteria |
|--------|----------|
| **Ready to extract** | All transaction clusters are internal. No cross-context co-writes. Clean aggregate boundaries. |
| **Extractable with work** | 1-2 cross-context clusters, low frequency (<1,000/week). Can be refactored to saga/events. |
| **Blocked** | High-frequency cross-context clusters (>5,000/week). Refactoring required before extraction. |
| **Entangled** | Multiple high-frequency cross-context clusters touching 3+ services. Major redesign needed. |

**Thought process:**
- A service that only commits to its own tables = ready to extract tomorrow
- A service that occasionally writes to another service's table = refactor the co-write first, then extract
- A service that always writes to another service's table in its core operation = these two services are actually one context (confirms Exhibit A's dead boundary finding)
- **The strangler fig application:** For each service, the extraction readiness tells you the order of the strangler fig migration. Extract "ready" services first. Then "extractable with work." Leave "entangled" for last — they need the most redesign

**Output:** Extraction readiness report per service/context

---

## Phase 6: Cross-Reference with Exhibits A and B

**Goal:** Validate and deepen previous findings with transaction evidence.

**Cross-reference patterns:**

| Previous finding | Transaction evidence to look for |
|-----------------|----------------------------------|
| God entity (Exhibit A) | Does the god entity's table appear in cross-context transactions? If yes, the god entity is also a transactional coupling point |
| Dead boundary (Exhibit A) | Do the two services co-write in transactions? If yes, the boundary is dead at every level |
| Missing events (Exhibit A) | Do lifecycle timestamps from Exhibit B correspond to transaction boundaries? Each timestamp set within a transaction IS the event that should be published |
| Two-writer violation (Exhibit B) | Is the two-writer pattern in the same transaction or separate? Same transaction = designed coupling. Separate transactions = race condition risk |
| Ghost users (Exhibit B) | Do ghost users appear in transaction clusters? If yes, the ghost process is part of an aggregate nobody knows about |

**The timestamp connection:** Exhibit B found lifecycle timestamps (`confirmed_at`, `shipped_at`, `delivered_at`). Each of these is set within a transaction cluster. The transaction that sets `confirmed_at` on the order IS the `OrderConfirmed` event that should be published but isn't. The transaction boundary tells you exactly what data changes constitute that event — and that's the event payload.

**Output:** Cross-reference validation report with confidence adjustments

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Collect transaction data | 80% — query APM/logs | Access negotiations, data source selection |
| 2. Cluster co-occurring writes | 100% — SQL grouping | — |
| 3. Classify clusters | 70% — rule-based classification | Is this co-write intentional or accidental? |
| 4. Identify aggregate boundaries | 60% — root detection heuristics | Is this really one aggregate or two? |
| 5. Extraction readiness | 50% — threshold-based scoring | Can this actually be refactored to a saga? |
| 6. Cross-reference | 40% — name matching | Interpret discrepancies between exhibits |

**Scripts handle Phases 1-2. Rules + heuristics handle 3-4. Agent skills handle 5-6.**

---

## Technique Limitations

- **Requires transaction-level observability.** If your APM doesn't capture database spans, or your database doesn't log transaction boundaries, this technique is blocked. Fall back to code analysis (look for `@Transactional` annotations or explicit `BEGIN/COMMIT` in the source)
- **ORM batching creates false co-writes.** ORMs flush dirty objects at transaction commit, which may batch writes that aren't semantically part of the same aggregate. Cross-reference with frequency: true aggregates have high co-occurrence. ORM artifacts are sporadic
- **Read-for-write patterns are invisible.** If a service reads from Table A, computes something, then writes to Table B in the same transaction — only the write to B appears. The read dependency on A is hidden. Combine with Exhibit B for the read dependencies
- **Stored procedures may bundle unrelated writes.** A stored procedure might write to 5 tables from 3 different contexts in one transaction "for performance." That's a procedural coupling, not an aggregate boundary. Check stored procedure bodies separately
- **Async write patterns (queues, events) won't appear.** If a service publishes an event and a consumer writes to another table asynchronously, those writes happen in separate transactions. This is actually correct eventual consistency — but it means the technique underreports clean patterns. Event-driven writes look like separate aggregates, which they are
- **Short-lived transactions only.** Long-running transactions (batch jobs, reports) that lock many tables for minutes are a different pattern. Filter by duration — aggregate transactions typically complete in milliseconds
