# Incident Clustering — Chain of Thought Process

## What Is This?

A process for discovering wrongly-placed domain boundaries by analyzing where production incidents cluster. While Exhibits A-D map the architecture from artifacts and behavior, Incident Clustering reveals the cost of architectural decisions — where the system's design assumptions cause real failures.

**Input:** Incident database (Jira, ServiceNow, PagerDuty, Opsgenie), post-mortem reports, on-call logs
**Output:** Boundary incident map, incident pattern taxonomy, severity-weighted priority list, cross-reference with previous exhibits

---

## Why Incidents Matter

Incidents are the system telling you where it hurts. Individual incidents are debugging problems. Clusters of incidents at the same boundary are architecture problems. When failures repeatedly occur at the same service integration point, the boundary is wrong — either in location, in integration pattern, or in consistency model.

**Key principle:** Incidents don't cluster randomly. If 23 incidents in 12 months involve the same two services, that's a structural signal. The boundary between those services is either in the wrong place, using the wrong integration pattern, or enforcing the wrong consistency model.

---

## Phase 1: Collect and Normalize Incident Data

**Goal:** Get all production incidents from the last 12 months in a analyzable format.

**Process:**
1. Export from incident management system (Jira filter, ServiceNow query, PagerDuty API)
2. For each incident, extract: date, severity (SEV1-SEV3), title, affected services, root cause (if documented), resolution, time to resolve
3. Filter to production-impacting incidents only (exclude dev/staging, exclude planned maintenance)
4. Normalize severity levels if different teams use different scales

**Thought process:**
- **12 months is the sweet spot.** Less than 6 months may miss seasonal patterns. More than 24 months includes incidents from deprecated architectures. 12 months captures the current system's failure profile
- **Severity matters for prioritization.** A boundary with 5 SEV1 incidents is more urgent than one with 20 SEV3 incidents. Weight accordingly
- **Post-mortem quality varies.** Some incidents have detailed root cause analysis. Others just say "restarted the service." The quality of your analysis depends on the quality of the incident documentation. If post-mortems are sparse, supplement with on-call interviews
- **Undocumented incidents exist.** Teams sometimes fix issues without filing incidents. If a specific failure pattern is well-known ("oh yeah, that happens every Monday"), it's an incident even if it's not in the database. Interview on-call engineers for the "known but unfiled" incidents

**Output:** Normalized incident list — date, severity, services involved, root cause category, resolution

---

## Phase 2: Tag Incidents with Boundary Information

**Goal:** For each incident, identify which service boundary (or internal service) was involved.

**Process:**
1. Read each incident's description and root cause
2. Tag with: service(s) involved, boundary type (cross-boundary or internal)
3. For cross-boundary incidents, record the specific boundary: `Service A ↔ Service B`
4. For internal incidents, record the single service

**Tagging heuristics:**
- **Timeout/connection errors** between services → cross-boundary at the network level
- **Data inconsistency** between two services → cross-boundary at the data level
- **Race condition** involving two services' writes → cross-boundary at the consistency level
- **Null pointer / data validation** within one service → internal (usually)
- **Deployment failure** → could be either — check if the deployment broke a contract between services

**Thought process:**
- **Many incidents involve more than 2 services.** A cascading failure might touch 5 services. Tag the PRIMARY boundary where the failure originated, not every service affected by the cascade. The origin point is the architectural signal
- **"Root cause: unknown"** is common in legacy systems. If the root cause isn't documented, look at the resolution: "restarted Service A" tells you Service A was involved. "Manually synchronized data between Service A and Service B" tells you the boundary
- **Some incidents are genuinely internal** — a memory leak, a bad deployment, a data migration error. These don't indicate boundary problems. Separate them clearly
- **Cascade attribution is the hardest tagging problem.** When a Carrier Integration timeout causes a Shipment Service error that causes a customer-facing failure — the incident is tagged to whatever the customer saw. Back-trace the cascade: the PRIMARY boundary is where the first failure originated, not where the customer felt it. This requires reading the timeline in post-mortems, not just the title and resolution

**Output:** Tagged incident list with boundary annotations

---

## Phase 3: Cluster by Boundary

**Goal:** Group incidents by the boundary they involve and rank by frequency and severity.

**Process:**
1. Group tagged incidents by boundary (`Service A ↔ Service B`)
2. Count incidents per boundary
3. Count by severity per boundary
4. Calculate weighted score: SEV1 × 10 + SEV2 × 3 + SEV3 × 1
5. Sort by weighted score descending

**Thought process:**
- **Top 3 boundaries by weighted score** = your extraction priorities. These are where the architecture costs you the most
- **Boundaries with SEV1 but low total count** = critical but intermittent. Usually a specific failure mode that's catastrophic when it triggers (e.g., race condition)
- **Boundaries with high count but no SEV1** = chronic but manageable. Usually degraded performance or retry storms that self-resolve
- **Compare to Exhibit C's extraction readiness.** Blocked services should correlate with high-incident boundaries. If a service is "blocked" in Exhibit C but has no incidents, the coupling is real but hasn't bitten yet — it will
- **The 77% signal.** If the vast majority of incidents are cross-boundary, the system's boundaries are the primary reliability risk. This is the strongest possible argument for investing in domain redesign over code-level fixes

**Output:** Boundary incident map — boundary, total incidents, severity breakdown, weighted score, rank

---

## Phase 4: Decompose Top Clusters into Incident Patterns

**Goal:** For each top-3 boundary cluster, categorize the specific failure patterns.

**Process:**
1. For each top boundary, read all incident descriptions and root causes
2. Group into failure patterns: race conditions, timeouts, stale reads, data inconsistency, missing compensation, contract violations
3. Map each pattern to an architectural root cause (not a code bug)

**Common incident patterns and their architectural root causes:**

| Pattern | Architectural Root Cause |
|---------|-------------------------|
| **Race condition** (double write, lost update) | Two services write to same aggregate — boundary violation (Exhibit B) |
| **Timeout** (sync call blocks) | Synchronous coupling in critical path — should be async (Exhibit D) |
| **Stale read** (read replica lag) | Read coupling without consistency guarantee — needs event or CQRS |
| **Orphaned state** (cancelled but not rolled back) | No compensating transaction — needs saga (Exhibit C) |
| **Contract violation** (schema mismatch) | API contract drift — no versioning or contract testing (Exhibit A) |
| **Cascading failure** (one service down → many fail) | Tight synchronous coupling — needs circuit breaker + async fallback |
| **Data inconsistency** (two services disagree) | Shared data without single owner — needs ownership decision (Exhibit B) |

**Thought process:**
- **Each pattern maps to a previous exhibit's finding.** Race conditions → Exhibit B's two-writer violation. Timeouts → Exhibit D's sync chain. This cross-reference is the payoff of doing all exhibits — the incidents have root causes you've already diagnosed
- **The same root cause can produce multiple patterns.** The `inventory_reserved` two-writer violation causes race conditions AND orphaned reservations AND stale reads. One architectural fix (saga + single owner) addresses all three failure patterns
- **Code fixes vs architecture fixes.** If a timeout is fixed by increasing the timeout value, it'll recur. If it's fixed by making the call async, the entire pattern disappears. Incident patterns that recur despite code fixes are architecture problems

**Output:** Pattern decomposition per boundary — pattern, count, architectural root cause, fix category (code vs architecture)

---

## Phase 5: Map to Extraction Priority

**Goal:** Use incident data to prioritize which boundaries to fix and in what order.

**Priority formula:** Same as Exhibit C but now weighted by incident pain:
- **Priority = Incident Count × Severity Weight × Coupling Depth**
  - Incident count: from Phase 3
  - Severity weight: SEV1=10, SEV2=3, SEV3=1
  - Coupling depth: number of exhibits (A-D) that confirmed this coupling

**Extraction recommendations by priority:**
1. **P1: Fix the integration pattern.** Boundaries with SEV1 incidents AND confirmed coupling from 3+ exhibits → change the integration pattern (sync → saga, shared write → single owner). Don't just split the service — fix HOW they communicate
2. **P2: Merge or properly separate.** Boundaries with high incident count AND confirmed dead boundary → either merge into one service or invest in a proper ACL
3. **P3: Decouple read dependencies.** Boundaries with SEV3 incidents from stale reads → add event-driven updates or read replicas with explicit consistency guarantees
4. **P4: Monitor and accept.** Boundaries with low incident count and low coupling depth → the boundary may be fine; the incidents may be operational, not architectural

**Output:** Prioritized extraction roadmap — boundary, priority, recommended action, estimated reduction in incident count

---

## Phase 6: Cross-Reference with Exhibits A-D

**Goal:** Complete the five-exhibit convergence — every finding now has structural evidence AND cost evidence.

**Cross-reference:**

| Finding (Exhibits A-D) | Incident Evidence (Exhibit E) | Confidence |
|------------------------|-------------------------------|------------|
| Two-writer violation (Exhibit B) | 7 race conditions | **Proven — fix immediately** |
| Sync chain blocks extraction (Exhibit C) | 6 timeouts | **Proven — async needed** |
| Missing compensating transaction (Exhibit C) | 5 orphaned reservations | **Proven — saga needed** |
| Dead boundary (Exhibits A-D) | 17 incidents at Shipment↔Carrier | **Proven — merge or ACL** |
| Clean boundary (Exhibits A-D) | 0 incidents at Consignee | **Confirmed — leave as-is** |

**The convergence argument:** After 5 exhibits, each finding is supported by multiple independent evidence sources. A coupling that appears in API contracts, database access, transaction logs, production logs, AND incident data is not debatable. The question shifts from "is this a problem?" to "how do we fix it?"

**Output:** Five-exhibit convergence table with confidence levels and recommended actions

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Collect incidents | 80% — API export from incident system | Normalize severity scales |
| 2. Tag with boundary | 40% — keyword matching on service names | Read descriptions, determine primary boundary |
| 3. Cluster by boundary | 100% — group + count + sort | — |
| 4. Decompose patterns | 30% — categorize by keywords | Read root causes, map to architectural issues |
| 5. Map to priority | 70% — formula-based scoring | Validate priority against business context |
| 6. Cross-reference | 40% — name matching | Synthesize 5 evidence sources |

**The biggest human judgment requirement is Phase 2** — tagging incidents with boundary information. Incident descriptions are written for ops teams, not architects. Translating "Order placement failed for customer X" into "Shipment ↔ Inventory boundary failure" requires domain understanding.

---

## Technique Limitations

- **Incident quality determines analysis quality.** If post-mortems are shallow ("restarted service, fixed"), the root cause analysis is limited. Invest in post-mortem culture before running this technique
- **Survivorship bias.** You only see incidents that were reported. Failures that self-resolve, that teams fix without filing, or that are accepted as "normal" don't appear. Interview on-call engineers for the unreported incidents
- **Attribution ambiguity.** A cascading failure may touch 5 services. Deciding the PRIMARY boundary requires judgment. Different analysts may attribute the same incident differently
- **Severity calibration.** Different teams use severity scales differently. One team's SEV2 is another team's SEV1. Normalize before clustering
- **Small sample size.** 83 incidents in 12 months is ~7 per month. For smaller systems with fewer incidents, you may not have enough data to find patterns. In that case, extend the window to 24 months or supplement with near-miss data (alerts that didn't become incidents)
- **Incidents lag architecture.** A boundary that was fixed 6 months ago may still show incidents from before the fix. Filter by date range when a known fix was deployed
