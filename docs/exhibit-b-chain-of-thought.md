# Schema Archaeology — Chain of Thought Process

## What Is This?

A systematic process for discovering hidden coupling, boundary violations, and missing bounded contexts by analyzing which database tables are accessed by which services. While Contract Archaeology (Exhibit A) reveals the declared architecture, Schema Archaeology reveals the real integration layer — the database.

**Input:** Database access logs (pg_stat_statements, slow query logs, connection pool metadata), database schema (DDL), service-to-database-user mapping
**Output:** Shared table map, boundary violation report, missing context candidates, read/write coupling matrix

---

## Why the Database Matters

In legacy systems, the database is often the oldest, most stable artifact. Services are rewritten, APIs are versioned, documentation rots — but the tables persist. A table created in 2014 is still being accessed by a service built in 2023. The schema is the geological record of every architectural decision.

More importantly: **services can lie through their APIs but can't lie to the database.** A service may expose a clean REST interface while underneath, it reads 15 tables from 3 other services' schemas. The database sees everything.

---

## Phase 1: Map Service-to-Database-User Relationships

**Goal:** Know which database connections belong to which services.

**Process:**
1. List all database users/roles that connect to the production database
2. Map each user to its owning service (naming conventions: `svc_order`, `svc_delivery`, etc.)
3. Identify shared users (e.g., `app_user` used by multiple services) — these are blind spots
4. Note any ORM-generated queries vs raw SQL — ORMs leave fingerprints in query patterns

**Thought process:**
- If all services use the same database user → you can't distinguish who's accessing what. This is itself a finding: no database-level service isolation. Flag for infrastructure team
- If services have dedicated users → you can correlate queries to services via `pg_stat_statements`, query logs, or connection pool metadata
- Shared users (like a reporting user) should be tracked separately — they're read-only consumers, not domain services
- **Ghost services:** If a database user exists but no running service maps to it → that's a ghost service. In a 12-year-old vendor-built platform, ghost users are common and dangerous. They represent: decommissioned services whose scheduled jobs still run, ETL pipelines nobody documented, vendor tools "turned off" but whose credentials still work, or migration scripts that ran once in 2019 and were never cleaned up. A ghost user with WRITE access to a critical table is a hidden writer that won't appear in any service inventory or architecture diagram

**Output:** Service → database user mapping table, with blind spots flagged

---

## Phase 2: Extract Table Access Patterns

**Goal:** Determine which services touch which tables, and how (read vs write).

**Process:**
1. Query `pg_stat_statements` (PostgreSQL) or equivalent for your database
2. Parse query text to extract table names from FROM, JOIN, INTO, UPDATE clauses
3. Correlate with database user to determine which service executed the query
4. Classify access: SELECT = read, INSERT/UPDATE/DELETE = write
5. Count query frequency — a table hit 10,000 times/day is more significant than one hit once/month

**SQL for PostgreSQL:**
```sql
WITH service_table_access AS (
    SELECT DISTINCT
        u.usename AS db_user,
        (regexp_matches(s.query, '(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)', 'gi'))[1] AS table_name,
        CASE 
            WHEN s.query ~* '^SELECT' THEN 'READ'
            WHEN s.query ~* '^(INSERT|UPDATE|DELETE)' THEN 'WRITE'
            ELSE 'OTHER'
        END AS access_type
    FROM pg_stat_statements s
    JOIN pg_user u ON s.userid = u.usesysid
    WHERE s.query ~* '(SELECT|INSERT|UPDATE|DELETE)'
)
SELECT table_name, db_user, access_type, COUNT(*) AS query_count
FROM service_table_access
GROUP BY table_name, db_user, access_type
ORDER BY query_count DESC;
```

**SQL caveat:** This regex is illustrative — production use requires handling schema-qualified names (`schema.table`), CTEs, subquery aliases, and parameterized queries where table names may be in query templates rather than the executed text. The automation layer normalizes these before analysis.

**Thought process:**
- High-frequency reads from another service's table → tight runtime dependency. If that table's schema changes, the reading service breaks silently
- Any writes to another service's table → boundary violation. This is the highest-priority finding
- Tables accessed by only one service → well-bounded. These tables belong to that service's context
- Tables accessed by many services but only read → candidate for event publishing or read replica
- Tables with no access at all → dead tables. May be remnants of decommissioned features. Worth investigating before deleting

**Output:** Table access matrix — table × service × access type (read/write) × frequency

---

## Phase 3: Identify Shared Tables

**Goal:** Find tables accessed by more than one service.

**Process:**
1. Filter the access matrix for tables with 2+ distinct services
2. For each shared table, classify the sharing pattern:
   - **Single writer, multiple readers** — one owner, downstream consumers (manageable)
   - **Multiple writers** — boundary violation (critical)
   - **All readers, no clear owner** — orphaned table or missing context
3. Cross-reference with the schema DDL — which service's schema/namespace contains the table?

**Thought process:**
- **Single writer, multiple readers:** The writing service owns this table. Readers are coupled but not violating boundaries. Fix: publish events or provide a read API so readers don't need direct table access. Priority depends on how often the schema changes
- **Multiple writers:** This is always a problem. Two services writing to the same table means two owners for the same aggregate. Invariants can't be enforced. Race conditions are likely. This is the highest-priority finding in Schema Archaeology
- **All readers, no clear owner:** The table exists but no service claims it via writes. It's either: (a) written by a legacy process (stored procedure, batch job, ETL), or (b) truly orphaned — data was loaded once and everyone reads it. Both are missing contexts that should become explicit services
- **Table namespace matters:** If `orders` lives in the `shipment` schema but is read by the `invoicing` user, that's a clear cross-boundary access. If schemas aren't used, table naming conventions may hint at ownership (`order_*`, `delivery_*`, `billing_*`)

**Output:** Shared table report — table, service count, access pattern classification, owner candidate

---

## Phase 4: Analyze Schema Structure for Domain Signals

**Goal:** Extract domain knowledge from the table definitions themselves.

**Process:**
1. Extract DDL for all shared tables
2. Analyze foreign key relationships — these are the database's version of entity relationships
3. Identify junction/bridge tables — these often represent domain relationships that aren't modeled explicitly
4. Look at column naming patterns across tables — same vocabulary drift as API schemas
5. Check for enum-like columns (status fields) — these reveal domain lifecycles
6. Identify soft-delete patterns (`deleted_at`, `is_active`) — these reveal domain events that should be explicit

**Thought process:**
- Foreign keys crossing schema boundaries → explicit coupling at the database level. If `shipment.orders.customer_id` references `customer.customers.id`, the database has enforced a relationship that may or may not be in the API contracts
- **Status columns reveal domain lifecycles:** `order_status VARCHAR` with values like `draft, placed, confirmed, picking, packed, shipped, delivered, cancelled, returned` tells you the full lifecycle of the aggregate. Compare to the API's enum values (from Exhibit A) — differences reveal states that exist in the database but aren't exposed through the API
- **Timestamp columns reveal domain events:** `created_at`, `confirmed_at`, `shipped_at`, `delivered_at` — each timestamp is an implicit domain event. If these timestamps exist but no corresponding events are published (from Exhibit A), the service is tracking lifecycle changes without announcing them
- **Soft deletes vs hard deletes:** If a table uses `deleted_at` timestamps instead of actual DELETE, the domain considers these records valuable even after "deletion." This is often a regulatory or audit requirement that isn't visible in the API
- **Fat tables (60+ columns):** A table with 60+ columns in a system supposedly decomposed into microservices is almost always a legacy monolith's core table that was never split. These are the database equivalent of a god entity — they accumulate every concept that was ever loosely related to the core domain object. Column count alone tells you where the next decomposition effort needs to start
- **Indexes as query pattern fossils:** The indexes on a shared table tell you *how* each service uses it. If `orders` has indexes on `carrier_id`, `invoice_id`, and `warehouse_id`, those indexes are the database's memory of every service that was given read access. Each index is a fossil of a coupling decision. This is particularly valuable when `pg_stat_statements` history has been rotated — indexes persist long after query history is gone
- **Table naming namespace violations:** In a well-governed database, tables are prefixed or schema-separated by owning service (`shipment_orders`, `carrier_tracking_events`). Tables with no clear ownership prefix — or tables prefixed with one service's namespace accessed by another service's user (e.g., `shipment_status` written by `svc_carrier`) — are namespace violations that signal the boundary was never real

**Output:** Schema analysis report — foreign key map, lifecycle states, implicit events, cross-schema references, fat table flags, index fossils, namespace violations

---

## Phase 5: Cross-Reference with Exhibit A

**Goal:** Validate and deepen Contract Archaeology findings using database evidence.

**Process:**
1. For each god entity found in Exhibit A → check if the table is accessed by the same services that the API showed coupling to. Is the database coupling broader or narrower?
2. For each dead boundary found in Exhibit A → check if the two services share tables. Shared tables confirm the boundary is fictional
3. For each missing events finding → check if the table has timestamp columns that represent lifecycle changes. These are the events that should exist but don't
4. For each vocabulary drift → check column names across shared tables. Does the database use the same fractured vocabulary as the APIs?
5. Look for **new findings** — coupling that Exhibit A couldn't see because it was below the API layer

**Thought process:**
- If Exhibit A shows clean API boundaries but Exhibit B shows shared tables → the architecture is a facade. The real coupling is in the database
- If Exhibit A shows coupling AND Exhibit B confirms it → high-confidence finding. Two independent evidence sources agree
- If Exhibit A shows coupling but Exhibit B doesn't → the coupling may be at runtime (API calls, not shared data). Check with Exhibit D (log mining)
- **New findings are the highest value.** Things Exhibit A couldn't see: direct table reads bypassing APIs, stored procedures that cross boundaries, batch jobs that read from multiple service schemas, reporting queries that join across contexts

**Output:** Cross-reference report — Exhibit A finding, database evidence (confirms/deepens/contradicts), confidence adjustment

---

## Phase 6: Generate Recommendations

**Goal:** Produce actionable recommendations from the database findings.

**Process:**
1. For multi-writer tables → recommend ownership decision + coordination mechanism
2. For single-writer/multi-reader tables → recommend event publishing or read API
3. For orphaned tables → recommend explicit context creation or decommission investigation
4. For cross-schema foreign keys → recommend whether to keep (legitimate relationship) or break (coupling violation)
5. Prioritize by: write violations first, then high-frequency read coupling, then structural issues

**Prioritization formula (same as Exhibit A):**
- **Priority = Access Frequency × Violation Severity**
- A table with 2 writers and 10,000 daily writes = P1 (active boundary violation under load)
- A table read by 3 services once per hour = P3 (manageable dependency)
- Adjust confidence based on Exhibit A cross-reference — findings confirmed by both exhibits are higher priority

**Output:** Prioritized recommendation list with evidence from both database and contracts

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Service-user mapping | 70% — query pg roles | Map shared users to services |
| 2. Table access extraction | 100% — parse pg_stat_statements | — |
| 3. Shared table identification | 90% — filter + classify | Is this sharing intentional? |
| 4. Schema structure analysis | 80% — parse DDL, trace FKs | Is this a domain lifecycle or just a status flag? |
| 5. Cross-reference Exhibit A | 60% — match names | Interpret discrepancies |
| 6. Recommendations | 20% — template generation | All judgment: what to fix, in what order |

**Scripts handle Phases 1-4. Agent skills handle Phases 5-6. Humans review everything.**

---

## Key Principle

**Read coupling is dependency. Write coupling is a boundary violation.**

Always separate reads from writes in your analysis. A service reading another service's table is like a Customer-Supplier relationship — manageable, should be explicit. Two services writing to the same table is like two aggregate owners — invariants can't be enforced, and this is where your 3 AM pages come from.

---

## Technique Limitations

- **Requires database access.** If you can't access `pg_stat_statements` or query logs, this technique is blocked. Fall back to application-level logging (Exhibit D)
- **Shared database users are blind spots.** If all services use the same `app_user`, you can't distinguish who's accessing what
- **Stored procedures hide access patterns.** A stored procedure called by Service A might read tables from Service B's schema — this doesn't show up as Service A's access in all logging tools
- **Read replicas complicate the picture.** If services read from a replica, the access may not show up in the primary's `pg_stat_statements`
- **`pg_stat_statements` has a query cap.** Default is 5,000 tracked queries. On high-traffic systems processing millions of daily transactions, low-frequency but architecturally significant queries — batch jobs, end-of-day reconciliation, stored procedures — may be evicted. Supplement with slow query log analysis for a complete picture
- **Database-per-service prevents direct sharing but not data duplication.** If each service has its own database, there are no shared tables — which is a strong architectural signal. But it doesn't prevent data duplication coupling, where services copy each other's data into their own database and keep it in sync via polling or events. The coupling exists at the data *model* level, not the database access level. If you have database-per-service, the shared table technique doesn't apply — move to data lineage tracing to find duplicated data patterns
