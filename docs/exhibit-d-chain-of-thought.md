# Log Mining (Production Forensics) — Chain of Thought Process

## What Is This?

A process for recovering implicit domain events, actual service interaction flows, and behavioral patterns from production logs. While Exhibits A-C analyze static artifacts (contracts, schemas, transactions), Log Mining analyzes runtime behavior — what the system actually does when processing real requests.

**Input:** Production logs (structured or unstructured), centralized logging (ELK, Splunk, Datadog Logs, CloudWatch), or raw log files from service hosts
**Output:** Recovered event flow, event frequency map, event storming validation report, timing analysis, silent participant detection

---

## Why Logs Matter

Production logs are fossilized domain events. Every `logger.info("Order {} transitioned to CONFIRMED", orderId)` is a domain event that nobody wired up as a formal event. It has a timestamp, a service context, a domain entity reference, and a state description. It's the event the system publishes to nobody — preserved in plain text.

In a legacy system:
- **Contracts** (Exhibit A) tell you what teams agreed to show each other
- **Database** (Exhibit B) tells you what they store
- **Transactions** (Exhibit C) tell you what they commit together
- **Logs** tell you what actually happens at runtime — sequence, timing, participants, frequency, error paths

Logs are the only artifact that captures behavior, not just structure. They're the system narrating itself in real time.

---

## Phase 1: Identify Log Sources and Format

**Goal:** Know what log data is available and how to parse it.

**Process:**
1. Inventory log sources: which services log, where logs are stored, what format
2. Identify log format: structured (JSON), semi-structured (key=value), or unstructured (free text)
3. Check for correlation IDs: trace ID, request ID, order ID — anything that links log lines across services
4. Determine time window: how far back do logs go? (Often 7-90 days in centralized logging)

**Thought process:**
- **Structured logs (JSON)** are easiest: parse fields directly. Most modern services use structured logging
- **Semi-structured** (e.g., `2024-11-14T09:14:02Z | order-service | Order ORD-2024-881742 created`) can be parsed with regex
- **Unstructured** (free-text log messages) require NLP-style pattern extraction. Harder but still possible — look for entity IDs, status keywords, service names
- **Correlation ID is critical.** Without a shared ID across services, you can't trace a single entity's journey. If no correlation ID exists, use the domain entity ID (order ID, shipment ID) as the correlation key
- **Legacy systems often lack centralized logging.** You may need to grep across individual service hosts. That's fine — the technique works with `grep` on raw files. It's slower but the signal is the same

**Output:** Log source inventory — service, log location, format, retention period, correlation ID availability

---

## Phase 2: Trace Single Entity Flow

**Goal:** Reconstruct the complete lifecycle of one domain entity across all services.

**Process:**
1. Pick one entity ID (e.g., an order ID that completed the full lifecycle)
2. Grep for that ID across ALL service logs
3. Sort results chronologically
4. Annotate each line: service, timestamp, action/event, related entities

**Command pattern:**
```bash
grep -h "ORD-2024-881742" \
    /var/log/shipment-service/*.log \
    /var/log/carrier-service/*.log \
    /var/log/invoicing-service/*.log \
    /var/log/inventory-service/*.log \
    /var/log/tracking-notifications/*.log \
  | sort -t'|' -k1
```

**Timestamp normalization caveat:** In a 12-year-old platform, log formats from different teams rarely agree on timestamp format, timezone, or precision. You'll need to normalize timestamps across services before sorting. The automation layer handles this normalization. For manual analysis, convert everything to UTC ISO 8601 first.

For centralized logging (ELK/Splunk):
```
order_id:"ORD-2024-881742" | sort timestamp asc | table timestamp, service, message
```

**Thought process:**
- **Pick a "happy path" entity first** — one that completed the full lifecycle. This gives you the baseline flow
- **Then pick an "error path" entity** — one that was cancelled, refunded, or failed delivery. This reveals exception flows that event storming typically misses
- **Note the services that appear.** If a service appears in the logs but wasn't in Exhibit A's contract inventory → it's a hidden participant. If a service from Exhibit A doesn't appear in the logs → it may not be involved in this particular flow
- **Note what's NOT logged.** If a state transition happens (confirmed_at timestamp is set in the database) but no log line records it → the service doesn't log that transition. That's a gap — a domain event that neither logs nor events capture

**Output:** Annotated event flow for 1-3 entities (happy path, error path, edge case)

---

## Phase 3: Extract Fossilized Events

**Goal:** Build a vocabulary of implicit domain events from log patterns.

**Process:**
1. Grep for state transition keywords across all logs: "created", "confirmed", "shipped", "delivered", "cancelled", "failed", "reserved", "released", "generated", "sent"
2. Parse the entity type + action: "Order CREATED", "Shipment DELIVERED", "Invoice GENERATED"
3. Count frequency over 7 days
4. Rank by frequency — most common = core domain events, rare = edge cases and error flows

**Pattern extraction:**
```bash
# Find all state transition log patterns
grep -oE '(Order|Shipment|Invoice|Payment|Inventory|Customer|Refund)\s+[A-Z]+' \
    /var/log/*-service/*.log \
  | sort | uniq -c | sort -rn
```

**Thought process:**
- **High-frequency events (10,000+/day)** = core domain lifecycle. These are the events you must publish when decomposing
- **Medium-frequency (100-1,000/day)** = secondary flows. Important but not critical path
- **Low-frequency (<100/day)** = edge cases, error handling, admin operations. Often the most architecturally interesting — these are the flows nobody remembers
- **Compare to Exhibit C's timestamp findings:** Each lifecycle timestamp (`confirmed_at`, `shipped_at`) should have a corresponding log event. If the timestamp exists but no log event → the transition is silent. If the log event exists but no timestamp → the transition isn't persisted
- **Event names from logs become the event catalog.** The fossilized events ARE the event model for your future event-driven architecture. Don't invent event names — use what the system already calls them

**Output:** Frequency-ranked event catalog — event name, daily count, originating service, related entities

---

## Phase 4: Analyze Timing and Dependencies

**Goal:** Discover synchronous vs asynchronous boundaries from log timestamps.

**Process:**
1. For traced entity flows, calculate time delta between consecutive events
2. Classify: <100ms = synchronous call, 100ms-5s = slow synchronous or fast async, >5s = asynchronous/queued
3. Identify synchronous chains: sequences of events with <100ms gaps = tightly coupled call chain
4. Identify async boundaries: large time gaps between events = queue/poll/event-driven boundary

**Thought process:**
- **Synchronous chains are the extraction blockers.** If Order CREATED → Inventory RESERVED → Order CONFIRMED → Invoice GENERATED all happen within 2 seconds with <100ms gaps, they're all synchronous calls. Extracting any service in that chain breaks the chain
- **The first large time gap is the natural async boundary.** If there's an 87-second gap between Invoice GENERATED and Shipment CREATED, the carrier integration is already decoupled at runtime. This is the easiest extraction point
- **Compare to Exhibit C:** The synchronous chain in the logs should match the transaction clusters from Exhibit C. If `{orders, inventory_reserved}` is one transaction AND the logs show <100ms between Order CREATED and Inventory RESERVED → confirmed synchronous coupling from two independent sources
- **Timing anomalies:** If a usually-fast synchronous call occasionally takes 5+ seconds, that's a performance issue — the coupling is creating latency spikes. Flag for the team

**Output:** Timing analysis — synchronous chains, async boundaries, latency hotspots

---

## Phase 5: Validate Event Storming Output

**Goal:** Compare the actual production flow to the documented event storming model.

**Process:**
1. Get the event storming output (sticky notes, Miro board, documentation)
2. Map each documented event to a fossilized log event
3. Flag discrepancies:
   - **Missing events:** Documented in ES but no log evidence → the event was aspirational, never implemented
   - **Extra events:** In logs but not in ES → the system does things nobody documented
   - **Wrong sequence:** ES says A → B → C, logs say A → C → B → different developer assumptions
   - **Wrong participants:** ES says Service X handles it, logs show Service Y handles it
   - **Missing participants:** Services that appear in logs but weren't in the ES session

**Thought process:**
- **The sequence difference is the most dangerous.** If the team's mental model says "payment before inventory" but production does "inventory before payment," any new feature built on the wrong mental model will have bugs. This is invisible technical debt — it's not in the code, it's in the team's understanding
- **Extra events are usually good news.** The system does MORE than the team documented. The logs reveal the complete picture. These extra events become part of the corrected domain model
- **Missing events are action items.** If event storming said `PaymentCaptured` should happen but the logs show no payment event during order creation — either the team hasn't built it yet, or the business process works differently than assumed
- **ES validation is the highest-value output of log mining.** This is what makes architects go "oh no" — the realization that the documented model and the production model diverge

**Triage priority for discrepancies:**
- **Wrong sequence** = highest priority. Mental model errors cause bugs in new features. Fix the model immediately
- **Missing participants** = high priority. A service nobody knew about is a hidden dependency that blocks extraction
- **Extra events** = medium priority. Good news — document them and add to the event catalog
- **Missing events** = low priority unless they're in the critical path. Either the feature wasn't built or the business works differently than assumed

**Output:** Event storming validation report — documented events vs actual events, with specific discrepancies prioritized by type

---

## Phase 6: Cross-Reference with Exhibits A-C

**Goal:** Complete the triangulation across all four exhibits.

**Cross-reference patterns:**

| Previous finding | Log evidence to look for |
|-----------------|-------------------------|
| Exhibit A: God entity | Does the god service orchestrate multiple service calls synchronously in the logs? |
| Exhibit A: Missing events | Are there fossilized log events that should be formal events? |
| Exhibit B: Shared tables | Do the logs show services reading from shared tables before their transactions? |
| Exhibit B: Two-writer violation | Do the logs show both services writing in close temporal proximity? |
| Exhibit C: Cross-context transaction | Does the synchronous log chain match the transaction cluster? |
| Exhibit C: Extraction readiness | Do the async boundaries in logs confirm which services are already decoupled? |

**The four-exhibit convergence:**
After Exhibit D, you have four independent evidence sources for each architectural finding. A coupling that appears in all four — API contracts, database access, transaction clusters, AND runtime logs — is as close to proven as you can get without reading the code.

**Output:** Four-exhibit convergence report with confidence levels

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Log source inventory | 60% — list services, check formats | Access negotiations, coverage gaps |
| 2. Single entity trace | 90% — grep + sort | Pick representative entities |
| 3. Fossilized event extraction | 80% — regex pattern matching | Is "Order updated" an event or noise? |
| 4. Timing analysis | 90% — timestamp arithmetic | Is 200ms sync or slow async? |
| 5. ES validation | 30% — name matching | Interpret sequence and participant differences |
| 6. Cross-reference | 40% — name matching across exhibits | Synthesize 4 evidence sources into conclusions |

**Scripts handle Phases 1-4. Agent skills handle Phases 5-6. Humans validate the event storming comparison.**

---

## Technique Limitations

- **Log retention.** Most centralized logging retains 7-90 days. If you need historical patterns, you may not have enough data. For frequency analysis, 7 days is usually sufficient
- **Log quality varies wildly.** Some services log every state transition. Others log only errors. The coverage gap IS a finding — a service that doesn't log domain events is a monitoring blind spot
- **Structured vs unstructured.** Structured logs (JSON) are trivially parseable. Free-text logs require regex pattern extraction, which is fragile and may miss variations. Invest in normalizing logs before running the analysis
- **Correlation across services.** Without a shared trace/request ID, you rely on entity IDs (order ID, shipment ID) to correlate. This works for the primary entity but may miss secondary entities involved in the same flow
- **Log lines ≠ events.** A log line is a developer's debug output. It may not capture domain intent — just "something happened." The human judgment step is deciding which log patterns are domain events and which are operational noise
- **Sampling bias.** Tracing one entity gives you one flow. The system may have many flows. Trace at least 10 entities covering happy path, error path, and edge cases to get representative coverage. For frequency analysis, use the full log dataset
- **Performance logs vs domain logs.** Filter out health checks, metrics, and infrastructure logs before analysis. They add noise without domain signal
- **Log vocabulary ≠ domain vocabulary.** Legacy systems often use internal technical language in log messages, not ubiquitous language. "Processing entity state update" is not "OrderConfirmed." The domain vocabulary has to be mapped to the log vocabulary — and that mapping requires either code access or developer interviews. This is the one step in log mining that can't be automated and can't be skipped

## Additional Signals

### Retry patterns as boundary signals
If you see a service log the same operation twice with a short gap — `Inventory RESERVED` at `09:14:03.000` and again at `09:14:03.847` — that's a retry. Retries in a synchronous chain are the loudest signal that the boundary should be async. The service was designed with the assumption that the downstream call could fail. That defensive coding is evidence of acknowledged coupling fragility. Only the logs show this — contracts, database, and transactions all miss it.

### Log gaps as invisible participant evidence
If an entity appears in Service A at `09:14:02` and next in Service C at `09:14:04` but no service logs anything at `09:14:03` — the gap itself is evidence. Either a service isn't logging, or there's a service in the flow that you don't have logs for. This connects to the "black box services" from Exhibit A's setup — their presence appears as unexplained gaps in the flows from services you CAN see
