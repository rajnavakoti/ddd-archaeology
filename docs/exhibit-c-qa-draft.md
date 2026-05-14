# Exhibit C: Transaction Boundary Analysis — Q&A (Final)

## Strategy

Exhibit C is the deepest forensic technique — it proves coupling at the consistency layer, which is the hardest to deny. Your strongest defense: "The database doesn't have opinions. It just commits what the code tells it to. These aren't my interpretations — these are the system's actual consistency decisions."

---

## Foundational Challenges

### Q1: "This requires APM traces with database span-level detail. Most teams don't have that."
You need one of four sources, in order of preference: (1) APM with DB monitoring (Datadog, New Relic) — richest data, (2) PostgreSQL query logs with `log_statement = 'all'` — parse BEGIN/COMMIT blocks, (3) Application-level ORM logging — most ORMs can log SQL with transaction boundaries, (4) Static code analysis — find `@Transactional` annotations and trace which repositories are called within them. The technique degrades gracefully. Even static analysis alone gives you intentional aggregate boundaries.

### Q2: "We use eventual consistency already — no shared database transactions."
Then Exhibit C confirms your architecture is already decomposed at the transaction layer — that's a positive finding. The absence of cross-context transactions means your service boundaries are real, not fictional. Move to Exhibit D (log mining) to verify the eventual consistency is actually working — do the events arrive? Are there gaps? Exhibit C's "no finding" is still a finding.

### Q3: "Our monolith uses a single database transaction for everything — one big commit per request."
That's a common pattern and it's still analyzable. Within that single commit, which tables are ALWAYS modified together and which are SOMETIMES modified together? The "always together" set is your aggregate. The "sometimes together" set is where conditional coupling lives — specific code paths that create cross-context writes. The frequency data separates the core aggregate from the conditional coupling.

### Q4: "In a microservice architecture, there are no shared database transactions. This only works for monoliths."
Correct — and that's the point. This technique is designed for legacy systems where the monolith's database is the real integration layer. If you have database-per-service, the boundaries are already enforced at the data layer. Exhibit C is most valuable during the transitional phase: you have "microservices" that still share a database, or a monolith you're planning to decompose. It tells you the extraction order.

---

## Technical Depth

### Q5: "ORMs create false co-writes by flushing dirty objects. How do you distinguish real aggregates from ORM artifacts?"
Frequency. A true aggregate co-write happens 80,000 times in a week because it's the core business operation. An ORM flush that batches a Customer read-for-validation with an Order write happens 40 times — sporadic, low-frequency, doesn't make semantic sense. If you see a low-frequency cluster with unrelated tables, it's almost always an ORM artifact. Filter by a threshold — 1,000+ occurrences per week is a safe floor for real aggregate signals.

### Q6: "APM traces don't always capture which specific tables are written — they capture spans at the service call level."
Depends on your APM instrumentation. Datadog APM with Database Monitoring captures table-level spans. Jaeger with OpenTelemetry DB instrumentation does. Without table-level detail, you can still identify which service-to-service calls happen in the same trace — that tells you which services participate in the same logical transaction, even if you can't see the specific tables. For table-level detail without APM, fall back to `pg_stat_statements` or ORM query logging.

### Q7: "Two-phase commit solves the cross-context transaction problem. Why use sagas?"
2PC is a distributed transaction protocol that requires all participants to support it, introduces a coordinator single point of failure, and holds locks across services during the prepare phase. At the scale of a delivery platform processing millions of daily transactions, 2PC under load is a reliability risk worse than the coupling it solves. Sagas trade atomicity for availability — compensating transactions instead of distributed locks. At enterprise scale, that's the right trade.

### Q8: "Stored procedures that write to multiple tables in one transaction — how do you handle those?"
Stored procedures are a special case. They bundle multiple writes in one transaction for performance, but the writes may span context boundaries. You can't see the calling service in `pg_stat_statements` — you see the procedure execution. The fix: audit stored procedure bodies for which tables they write to. That's a static analysis pass, separate from the runtime transaction mining. Flag stored procedures as potential hidden coupling vectors and analyze their bodies separately.

### Q9: "What about async patterns — message queues, events that trigger writes in other services?"
Async writes happen in separate transactions by definition — the publisher commits, then the consumer commits independently. This is correct eventual consistency and won't appear as a co-write cluster. That's actually a good sign. The technique specifically finds synchronous coupling. Async decoupling is invisible to Exhibit C, which means if you DON'T see a cross-context co-write, the services might already be communicating asynchronously. Confirm with Exhibit D (log mining).

### Q10: "How do you handle read-for-write patterns where a service reads from one table and writes to another in the same transaction?"
The read dependency is invisible in the write cluster — only the write shows up. That's a limitation. But Exhibit B covers the read coupling. Combine: Exhibit C tells you what's written together (aggregate), Exhibit B tells you what's read together (dependency). The write cluster defines the aggregate boundary. The read dependency defines what the aggregate needs to function. Both matter for extraction planning.

---

## DDD Purity

### Q11: "You're inferring aggregates from database transactions. In DDD, aggregates are designed from domain invariants, not implementation details."
In a greenfield system, absolutely — you design aggregates from business rules. In a 12-year-old legacy system, nobody designed aggregates. The code evolved. Developers added writes to transactions because "this data must be consistent." Over 12 years, those decisions ARE the domain invariants — they're just implicit. The transaction log makes them explicit. The goal isn't to accept them as correct — it's to discover them so you can redesign them intentionally.

### Q12: "An aggregate should have one root entity. Your transaction clusters might group unrelated tables that happen to share a transaction."
True — and that's what the classification step handles. A cluster like `{orders, order_lines, order_audit}` has a clear root (`orders`) with children. A cluster like `{orders, shipments}` has two potential roots from different contexts — that's not an aggregate, it's a violation. The technique distinguishes them: parent-child co-writes = aggregate. Peer-to-peer co-writes across contexts = coupling.

### Q13: "You said the transaction that sets `confirmed_at` IS the `OrderConfirmed` event. But the event should capture domain intent, not just a timestamp change."
Fair point. The transaction captures more than just the timestamp — it captures ALL the data changes in that commit: the status change, the confirmation timestamp, any line item adjustments, the audit record. That full set of changes IS the event payload — the "what changed" part. The "why it changed" — the domain intent — comes from the API call or command that triggered the transaction. You need both: Exhibit A (the command) + Exhibit C (the state change) = the complete domain event.

### Q14: "Evans says aggregates should be small. Your 84,000-occurrence cluster with 3 tables might be too large."
Evans says aggregates should be as small as possible while maintaining consistency. `{orders, order_lines, order_audit}` is 3 tables — that's actually quite small. The 84,000 occurrences is the frequency, not the size. An order with 5 line items and 1 audit record is a small aggregate. The high frequency means it's the core business operation, not that the aggregate is bloated. If you found a cluster with 15 tables, THAT would be a "too large" signal — likely a transaction that's doing too much.

---

## Practical / Scaling

### Q15: "We process 10 million transactions per day. Analyzing all of them is impractical."
Sample. Take 7 days of data, sample 10% of transactions, and the clusters will be the same — the patterns are stable at high frequency. A table pair that co-writes 84,000 times in full data will show ~8,400 times in a 10% sample. The signal is the same. For low-frequency patterns (<1,000/week), you need full data. For aggregate discovery, sampling works fine.

### Q16: "How do I present this to a team that didn't design aggregates and doesn't use DDD vocabulary?"
Don't use DDD vocabulary. Say: "Here are the tables that are always committed together in your database. These groups can't be split without changing the code. Here's which groups span two teams' data — those are the ones that will break when we try to split the system." The extraction readiness framework (Ready / Extractable / Blocked / Entangled) speaks to anyone planning a decomposition, DDD or not.

### Q17: "The extraction readiness assessment — how do you validate it before committing to a migration?"
Run a proof of concept: take one "Ready to extract" service, put it behind a feature flag, route a percentage of traffic to the extracted version. If nothing breaks — the assessment was correct. For "Blocked" services, the validation is different: write the saga version of the cross-context transaction, run it alongside the monolith transaction with dual-write, compare results. The transaction clusters tell you exactly which code paths need saga conversion.

---

## Hostile / Trap

### Q18: "You said high-frequency co-writes are intentional aggregates. But what if the high-frequency pattern is a bug that's been in production for 10 years?"
Then that bug is load-bearing. The system has been correct in production at high frequency for 10 years, which means the business process depends on this coupling even if the code that implements it is wrong. You still have to untangle it carefully — you just call it a legacy constraint rather than a designed aggregate. The technique finds what's there, not what should be there. Whether it's a designed aggregate or a load-bearing bug, the extraction plan is the same: you can't break it without a replacement.

### Q19: "Event sourcing eliminates this whole problem. Why not just use it?"
Event sourcing requires knowing what the events are before you can implement it. The transaction clusters tell you what the events are — `OrderConfirmed` is the transaction that sets `confirmed_at` and modifies `order_lines`. `ShipmentCreated` is the transaction that writes to `shipments` and `tracking_events`. You need Exhibit C to design your event sourcing model correctly. Jumping to event sourcing without understanding the current transaction structure means you'll model the wrong events.

### Q20: "You're telling architects to read database transaction logs. That's DBA work, not architecture work."
In a legacy system, the database IS the architecture. The transactions are the consistency decisions. The DBA sees performance and resource usage. The architect sees domain boundaries and coupling. Same data, different lens. The DDD vocabulary transforms transaction analysis into architectural decisions — just like Exhibit B transforms table access analysis into boundary violations. The DBA gives you the data. DDD gives you the meaning.

### Q21: "Your extraction readiness framework assumes you want to extract into microservices. What if the monolith is the right answer?"
Then the transaction clusters confirm you made the right call. Clean, internal-only aggregates with no cross-context writes means the monolith has well-defined internal boundaries. You can modularize without distributing — use modules, packages, or bounded context namespaces within the monolith. The technique is neutral about the destination. It maps the current state. Whether you extract to services or modularize in-place, you need to know where the aggregate boundaries are.

---

## Confrontation

### Q22: "Michael Nygard talks about 'architectural quanta' — the smallest deployable unit. Aren't you just finding quanta, not aggregates?"
There's overlap. Nygard's architectural quantum is the smallest independently deployable unit that includes all the code, infrastructure, and data needed for a function. An aggregate is a consistency boundary within a single quantum. What Exhibit C finds is both: the transaction cluster IS the consistency boundary, and the extraction readiness assessment tells you which clusters can become independent quanta. The difference is granularity — Nygard works at the deployment level, I work at the data consistency level. They inform each other.

### Q23: "Sam Newman's 'Building Microservices' says start with a modular monolith. Your technique starts with the database. Isn't that bottom-up when it should be top-down?"
Newman is right that the modular monolith is a good intermediate state. Exhibit C tells you how to get there. The transaction clusters are the module boundaries — tables that always commit together belong in the same module. Cross-context transactions tell you where the module boundaries need work. It IS bottom-up, and intentionally so — because in a 12-year-old system, the top-down design has drifted so far from reality that you need the bottom-up evidence to calibrate it. Top-down gives you the aspiration. Bottom-up gives you the starting point. You need both.

---

## Danger Level Summary

| Category | Questions | Danger Level |
|----------|-----------|-------------|
| Foundational (tooling, access) | Q1-Q4 | Medium |
| Technical depth | Q5-Q10 | High |
| DDD purity | Q11-Q14 | **Highest** |
| Practical / scaling | Q15-Q17 | Medium |
| Hostile / trap | Q18-Q21 | High |
| Confrontation (Nygard/Newman) | Q22-Q23 | **Highest** |

## Your Strongest Answers
- Q11 ("In a legacy system, those decisions ARE the domain invariants — just implicit" — reframes the whole exhibit)
- Q13 ("Exhibit A gives the command, Exhibit C gives the state change = complete domain event" — shows layered methodology)
- Q18 ("Load-bearing bug" — the most intellectually interesting answer, rehearse it verbatim)
- Q20 ("Same data, different lens" — shuts down the DBA/architect turf war)
- Q23 ("Top-down gives aspiration, bottom-up gives starting point. You need both." — Newman-proof)
