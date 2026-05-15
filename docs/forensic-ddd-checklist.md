# The Forensic DDD Checklist

Take this to your own systems. Eight exhibits, each revealing something the others can't.

## Exhibit A: Contract Archaeology
Catalogue all API contracts (OpenAPI, AsyncAPI, GraphQL). Compare vocabulary across services. Find the god entities, the dead boundaries, the vocabulary drift. The contracts are the implementation's confession.

## Exhibit B: Schema Archaeology
Find tables accessed by multiple services. Especially find tables with multiple writers — that's your highest-risk boundary violation. The database tells you what services actually do when nobody's watching.

## Exhibit C: Transaction Boundary Analysis
Identify tables that always commit together — those are your aggregates. Tables that sometimes commit together across services are boundary violations that must be addressed before extraction.

## Exhibit D: Log Mining
Trace one entity end-to-end through production logs. Compare the real flow to the documented flow. Where they differ, production is right. Every log line is a fossilized domain event.

## Exhibit E: Incident Clustering
Categorize 12 months of incidents by service boundary. Where incidents cluster is where boundaries need to move. The architecture is the bug.

## Exhibit F: Data Lineage Tracing
Pick your most-shared entity. Find every copy. Map format differences and update policies. Identify the real source of truth. Each copy with different rules is a bounded context boundary.

## Exhibit G: Error Code Reverse-Engineering
Map every cryptic error code to the business rule it encodes. These are invariants that exist nowhere in documentation. The error code table is the most honest business rules document.

## Exhibit H: Change Velocity Clustering
Find files that change together in git. If they're in different services, those services are coupled regardless of what the architecture diagram says. Git is the tiebreaker.

---

## The Extraction Decision

For each discovered boundary:

| Question | Yes → | No → |
|----------|-------|------|
| Causing production incidents? | **Extract** (priority = incident severity) | Next question ↓ |
| Blocking team delivery velocity? | **Wrap with ACL** (buy time) | Next question ↓ |
| Clean boundary, confirmed by 3+ exhibits? | **Leave alone** | Investigate further |

## The Extraction Sequence

Always in this order:
1. **Strangle reads** — API gateway in front of shared tables
2. **Introduce events** — Replace synchronous co-writes with domain events
3. **Shadow traffic** — Run new path in parallel, compare outputs
4. **Feature-flag cutover** — 1% → 10% → 50% → 100%, rollback if error rates spike

---

## Tools

The [DDD Archaeology toolkit](https://github.com/rajnavakoti/ddd-archaeology) provides automation for Exhibits A through H:

```bash
pip install ddd-archaeology

# Exhibit A: Contract Archaeology
python -m ddd_archaeology collect <contracts-dir>
python -m ddd_archaeology extract-vocab output/inventory.json
python -m ddd_archaeology discover-entities output/inventory.json
python -m ddd_archaeology compare output/entities.json
python -m ddd_archaeology analyze-coupling output/entities.json

# Exhibit B: Schema Archaeology
python -m ddd_archaeology schema-archaeology <access_log.json> <service_users.json>

# Exhibit C: Transaction Boundary Analysis
python -m ddd_archaeology transaction-boundaries <transaction_clusters.json>

# Exhibit D: Log Mining
python -m ddd_archaeology log-mining <trace.jsonl>

# Exhibit E: Incident Clustering
python -m ddd_archaeology incident-clustering <incidents.json>

# Exhibit F: Data Lineage Tracing
python -m ddd_archaeology data-lineage <data_lineage.json>

# Exhibit G: Error Code Reverse-Engineering
python -m ddd_archaeology error-codes <error_codes.json>

# Exhibit H: Change Velocity Clustering
python -m ddd_archaeology change-velocity <co_changes.json>
```

---

*The domain isn't in the documentation. It's in the system. Go read the evidence.*
