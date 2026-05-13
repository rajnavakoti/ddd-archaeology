# Exhibit A: Contract Archaeology — Q&A (Final)

## Strategy: How an Imposter Survives Q&A

Your safety net has three layers:
1. **The IKEA story** — you actually did this. Not in theory. With a real data architect, on real API specs. That's more hands-on than most people in the room.
2. **The limits are honest** — you've already said what the technique can't do. Nobody can trap you if you've pre-declared the blind spots.
3. **The 8 exhibits** — if a question is outside Contract Archaeology's scope, redirect to the exhibit that covers it. "Great question — that's exactly what the log mining exhibit addresses."

---

## Foundational Challenges (They'll question the premise)

### Q1: "You're just reverse-engineering the mess, not the domain. How is this useful?"
Yes, I'm reverse-engineering the mess. That's exactly the point. You can't draw a map to where you're going if you don't know where you are. The contracts are your GPS coordinates — ugly, real, and precise. And they reveal four things domain conversations miss: hidden coupling, vocabulary drift, god entities, and dead boundaries. Event storming tells you the intended architecture. Contract archaeology tells you the implemented architecture. The gap between those two is where your real problems live.

### Q2: "Evans already talks about reverse-engineering from code. What's new here?"
Evans wrote about legacy strategies — bubble contexts, ACLs — before standardized machine-readable contracts existed. What's new isn't the problem, it's the medium. When every service publishes an OpenAPI spec and every event has an AsyncAPI schema, you have a standardized, parseable artifact layer that didn't exist when the DDD book was written. The technique is only possible because of infrastructure maturity in the last decade. Evans gave us the vocabulary to interpret what we find — he just didn't have this particular artifact source.

### Q3: "This is just API governance with extra steps. How is it DDD?"
API governance says "your API should look like X." This says "your API *reveals* your domain model whether you intended it or not." Governance is prescriptive — here's the standard, follow it. Archaeology is diagnostic — here's what your contracts say about your actual boundaries. The DDD part is mapping the findings to strategic design concepts: bounded contexts, context maps, shared kernels. The technique produces DDD artifacts from non-DDD inputs.

### Q4: "Why not just ask the teams? They know their own domains."
They know their *intended* domain. They don't know the implementation drift. In my experience, when you show a team their own coupling heatmap, they're surprised. "We didn't know Order was pulling warehouse names." Teams optimize locally — they don't see the cross-boundary picture. The contracts see it because they're the handshake between services.

### Q5: "Domain modeling is a collaborative exercise. You're removing the humans."
No — I'm removing the first 3 hours of a workshop where everyone argues about what exists today. The archaeology gives you the current state in minutes. Then humans do what they're actually good at: deciding what the *target* state should be. I'm not replacing event storming — I'm giving event storming a head start.

---

## Technical Depth (They'll probe whether you know the details)

### Q6: "What about services that use code-generated specs? Those specs reflect the code, not the design."
Good — that's actually better for archaeology. Code-generated specs are the most honest contracts because they can't lie. A hand-written spec might describe the ideal; a generated spec describes reality. The vocabulary drift, coupling, and god entities are even more visible in generated specs because nobody cleaned them up.

### Q7: "OpenAPI doesn't capture domain invariants — no business rules, no constraints beyond type validation. How do you infer aggregates?"
You're right — contracts don't show invariants. But they show aggregate *boundaries* through path structure: `/orders/{id}/lines` tells you Order is the aggregate root and OrderLine is a child entity. You can't infer "an order must have at least one line" from the spec, but you can infer the ownership relationship. For invariants, you need the error pattern exhibit — error responses tell you what rules were violated. "400: Order must have at least one line item" IS a domain invariant, just surfaced through the API's error contract.

### Q8: "Your coupling heatmap treats all references equally. A `buyerId` foreign key is very different from duplicating an entire Invoice schema."
Absolutely. The heatmap is a first-pass signal — it shows you *where* to look. The comparison matrix (Phase 4) then tells you *how deep* the coupling is. An ID reference is a Customer-Supplier relationship — that's expected and healthy. A duplicated schema is either Shared Kernel (intentional) or accidental coupling. The technique distinguishes them — the heatmap just points you to the right place.

### Q9: "How do you handle API versioning? If a service has v1 and v2 running simultaneously, which do you analyze?"
Both. The delta between v1 and v2 is itself a finding — it shows you how the domain model evolved. Which fields were added, renamed, removed? Which schemas were split or merged? The version history is domain archaeology. In the automation, we flag version co-existence and diff them.

### Q10: "GraphQL schemas are generated from resolvers that aggregate multiple backends. You're analyzing a derivative, not a source of truth."
That's the point. The GraphQL schema is the *consumer's truth* — what the frontend thinks the domain looks like. Comparing it to the backend contracts reveals where the translation happens. If the frontend sees one concept ("Order" with payment and shipment inline) and the backend has four separate services, that gap tells you the BFF is doing implicit aggregation. Whether that's good (ACL) or bad (business logic in the wrong place) is the human judgment call.

### Q11: "AsyncAPI adoption is still low. Most organizations don't have formal event schemas. What then?"
You work with what you have. In practice, I look for the schema registry first. If your org uses Kafka, the schemas in Confluent Schema Registry or AWS Glue Schema Registry are your AsyncAPI equivalent — machine-readable event contracts without the formal spec. Kafka topic names themselves reveal domain boundaries. If none of that exists, the absence is itself a finding: the organization has event-driven patterns with no contract governance. That's log mining territory — you mine the actual event flows from production.

---

## Scaling & Practicality (They'll question if it works in the real world)

### Q12: "This works for your synthetic 6-service example. What about 200 microservices across 30 teams?"
That's exactly where automation matters. Phases 1-6 are scripts — they scale linearly. 200 specs take the same CPU time per spec as 6. The output is bigger — more signals, more noise. That's why Phase 7 needs human or AI judgment to filter. But the point is: reading 200 specs manually is impossible. Running a script against 200 specs takes seconds.

### Q13: "What if only 30% of our services have OpenAPI specs?"
Then you've already found your first finding: 70% of your services have no contract governance. That's a massive blind spot. Start with the 30% — you'll still find coupling, vocabulary drift, and boundary signals. And the missing 70% becomes your backlog: generate specs from code (tools exist), or flag those services for code-level archaeology.

### Q14: "How often should we run this? Once? Quarterly? On every PR?"
Depends on your rate of change. Contract archaeology is cheap — under a minute for 200 specs. You could run it on every PR that modifies a spec file (CI integration). Quarterly is the minimum for a health check. The value compounds: if you baseline today and diff in 3 months, you can see whether vocabulary is converging or diverging, whether coupling is increasing or decreasing. That's a trend, not a snapshot.

### Q15: "Our specs are auto-generated and not maintained. They're garbage. How do I trust the output?"
Garbage-in tells you something: the team doesn't maintain their contracts. That's finding #1. Auto-generated specs that haven't been updated in 14 months while the code has changed 80 times = confirmed drift. You now know the contract can't be trusted, AND you know the team has no contract governance. Both are actionable. For the stale specs, score findings as low-confidence and validate with production logs.

---

## DDD Purity (The Evans/Brandolini/Vernon crowd will test your DDD knowledge)

### Q16: "You're mapping to DDD vocabulary, but your technique doesn't produce bounded contexts — it produces service clusters. Those aren't the same thing."
You're right — and this is worth being precise about. A bounded context is a semantic boundary defined by language, not deployment. What Contract Archaeology produces is *coupling evidence* that suggests where the semantic boundaries are or aren't. The boundary still needs to be *declared* by the team. What I'm providing is the forensic case that helps teams make that declaration with evidence instead of gut feeling. Think of it this way: Evans says the bounded context is where the ubiquitous language is consistent. If I show you that `buyer`, `user`, `account`, `recipient`, and `customer` all refer to the same concept across five services — I haven't *defined* a bounded context, but I've shown you that one *doesn't* currently exist. That's the diagnostic. The prescriptive work is yours.

### Q17: "Where does the ubiquitous language come from in your approach? In DDD, it's co-created with domain experts."
The contracts reveal the *implemented* ubiquitous language — what the teams actually call things in code. That's different from the *intended* ubiquitous language from workshops. The archaeology shows you the gap: "domain experts call it Customer, the code calls it buyer, user, account, recipient." That gap IS the problem to solve. The language should come from domain experts — the archaeology shows you where it hasn't.

### Q18: "Eric Evans talks about continuous knowledge crunching. How is a one-time scan different from continuous modeling?"
Evans' knowledge crunching in Chapter 1 of the Blue Book is about the iterative collaboration between developers and domain experts that evolves the model over time. My technique doesn't replicate that — it measures drift between the planned model and the implemented model. These are complementary: crunching tells you where to go, archaeology tells you where you are. And it's not one-time — run the scan on cadence, in CI. The trend data shows you whether your domain model is converging or diverging. That IS measurement-backed knowledge crunching.

### Q19: "You mention Shared Kernel, Customer-Supplier, ACL — but your technique can't actually distinguish between them. It just shows coupling."
Correct — the pattern matching gives you *evidence toward* a relationship type, not proof of it. A duplicated schema *could* be Shared Kernel or Conformist — you need to ask: is there a shared library? A governance agreement? An ownership conversation? The archaeology raises the question. But here's why that's still valuable: in my experience, most teams can't answer that question because they've never been asked it in this precise form. Showing them "both Order and Billing define Invoice with 80% field overlap — is this intentional Shared Kernel or accidental coupling?" forces a conversation that produces the answer. The technique creates the diagnostic condition for the relationship type to be named.

### Q20: "What about subdomains? Your technique says nothing about Core vs Supporting vs Generic."
Correct that business value classification requires business context. But there are weak signals. A service with only `GET` endpoints, no lifecycle events, and lots of cross-references is almost certainly Generic or Supporting — it's a read-model or utility. A service with a rich event lifecycle, its own vocabulary that other services defer to, and no duplicated schemas pulling from others — that's a Core Domain candidate. You'd never classify based on this alone. But in a Phase 7 conversation with the team, "here's why the contracts suggest this might be Core" is a better starting point than "tell me what's strategic."

---

## Hostile / Trap Questions (They'll try to corner you)

### Q21: "Have you actually done this at scale in production, or is this a thought experiment with synthetic data?"
I did this at IKEA with a data architect. We took existing API spec files across several services and reverse-engineered the domain model — entities, relationships, bounded context candidates — without top-down modeling. It produced a current-state understanding in weeks that would have taken months of workshops. That experience is what this whole talk is built on. The synthetic dataset is a teaching tool — clean enough to follow in a 5-minute segment. The real system was messier and told us more.

### Q22: "Your synthetic dataset is designed to show the signals you want. In a real system, most contracts are boring and well-structured. Where's the signal?"
In a well-structured system, the archaeology confirms it — that's valuable too. "Your vocabulary is consistent, your coupling is low, your boundaries match your org chart" is a finding. It means your investment in API governance is working. But in my experience and from talking to practitioners — most systems are NOT well-structured once you look at field-level detail. The vocabulary drift is almost universal.

### Q23: "Isn't this just what Backstage/Compass/any service catalog already does?"
Service catalogs track ownership and dependencies at the service level. They tell you "Order Service depends on Customer Service." They don't tell you: which specific fields create that coupling, whether the vocabulary is aligned, whether the boundary is real or fictional, or whether the address concept should be shared or separate. Archaeology is field-level forensics. Service catalogs are building-level maps. Both useful, different granularity.

### Q24: "You said the BFF is an 'accidental ACL.' But the team built it deliberately to aggregate backends. How is that accidental?"
The aggregation is deliberate. The anticorruption is accidental. The team built the BFF to give the frontend a clean API. They probably didn't think of it as an ACL in DDD terms — they just translated messy backends into clean frontend types. But that's exactly what an ACL does: it translates one model into another at a boundary. The fact that they built it without DDD vocabulary doesn't make it less of an ACL. The archaeology gives them the vocabulary for what they already did.

### Q25: "If I can get all this from contracts, why do I need the other 7 exhibits? Isn't this enough?"
No. Contract archaeology has declared blind spots: it can't see services without contracts, it can't see runtime behavior, it can't see business rules, it can't see how the code actually processes requests. A service might have a perfect contract but terrible implementation. A contract might be stale. The 8 exhibits are layered: contracts give you the declared architecture, logs give you the actual behavior, database schemas give you the persistence model, git history gives you how it evolved. Each one ground-truths the others. You need at least 3-4 exhibits for a trustworthy picture.

---

## Meta / Methodology Questions

### Q26: "How do you decide the scope? Which services to include in the archaeology?"
Start with one team's domain — their services plus the immediate neighbors they depend on. Don't boil the ocean. In my experience, a scope of 5-15 services is the sweet spot for one pass. You expand outward from there based on findings: if you discover a coupling to a service outside your scope, pull it in for the next pass.

### Q27: "Can this be done without automation? Can I do it with just a whiteboard and the spec files?"
Yes — I literally did it that way at IKEA. Open the specs, compare field names, trace IDs manually. It works for 5-10 services. Beyond that, it's tedious enough that you'll miss things. The automation makes it repeatable and catches patterns a human eye would skim over. But the technique itself is pen-and-paper valid.

### Q28: "What's the output format? How do I share findings with my team?"
The automation outputs: vocabulary consistency report, entity map, coupling heatmap, inferred context map, gap report. All as structured data (JSON) and human-readable reports (Markdown). The coupling heatmap renders as a visual. For a team conversation, the most powerful artifact is the vocabulary comparison table — "here are 6 names for Customer across our services" gets an immediate reaction every time.

### Q29: "How does this relate to your DDC framework / Context Blocks work?"
The talk is about the forensic technique — it works whether you use Context Blocks or a spreadsheet. Context Blocks is where I'm taking this further: the archaeology outputs feed directly into the knowledge base that agents use to answer domain questions. But that's a separate conversation. This exhibit is about the technique.

### Q30: "What tools do you recommend? Is there something I can install today?"
The DDD Archaeology repo has the synthetic dataset and the chain-of-thought process. The automation scripts are coming — they'll be open source. For today, you can manually walk through the process: collect your specs, compare vocabularies, trace coupling. The tooling makes it faster, but the methodology works without it.

---

## Confrontation Questions (Feathers/Brandolini/Vernon direct challenges)

### Q31: "What's the difference between this and Michael Feathers' 'Design Discovery in Existing Systems'?"
Feathers works from the inside out — static code analysis, identifying unnamed abstractions in existing code structure, cohesion and coupling at the class/module level. I work from the outside in — contracts, the declared interface between services, what teams have agreed to show each other. Feathers is powerful for a single codebase. My approach works when you have 30 teams with 30 codebases — you can't read all the code, but you can read the contracts. The two techniques are complementary: Feathers tells you what's inside one service, I tell you how services relate to each other.

### Q32: "Brandolini says Event Storming discovers the domain through conversation — your technique replaces the conversation with analysis. Doesn't that lose the social/political dimension of domain modeling?"
Brandolini is right that the conversation *is* the point of Event Storming — the discoveries happen in the room, not on the sticky notes. I'm not replacing that conversation. I'm changing the question the conversation starts with. If you walk into a room and say "here's what your contracts tell us about your current boundaries" — the conversation that follows is richer, faster, and more grounded than starting from blank sticky notes. The archaeology doesn't remove the social dimension — it gives the social dimension better raw material. And the gap between the documented domain and the implemented domain IS the political conversation: who owns Shipment, Order or Shipping? That question only becomes visible when you show both teams the evidence. Teams are polite in workshops. Contracts are honest.

### Q33: "How do you handle GraphQL schemas that are fully auto-generated from a database schema? The types reflect tables, not domain concepts."
If the GraphQL schema is auto-generated from a database, you've found something important: the organization has no intentional API layer. The database IS the interface. That's itself a significant architectural finding — there are no contracts, just schema exposure. In that case, GraphQL archaeology tells you the database structure, not the domain model. Redirect to the database schema exhibit which is built for exactly this: extracting domain signals from the persistence layer directly.

### Q34: "Your vocabulary drift finding shows 6 names for 'customer.' But maybe each context is correct to use its own term — that's DDD. Why is this a problem?"
Great challenge — and this is where the Address finding and the Customer finding are actually different answers. Address *should* have different shapes per context — the fields are genuinely different because the business need is different (Shipping needs access codes, Billing needs VAT numbers). That's correct DDD. But `buyer`, `customer`, `user`, `recipient`, `account` are all names for the same *person* concept with no field-level justification for different naming — they just use a different word for the same ID, the same email, the same name. The signal is: different fields = intentional bounded context divergence. Different names, same fields = vocabulary drift, not domain differentiation. The difference is whether the divergence is semantic or cosmetic.

### Q35: "What happens when the contract says one thing and the actual behavior is different — like an endpoint that claims to accept an order but actually creates both an order and a shipment in one call?"
That's a perfect description of why Contract Archaeology is Exhibit A, not the only exhibit. The contract declares the interface; the behavior is in the logs. If `POST /orders` claims to create an Order but production logs show `[order-service] Order ORD-123 created` followed immediately by `[delivery-service] Shipment SHP-456 created` in the same trace — the contract lied. That gap between declared interface and actual behavior is exactly what the log mining exhibit surfaces. The 8 exhibits are designed to triangulate: if Exhibit A and the log exhibit contradict each other, the contradiction is the finding.

---

## Danger Level Summary

| Category | Questions | Danger Level |
|----------|-----------|-------------|
| Foundational (premise) | Q1-Q5 | Medium |
| Technical depth | Q6-Q11 | High |
| Scaling & practicality | Q12-Q15 | Medium |
| DDD purity | Q16-Q20 | **Highest** |
| Hostile / trap | Q21-Q25 | High |
| Meta / methodology | Q26-Q30 | Low |
| Confrontation (Feathers/Brandolini) | Q31-Q35 | **Highest** |

## Your Strongest Answers (Lead with These if Nervous)
- Q1 (GPS coordinates — rehearsed, polished)
- Q5 (giving event storming a head start — reframes from threat to complement)
- Q21 (IKEA story — real experience, not theory)
- Q34 (semantic vs cosmetic divergence — shows deep understanding)
- Q32 (workshops are polite, contracts are honest — memorable line)
