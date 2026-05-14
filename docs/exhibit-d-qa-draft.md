# Exhibit D: Log Mining (Production Forensics) — Q&A (Final)

## Strategy

Exhibit D is your most relatable exhibit — every engineer has grep'd production logs. The "fossilized domain events" framing is original and memorable. Your strongest defense: you're not introducing a new tool, you're teaching people to read what's already there with a DDD lens.

---

## Foundational Challenges

### Q1: "We have centralized logging (ELK/Splunk/Datadog). We already analyze logs. What's different?"
You analyze logs for debugging and alerting — "why did this request fail?" I'm analyzing logs for architecture — "what does this system actually do, and does it match what we think it does?" Same data, different question. Your ELK dashboard tells you a request took 800ms. My analysis tells you that 800ms is 4 synchronous service calls that prove the bounded context boundary is fictional. The DDD lens transforms ops data into architectural decisions.

### Q2: "Our legacy system writes unstructured logs. Free text, no correlation IDs, different formats per service."
That's the common case and it's still workable. Use the domain entity ID (order ID, shipment ID) as your correlation key — it's in every log line because developers put it there for debugging. For timestamp normalization, convert everything to UTC before sorting. For pattern extraction, build regexes against the most common log patterns. It's messier than structured logs but the signal is there. The automation layer handles normalization; the technique works manually with grep.

### Q3: "We only have 7 days of log retention. That's not enough for historical analysis."
7 days is enough for frequency analysis and flow tracing. The patterns are stable — the same order flow runs thousands of times per day. What you can't get from 7 days is trend analysis (is the flow changing over time?) or rare event archaeology (annual batch jobs, year-end processing). For those, you need either longer retention or scheduled exports. But for discovering your event model and validating event storming, 7 days covers it.

### Q4: "Grep across multiple servers? That's not scalable."
Correct — grep is the teaching tool, not the production tool. In practice, use your centralized logging. The Splunk/ELK query is one line: `order_id:"ORD-2024-881742" | sort timestamp asc`. If you don't have centralized logging, that's finding #1 — you can't trace a request across your system. The absence of centralized logging in a platform processing millions of transactions is itself an architectural gap worth flagging.

---

## Technical Depth

### Q5: "How do you distinguish domain events from operational noise in the logs?"
Frequency and domain vocabulary. A log line that says "Order confirmed, status=CONFIRMED" with an entity ID and a state transition — that's a domain event. A log line that says "HTTP 200 OK response sent" — that's operational noise. The frequency filter helps: domain events happen at business volume (thousands/day for core operations). Infrastructure logs happen at request volume (millions/day). Filter by entity ID patterns first, then by state transition keywords.

### Q6: "Log messages use internal technical language, not domain language. How do you map them?"
That's the hardest manual step. "Processing entity state update for ref=ORD-2024-881742" is not "OrderConfirmed." You need to map the log vocabulary to the domain vocabulary. Two approaches: (1) Read the logging code — find the `logger.info()` call and read what triggers it. (2) Ask the developer — "what does 'entity state update' mean?" Either way, this step requires code access or human knowledge. It can't be automated and can't be skipped.

### Q7: "Retries in the logs — how do you distinguish retries from legitimate repeated operations?"
Check the entity ID and timestamp. If the same entity ID appears with the same operation within milliseconds, it's a retry. If the same entity ID appears with the same operation minutes or hours apart, it's a legitimate re-processing (maybe the order was edited). The timing gap is the signal: <1 second = retry. >1 minute = business operation. Between = investigate.

### Q8: "What about async message processing? If Service A publishes to Kafka and Service B consumes, the logs won't show a direct correlation."
They'll show a time gap. Service A logs "Message published for ORD-123" at `09:14:04`. Service B logs "Processing ORD-123" at `09:15:31`. The 87-second gap IS the async boundary evidence. You don't need to see the Kafka topic — the timing tells you the communication is asynchronous. And the entity ID (ORD-123) correlates the two sides even without a shared trace ID.

### Q9: "Your timing analysis assumes network latency is negligible. In a geo-distributed system, 200ms might be network, not processing."
Fair point. In a single-datacenter deployment (common for legacy monoliths), <100ms gaps are reliably synchronous. In geo-distributed systems, you need to account for network latency — check your cross-region ping times and subtract. The timing analysis is a heuristic, not a proof. Cross-reference with Exhibit C's transaction data: if two events are in the same database transaction, they're synchronous regardless of timing.

---

## DDD Purity

### Q10: "Log lines aren't domain events. They have no schema, no versioning, no consumer contract."
Correct — they're not formal events. They're fossilized evidence that events should exist. The log line `"Order ORD-123 confirmed, status=CONFIRMED"` tells you: (1) the event type is `OrderConfirmed`, (2) the payload includes `orderId` and `status`, (3) the originating service is Shipment. That's enough to design the formal event. The logs give you the event catalog. The formalization (schema, versioning, contracts) is the next step after discovery.

### Q11: "Event storming discovers domain events through expert conversations. You're bypassing the experts."
I'm not bypassing them — I'm giving them better raw material. Walk into the event storming with the fossilized event catalog: "Here are the events your system actually emits. Here's the sequence. Here's the frequency. Here's where the flow differs from what you documented last time." The conversation that follows is richer, faster, and grounded in evidence. The experts still decide what the events SHOULD be — the logs show them what the events currently ARE.

### Q12: "Evans' domain events should capture domain intent, not just state changes. A log showing status=CONFIRMED doesn't capture WHY it was confirmed."
True. The log captures the "what" — `OrderConfirmed`. The "why" — business rules, user actions, automated triggers — comes from the command that triggered the state change. If the logs also capture the API call or user action (which they often do: "Confirmed by user U-1234" or "Auto-confirmed: payment verified"), you get both. If not, the "what" is still valuable. You need Exhibit A (the API contract showing the confirm endpoint) + Exhibit D (the log showing the state change) = the complete domain event with command and outcome.

### Q13: "The frequency map just shows me what happens most often. DDD isn't about frequency — it's about domain significance."
Frequency correlates with domain significance in production systems. The most frequent events are the core business operations — `OrderCreated`, `ShipmentDelivered`. The rare events are edge cases and error handling — `RefundProcessed`, `ShipmentFailed`. Both are domain-significant, but frequency tells you which are on the critical path. A `ShipmentFailed` event that happens 89 times per day is domain-significant AND architecturally significant — it's an error flow the team needs to handle explicitly. Frequency doesn't define significance, but it ranks urgency.

---

## Practical / Scaling

### Q14: "We process millions of orders. Tracing them all is impractical."
Don't trace them all. Trace 10 representative entities: 3 happy path (different product types or customer segments), 3 error path (cancellation, refund, delivery failure), 3 edge cases (partial shipment, split order, international). 10 traces gives you the flow variations. For frequency analysis, use the full log dataset with aggregation queries — your centralized logging handles this natively.

### Q15: "Our services log at different verbosity levels. Some log every state change, others only log errors."
The coverage gap IS a finding. A service that only logs errors is a monitoring blind spot — you can't trace the domain flow through it. Document which services have full domain logging and which have gaps. The gaps tell you where you need to improve logging before you can complete the flow analysis. In the meantime, use Exhibit C's transaction data to fill the timing gaps.

### Q16: "How do I convince my team to invest time in log mining when we have other priorities?"
Run one trace. Pick the most important order flow — the one that generates revenue. Trace one order across all services. Print the timeline. Show it to the team alongside the event storming output. The visual difference between "what we think happens" and "what actually happens" is usually enough. I've never seen a team look at that comparison and say "we're fine."

---

## Hostile / Trap

### Q17: "This is just distributed tracing (Jaeger, Zipkin). You're reinventing observability."
Distributed tracing shows you request flow for performance debugging — latency, errors, span hierarchy. I'm analyzing the same data for domain modeling — what state transitions happen, in what sequence, triggered by which services. Tracing tells you "the request took 800ms." Log mining tells you "the request caused 5 domain state changes across 4 services, and the third one contradicts what the team documented." Same infrastructure, different question. Tracing is for SRE. This is for architects.

### Q18: "You showed the event storming was wrong. But event storming is a workshop technique — it's meant to be iterative. You just showed it needs updating, not that it failed."
That's exactly right. Event storming didn't fail — it produced a model at a point in time. But the model wasn't updated when the implementation diverged. Log mining shows you WHERE it diverged so you can update it. I'm not attacking event storming. I'm providing the ground truth that makes the next event storming session productive instead of speculative.

### Q19: "What about privacy regulations? GDPR, CCPA — can you even analyze production logs that contain PII?"
Yes, with appropriate controls. Most log analysis doesn't require PII — you need entity IDs, timestamps, service names, and state transitions. If your logs contain PII (email addresses, names, IP addresses), redact before analysis. Many centralized logging systems support field-level redaction. The technique works on redacted logs — you're tracing domain events, not customer data.

### Q20: "Your example shows a clean trace. In production, I'd get thousands of log lines for one order — heartbeats, retries, debug noise, exception stack traces. How do you find the signal?"
Filter aggressively. Start with: (1) only log lines containing the entity ID, (2) only log levels INFO and above (drop DEBUG, TRACE), (3) only lines matching state transition keywords (created, confirmed, shipped, delivered, failed, cancelled). This typically reduces thousands of lines to 10-20 domain events. The noise is real, but domain events have a distinct pattern: entity ID + state keyword + timestamp. Operational logs rarely have all three.

---

## Confrontation

### Q21: "Brandolini would say you're doing 'software archaeology' which he explicitly warns against — spending time digging through code instead of talking to people."
Brandolini warns against spending months reading code in isolation. I agree. Log mining takes hours, not months. And I'm not replacing the conversation — I'm providing evidence FOR the conversation. Show up to the event storming with the production flow diagram. The conversation is better when people can see what the system actually does instead of debating from memory. Brandolini's own method produces better results when you start from evidence rather than blank sticky notes.

### Q22: "Martin Fowler says 'any fool can write code that a computer can understand; good programmers write code that humans can understand.' Your logs were written for debugging, not for domain modeling."
Fowler is right about intent. But in a 12-year-old system, the developers who wrote those log lines encoded domain knowledge without realizing it. `logger.info("Order {} confirmed", orderId)` IS domain knowledge — it's the developer's understanding of what this state transition means. That understanding may be imperfect. But 84,000 orders per day being "confirmed" through this code path means the business depends on this developer's encoding of the domain. We're reading it as architecture because it IS architecture — just not designed as such.

---

## Danger Level Summary

| Category | Questions | Danger Level |
|----------|-----------|-------------|
| Foundational (tooling, retention) | Q1-Q4 | Medium |
| Technical depth | Q5-Q9 | High |
| DDD purity | Q10-Q13 | **Highest** |
| Practical / scaling | Q14-Q16 | Medium |
| Hostile / trap | Q17-Q20 | High |
| Confrontation (Brandolini/Fowler) | Q21-Q22 | **Highest** |

## Your Strongest Answers
- Q1 ("Same data, different question" — reframes ops vs architecture)
- Q11 ("Giving experts better raw material, not bypassing them" — ES-friendly)
- Q17 ("Tracing is for SRE. This is for architects." — sharp distinction)
- Q18 ("I'm not attacking event storming. I'm providing ground truth." — disarms hostility)
- Q22 ("Developers encoded domain knowledge without realizing it" — the fossil metaphor at its strongest)
