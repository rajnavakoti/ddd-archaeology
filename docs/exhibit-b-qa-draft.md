# Exhibit B: Schema Archaeology — Q&A (Final)

## Strategy

Same safety net as Exhibit A, plus one extra: **Exhibit B confirms Exhibit A.** If anyone challenges a finding, you can point to two independent evidence sources agreeing. That's stronger than either alone.

---

## Foundational Challenges

### Q1: "This requires database access. Most architects don't have production DB access."
You don't need DBA-level access. You need one of: `pg_stat_statements` output (your DBA can export it), slow query logs (ops team has these), APM span data (Datadog, New Relic DB traces), or even application-level query logging. The technique degrades gracefully — each data source gives you a subset of the picture. Even just the DDL (table definitions) without access patterns gives you Phase 4 signals: fat tables, foreign keys crossing schemas, lifecycle timestamps.

### Q2: "We use a shared ORM connection pool — all services use the same database user."
That's Finding #1: no database-level service isolation. It's not a blocker, it's evidence. Pivot to slow query log analysis where application context is in the query comments — some ORMs inject service names or request IDs. If even that's not available, you can still do Phase 4 (schema structure analysis) which needs only the DDL, not access patterns.

### Q3: "This only works for relational databases. We use MongoDB / Cassandra / DynamoDB."
The principle is identical: who reads which collection/table/partition, and who writes. The tooling differs — MongoDB Atlas profiler, Cassandra audit logs, DynamoDB CloudTrail. Shared collections with multiple writers are boundary violations regardless of the database technology. The chain-of-thought process is the same; only the SQL changes.

### Q4: "Isn't looking at the database going too low? DDD is about the domain model, not the persistence layer."
In theory, yes — the domain model should be independent of persistence. In practice, in a 12-year-old legacy system, the database IS the domain model. Nobody built a separate domain layer. The tables ARE the entities. The foreign keys ARE the relationships. The status columns ARE the lifecycle. When the textbook says "model the domain," and the reality is that the domain was modeled as tables 12 years ago — the tables are where you find it.

### Q5: "Our DBA won't give us access to pg_stat_statements — it's too sensitive."
Respect that boundary. Ask for an anonymized export: table names, accessing users, read/write classification, frequency — no actual query text. That's enough for Phases 1-3. If even that's blocked, the DDL alone (Phase 4) gives you foreign key maps, fat table detection, lifecycle timestamps, and namespace violations. You don't need runtime data for all findings.

---

## Technical Depth

### Q6: "Your SQL regex will match subquery aliases and CTE names, not actual tables."
You're right — the regex is illustrative, not production-grade. Production use requires handling schema-qualified names, CTEs, subquery aliases, and parameterized queries. The automation layer normalizes these. But for a first pass — especially in a talk demo — the regex catches 80% of cases and the findings are directionally correct. We flag edge cases in the tooling.

### Q7: "pg_stat_statements only stores 5,000 queries by default. On a high-traffic system, won't you miss important patterns?"
Yes. Low-frequency but architecturally significant queries — batch jobs, end-of-day reconciliation, stored procedures — may be evicted by high-frequency OLTP queries. That's why we supplement with slow query log analysis for completeness. The pg_stat_statements gives you the common patterns. The slow query log gives you the rare but important ones. Together they cover the full picture.

### Q8: "Foreign keys crossing schemas — isn't that just how relational databases work? You have to join tables."
Foreign keys between tables in the same bounded context are fine — that's normal relational modeling. Foreign keys crossing schema or service boundaries are coupling. The difference: if `shipment.orders.customer_id` references `customer.customers.id`, the database has enforced a relationship that ties two services together at the data layer. You can't deploy one without the other. You can't migrate one independently. That FK is a hard coupling that no API redesign can break without a database migration.

### Q9: "You said two writers to the same table is always a problem. What about append-only tables like audit logs?"
Good distinction. Append-only tables where multiple services write but nobody reads across boundaries are a different pattern — that's an event store or audit log, not a shared aggregate. The "two writer" violation specifically applies to tables where the writes are mutations (UPDATE, DELETE) on the same rows, meaning two services believe they can change the state of the same entity. Append-only inserts from multiple services are fine — that's just logging.

### Q10: "How do you handle views and materialized views? They look like tables in some queries."
Views are interesting artifacts. A view that joins across service boundaries is an explicit acknowledgment of coupling — someone needed data from multiple contexts and built a view to get it. Materialized views are even more telling: someone needed that cross-boundary data fast enough to precompute it. Both are findings. In the automation, we separate base tables from views, but both show up in the shared access analysis.

### Q11: "Stored procedures that cross schema boundaries — your technique won't catch the calling service."
Correct — that's a declared limitation. A stored procedure called by Service A might read from Service B's tables, but `pg_stat_statements` records it under the procedure's execution context, not the caller. The fix: audit stored procedure bodies for cross-schema references. That's a static analysis pass, not a runtime analysis. We flag stored procedures as potential hidden coupling vectors in Phase 2.

---

## DDD Purity

### Q12: "In DDD, the aggregate is the consistency boundary. You're finding shared tables, not shared aggregates."
True — a shared table doesn't automatically mean a shared aggregate. But in legacy systems where the table IS the aggregate (no separate domain layer), table ownership IS aggregate ownership. The finding is: if two services write to the same table, two services believe they own the same consistency boundary. Whether you call it a "shared table" or a "shared aggregate," the problem is identical: invariants can't be enforced by either service alone.

### Q13: "You're conflating data ownership with domain ownership. A service can own the data but not the domain logic."
Fair point. Reporting services read data they don't own domain logic for. That's why the read vs write distinction matters. A read-only consumer doesn't own the domain — it's a downstream dependency. A writer does own (or claims to own) the domain. The technique distinguishes them: reads are dependencies, writes are ownership claims. Two write-owners is the violation.

### Q14: "Evans says persistence should be an implementation detail. Isn't analyzing the database the opposite of DDD?"
Evans is describing the ideal. In a legacy system, the persistence IS the implementation — there's no separate domain layer. The database is the domain model. Analyzing it isn't violating DDD principles; it's acknowledging reality. The goal is to use what we find to build toward the ideal: identify the implicit domain model in the tables, then extract it into a proper domain layer. You can't refactor what you haven't mapped.

### Q15: "How do you distinguish between a legitimate Shared Kernel and accidental table sharing?"
Ask two questions: (1) Is there a governance agreement? Does someone own the shared table's schema and publish changes? (2) Do both services need the same consistency guarantees on this data? If yes to both, it's a legitimate Shared Kernel — document it and govern it. If no, it's accidental — one service started reading another's table because it was easier than building an API. The contracts from Exhibit A help here: if the shared table has no corresponding API endpoint, nobody intended to share it.

---

## Practical / Scaling

### Q16: "We have 500 tables. How do I prioritize which shared tables to investigate first?"
Priority = access frequency × violation severity. A table with 2 writers and 10,000 daily writes is P1 — active boundary violation under load. A table read by 3 services once per hour is P3 — manageable dependency. Start with multi-writer tables (boundary violations), then high-frequency multi-reader tables (tight dependencies), then low-frequency reads (can wait).

### Q17: "How often should we run this? Schemas don't change that often."
Schemas don't, but access patterns do. A service that didn't read your table last month might start this month after a new feature ships. Run the access pattern analysis quarterly at minimum. The DDL analysis (Phase 4) can run less frequently — monthly or on schema changes.

### Q18: "This is a lot of manual SQL. Can it be automated?"
Yes — Phases 1-4 are fully scriptable. The SQL in the chain-of-thought is the core logic. Wrap it in a Python script that connects to the database, runs the queries, and outputs the shared table map as JSON + Markdown. Phase 5 (cross-reference with Exhibit A) is where the agent skill takes over.

---

## Hostile / Trap

### Q19: "Have you actually run this in production, or is this theoretical?"
I ran a version of this at IKEA with a data architect. We analyzed existing database schemas across multiple services to reverse-engineer the data model — which tables were shared, where foreign keys crossed boundaries, where the real ownership lived. The full automation with `pg_stat_statements` mining is newer tooling built from that experience. The technique is proven; the tooling is evolving.

### Q20: "Isn't the real fix just event sourcing? Solve the problem at the architecture level."
Event sourcing is one solution to write coupling. But in a 12-year-old delivery platform, you can't migrate to event sourcing before you know what the domain events are. Exhibit B tells you where the coupling is. The 8 exhibits together tell you what the domain events should be — the timestamp columns from Phase 4, the lifecycle states from the status fields, the event gaps from Exhibit A. You need the diagnosis before the prescription.

### Q21: "You showed 5 tables. In a real system there are hundreds of shared tables. How do you not drown in noise?"
Filter ruthlessly. Most shared table reads in legacy systems are from reporting or analytics — read-only consumers that don't affect domain boundaries. Filter those out first. Then sort by writer count: any table with 2+ writers is a priority finding. The remaining shared reads, sort by frequency. The top 10-15 tables by these criteria give you 80% of the architectural insight. You don't need to analyze all 500.

### Q22: "Your cross-reference table assumes Exhibit A and Exhibit B findings will align. What if they contradict?"
Contradictions are the most valuable findings. If Exhibit A shows clean API boundaries but Exhibit B shows shared tables underneath — the architecture is a facade. The APIs look clean; the database tells you they're not. That gap is exactly what the archaeology is designed to find. If Exhibit A shows coupling but Exhibit B doesn't — the coupling is at runtime (API calls), not at the data layer. Both directions are informative.

### Q23: "What about microservices that share a database but use separate schemas? Is that still a boundary violation?"
Separate schemas with no cross-schema foreign keys and no cross-schema queries is a reasonable intermediate step toward database-per-service. It's not ideal, but it's significantly better than shared tables. The technique still applies — you check for cross-schema access the same way you check for cross-service access. If Service A queries tables in Service B's schema, the schema separation is cosmetic.

---

## Confrontation

### Q24: "Sam Newman says 'shared databases are the devil.' You're spending a whole exhibit analyzing something the industry has already solved."
Newman is right about the goal. The industry has NOT solved it for legacy systems. Database-per-service is the target architecture. But the 12-year-old delivery platform we're analyzing was never decomposed. The shared database exists. Pretending it doesn't won't make the coupling disappear. Schema Archaeology tells you what you need to decompose, in what order, and where the boundary violations are worst. You can't get to Newman's ideal without first understanding the current state.

### Q25: "This is just standard database dependency analysis. DBAs have been doing this for decades. What's the DDD angle?"
DBAs analyze dependencies for performance and migration planning. The DDD angle is interpreting the findings through the lens of bounded contexts: a shared table isn't just a dependency — it's evidence of a missing or violated context boundary. A two-writer table isn't just a concurrency risk — it's two aggregates competing for ownership. A fat table isn't just bad normalization — it's a god entity at the persistence layer. The DDD vocabulary transforms operational findings into architectural decisions.

---

## Danger Level Summary

| Category | Questions | Danger Level |
|----------|-----------|-------------|
| Foundational (access, tooling) | Q1-Q5 | Medium |
| Technical depth | Q6-Q11 | High |
| DDD purity | Q12-Q15 | **Highest** |
| Practical / scaling | Q16-Q18 | Medium |
| Hostile / trap | Q19-Q23 | High |
| Confrontation (Newman) | Q24-Q25 | **Highest** |

## Your Strongest Answers
- Q4 ("the database IS the domain model in legacy" — reframes the whole exhibit)
- Q12 ("the table IS the aggregate" — shuts down the purity challenge)
- Q22 ("contradictions are the most valuable findings" — shows layered methodology)
- Q24 (Newman reframe — "you can't get to the ideal without mapping the current state")
- Q19 (IKEA story — real experience, same as Exhibit A)
