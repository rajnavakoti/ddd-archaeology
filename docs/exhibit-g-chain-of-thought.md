# Error Code Reverse-Engineering — Chain of Thought Process

## What Is This?

A process for recovering undocumented business rules, domain invariants, and misplaced logic by analyzing production error codes. Error codes are fossilized business rules — each one represents a validation that a developer encoded, often without documenting the business reason. Decoding them recovers domain logic that exists nowhere else.

**Input:** Error/exception tables from production databases, application logs with error codes, support ticket error references
**Output:** Error code → business rule mapping, invariant catalog, misplaced rule identification, escape hatch audit

---

## Why Error Codes Matter

In legacy systems, business rules migrate from documentation into code and never come back. A developer implements `if (priceVariance > 0.02) throw ORD-E003` and the 2% tolerance becomes a production-enforced invariant that nobody documents. Over 12 years, hundreds of these rules accumulate in error handling code.

Error codes are the most concentrated encoding of domain invariants because:
- **They represent boundaries** — what the system considers invalid
- **They're tested by production** — millions of real transactions validate them
- **They encode domain knowledge** — the developer understood something about the domain when writing them
- **They survive team turnover** — the developer left but the validation persists
- **They reveal hidden contexts** — a business rule in the wrong service reveals a missing bounded context

---

## Phase 1: Extract Error Code Inventory

**Goal:** Get all error codes from production with frequency and context.

**Process:**
1. Query error/exception tables for the last 12 months
2. Rank by frequency — most common errors first
3. For each error code, collect: code, message, frequency, affected entities, first/last seen, originating service

**SQL pattern:**
```sql
SELECT
    error_code,
    error_message,
    COUNT(*) AS occurrences,
    COUNT(DISTINCT order_id) AS affected_orders,
    MIN(created_at) AS first_seen,
    MAX(created_at) AS last_seen
FROM order_errors
WHERE created_at > NOW() - INTERVAL '12 months'
GROUP BY error_code, error_message
ORDER BY occurrences DESC;
```

**Thought process:**
- **High-frequency errors (>1,000/year)** are core domain invariants — they fire because the system enforces important business rules
- **Medium-frequency (100-1,000/year)** are secondary rules — important but not on the critical path
- **Low-frequency (<100/year)** are edge case rules — often the most interesting for domain modeling because they encode rare but important business scenarios
- **Errors with gaps in the timeline** (first_seen long ago, but only recent occurrences) may indicate reactivated rules or seasonal patterns
- **Error codes that only appear in certain date ranges** may correspond to feature deployments — cross-reference with git history
- **The first_seen date is the rule's birth certificate.** The frequency trend is the rule's health check. A rule that's been firing since 2013 at stable frequency is load-bearing — treat it like infrastructure. A rule that suddenly increased frequency in 2024 means something changed in the business or the code — find what triggered the change. Old rules that still fire are stable invariants. New rules are hypotheses still being tested

**Output:** Error code inventory — code, message, frequency, affected entities, date range

---

## Phase 2: Decode Business Rules

**Goal:** For each error code, document the actual business rule it encodes.

**Process:**
1. Read the error message — often cryptic but hints at the rule
2. Read the code that throws the error — find the condition that triggers it
3. Document: what invariant is being enforced? What entity does it protect? What's the threshold/condition?
4. If code access isn't available, interview the ops team — they know the workarounds, which means they understand the rule

**Decoding patterns:**

| Error Pattern | Likely Business Rule Type |
|--------------|--------------------------|
| "Exceeded" / "Threshold" / "Limit" | Quantitative invariant (amount, count, percentage) |
| "Validation failed" / "Invalid" | Format or data quality rule |
| "Expired" / "Window" / "Timeout" | Temporal invariant (SLA, policy period) |
| "Conflict" / "Already exists" | Uniqueness or state transition rule |
| "Override" / "Bypass" / "Manual" | Escape hatch — rules being skipped |
| "Not found" / "Missing" | Referential integrity or dependency |

**Thought process:**
- **The message is often misleading.** "Insufficient allocation" could mean 10 different things. The code is the truth — read the condition
- **Thresholds are gold.** `if (variance > 0.02)` tells you a specific business tolerance that's probably not documented anywhere else. Record the exact number
- **Temporal rules encode SLAs and policies.** "Fulfilment window expired" means someone defined a pick SLA. What's the window? Who decided it? Is it configurable or hardcoded?
- **Per-category rules reveal domain complexity.** "Return window differs by category" means the return policy context has more complexity than anyone described in event storming
- **Escape hatches are always the most dangerous.** Any `if (override) skip_validation()` path needs an audit. What rules does it skip? Who can trigger it? Is it logged?

**When code access isn't available — the ops interview pattern:**
Don't ask "what does ORD-E003 mean?" They'll say "it's a price mismatch thing." Ask instead: "when you get ORD-E003, what do you do?" The answer tells you the rule from the exception side. "We usually just reprocess the order" → the threshold is too strict. "We call the customer to confirm the new price" → the threshold represents a customer communication boundary. "We escalate to the pricing team" → the threshold is a business authority boundary. The workaround describes the rule.

**Output:** Error code → business rule mapping table

---

## Phase 3: Map Rules to Aggregates and Contexts

**Goal:** Determine which aggregate should own each business rule and whether it's in the right context.

**Process:**
1. For each decoded rule, identify the entity it validates (Order, Shipment, Inventory, etc.)
2. Map to the aggregate that should own it (the aggregate whose consistency it protects)
3. Check: is the rule currently implemented in the service that owns that aggregate?
4. Flag misplacements: rules in the wrong service = missing bounded context signal

**Thought process:**
- **The aggregate that the rule protects should own the rule.** ORD-E003 (price variance) protects Order confirmation → belongs in the Order aggregate
- **Rules that reference multiple aggregates** reveal cross-context invariants. ORD-E031 (split shipment) references warehouses, carriers, AND orders → either a saga invariant or a missing orchestration context
- **Rules in the wrong service are the strongest signal.** DEL-E011 (return window per category) is in the Carrier Integration service but the rule is about return POLICY, not delivery logistics. This reveals a missing Returns/Policy context
- **Error code prefixes often show which team IMPLEMENTED the rule, not which context OWNS it.** `DEL-E011` is prefixed `DEL-` because the delivery team built it. The prefix shows where the rule lives. The content shows where it belongs

**Output:** Rule → aggregate mapping with misplacement flags

---

## Phase 4: Audit Escape Hatches

**Goal:** For any override/bypass error codes, document what rules are being skipped.

**Process:**
1. Find all error codes related to overrides, bypasses, or manual interventions
2. Trace the code path: when the override is triggered, which validations are skipped?
3. Document: who can trigger the override? Is it logged? Is there approval workflow?
4. Categorize: legitimate domain exception vs workaround for a too-strict rule vs undocumented bypass

**Thought process:**
- **Overrides that are logged with reasons** are well-governed — these are legitimate domain exceptions that should become explicit domain events (`OrderOverrideApplied { reason, approver }`)
- **Overrides that are not logged** are dangerous — nobody knows how often or why they're used until you look at the data
- **High-frequency overrides** (>100/year) suggest the underlying validation is wrong or too strict. If ops overrides a rule 891 times, maybe the rule needs to change
- **Override paths that have grown** (more rules skipped over time) indicate creeping scope — each developer who needed a workaround added their case to the override path
- **The override audit is the highest-value output for risk management.** Every unlogged override is a production risk. Quantifying them converts a vague "we have manual overrides" into a specific "891 unlogged validation bypasses per year"

**Output:** Escape hatch audit — override code, rules skipped, frequency, governance status, risk level

---

## Phase 5: Build Domain Invariant Catalog

**Goal:** Compile all decoded business rules into a structured invariant catalog.

**Process:**
1. Combine all decoded rules from Phase 2
2. Add aggregate ownership from Phase 3
3. Add misplacement flags
4. Add escape hatch status from Phase 4
5. Categorize: validated invariant, unvalidated assumption, overridable policy, missing validation

**Catalog structure per invariant:**
- **Rule ID:** Original error code
- **Business Rule:** Plain language description
- **Aggregate Owner:** Which aggregate should enforce this
- **Current Location:** Which service currently implements it
- **Misplaced:** Yes/No
- **Threshold/Condition:** The specific validation logic
- **Frequency:** How often it fires
- **Overridable:** Yes/No, with governance status
- **Documented Elsewhere:** Yes/No (cross-reference with requirements, wiki, event storming output)

**Output:** Domain invariant catalog — the business rules document that should have existed all along, derived from production error codes

---

## Phase 6: Cross-Reference with Previous Exhibits

**Goal:** Connect error code findings to all previous architectural evidence.

**Cross-reference patterns:**

| Error Code Signal | Previous Exhibit Connection |
|------------------|----------------------------|
| Error fires at service boundary | Exhibit E: does this error cause incidents? If yes, the boundary needs fixing |
| Error references inventory/stock | Exhibit B: is this the two-writer violation surfacing as validation failures? |
| Error fires in transaction context | Exhibit C: does this validation happen inside or outside the aggregate's transaction? |
| Error not in event storming | Exhibit D: was this invariant visible in the log patterns? |
| Error reveals format mismatch | Exhibit F: is this a data lineage divergence surfacing as an error? |

**The 12,847 → 23 ratio:** ORD-E001 fires 12,847 times per year. But Exhibit E found only 23 incidents at the Shipment↔Inventory boundary. That means the error handling catches 12,824 cases successfully — only 23 escape into incidents. The error code is doing its job. The incidents occur when the error handling itself fails (race conditions, timeouts). This ratio tells you the error handling is load-bearing — removing or changing the validation without understanding it would cause 12,847 failures per year to go unhandled.

**Output:** Seven-exhibit convergence table with error code evidence

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Extract inventory | 100% — SQL query | — |
| 2. Decode rules | 30% — pattern matching on messages | Read code, interpret business intent |
| 3. Map to aggregates | 20% — name matching | Which aggregate should own this? |
| 4. Audit escape hatches | 50% — find override paths | Assess risk, governance status |
| 5. Build catalog | 80% — compile from phases 2-4 | Review and validate |
| 6. Cross-reference | 40% — match error codes to incidents | Interpret ratios and connections |

**Phase 2 (decoding) is the most human-intensive and highest-value step.** The error message is the hint. The code is the truth. The business intent is what you're reconstructing.

---

## Technique Limitations

- **Requires access to error/exception data.** If errors are only in application logs (not a structured table), extraction requires log parsing first (use Exhibit D's techniques)
- **Error messages are often misleading or generic.** `"Validation failed"` tells you nothing. You need the code to understand the actual rule. Without code access, interview ops teams about their workarounds
- **Not all business rules have error codes.** Rules enforced through UI validation, API contract validation, or database constraints don't appear in the error table. This technique finds rules enforced in application code
- **Historical error codes may reference deleted code.** An error code from 2016 may enforce a rule in code that was refactored in 2019. The error code persists in the table but the rule may have changed. Cross-reference with current code
- **Override paths may have undocumented side effects.** Auditing what an override skips requires reading the code path, which may have grown over years. Don't assume the override is simple
- **Error frequency ≠ business importance.** A rule that fires once per year (rare tax calculation edge case) may be more business-critical than one that fires 10,000 times (common stock check). Use business impact, not just frequency, for prioritization
