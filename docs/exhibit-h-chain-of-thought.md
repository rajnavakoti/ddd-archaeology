# Change Velocity Clustering — Chain of Thought Process

## What Is This?

A process for discovering actual code-level coupling by analyzing which files co-change in git commits. While previous exhibits analyze runtime artifacts (APIs, databases, logs, incidents), Change Velocity Clustering analyzes development artifacts — the commit history that records every coupling decision developers have made.

**Input:** Git log from the last 6-12 months (monorepo or multi-repo with cross-repo PRs)
**Output:** Co-change frequency matrix, coupling clusters, well-encapsulated file list, extraction readiness override

---

## Why Git History Matters

Git records something no other artifact does: the development coupling. Two files that change in the same commit are coupled — someone needed to modify both to complete one logical change. Over thousands of commits, the co-change frequency reveals structural dependencies that persist regardless of architecture diagrams.

Key insight: **runtime coupling and development coupling are different things.** Exhibit C may show clean transaction boundaries (ready to extract), but if git shows 72% co-change between two services, extraction will force coordinated changes across teams. The runtime boundary is clean; the development workflow isn't. Git is the tiebreaker for extraction readiness.

---

## Phase 1: Extract Commit Data

**Goal:** Get file co-occurrence data from git history.

**Process:**
1. Extract commits from the last 6 months: `git log --since="6 months ago" --name-only --pretty=format:"%H"`
2. For each commit, record the set of files that changed
3. Filter: exclude merge commits, exclude files that aren't source code (configs, docs, tests — unless you want to analyze test coupling separately)
4. For multi-repo setups: cross-reference PRs that span repositories (GitHub/GitLab API)

**Git commands:**
```bash
# Extract commit → file mapping
git log --since="6 months ago" --pretty=format:"COMMIT:%H" --name-only \
  | grep -v '^$'

# Simplified: list all co-changing file pairs
git log --since="6 months ago" --name-only --pretty=format:"---" \
  | awk '/^---$/{if(NR>1) for(i in files) for(j in files)
    if(i<j) print files[i]" + "files[j]; delete files; next}
    {files[NR]=$0}' \
  | sort | uniq -c | sort -rn | head -30
```

**Thought process:**
- **6 months** is the sweet spot. Less than 3 months may miss patterns. More than 12 months includes code that's been refactored — the coupling may no longer exist
- **Exclude large commits.** Commits that touch 50+ files are usually refactoring, formatting, or dependency updates — not domain coupling signals. Filter commits to <20 files for cleaner signals
- **Exclude generated files.** Auto-generated code, lock files, build artifacts add noise
- **Monorepo vs multi-repo:** In a monorepo, the technique works directly. In multi-repo, co-change happens across separate repos — you need to correlate PRs that were opened/merged in the same time window for the same feature. This is harder but the signal is the same
- **Developer behavior affects the data.** Some developers make small, focused commits (better signal). Others batch everything into one big commit (noisier). Normalize by looking at patterns across many developers, not just one

**Output:** Commit-to-file mapping, filtered and cleaned

---

## Phase 2: Calculate Co-Change Frequency

**Goal:** For every pair of files, calculate how often they change together.

**Process:**
1. For each commit, generate all file pairs (combinations of 2)
2. Count how many times each pair appears
3. For each file, count total commits it appears in
4. Calculate co-change percentage: `co_changes(A,B) / min(total_changes(A), total_changes(B)) * 100`
5. Sort by co-change percentage, descending

**Thought process:**
- **Normalize by the less-frequently-changed file.** If File A changes 100 times and File B changes 10 times, and they co-change 8 times, the co-change percentage should be 80% (relative to B), not 8% (relative to A). B almost always changes with A — that's the signal
- **Set a minimum threshold.** File pairs that co-changed only 2-3 times in 6 months are noise. Require at least 5 co-changes for a pair to be considered
- **Group by service/module.** Intra-service co-change is expected and healthy. Cross-service co-change is the signal you're looking for
- **The diagonal is always 100%.** Every file co-changes with itself. Ignore it

**Output:** Co-change frequency matrix — file pair, co-change count, co-change percentage, same-service/cross-service flag

---

## Phase 3: Cluster by Service Boundary

**Goal:** Identify cross-service co-change patterns — the coupling that contradicts the architecture.

**Process:**
1. Tag each file with its owning service (from directory structure, package name, or repo name)
2. Filter co-change pairs to cross-service only
3. Aggregate: for each service pair, what's the average co-change frequency of their files?
4. Rank service pairs by coupling strength

**Classification:**

| Co-Change % | Interpretation |
|-------------|---------------|
| >70% | **Effectively one unit** — boundary is fictional at the development level |
| 50-70% | **Tightly coupled** — extraction would force coordinated changes |
| 30-50% | **Moderately coupled** — extraction possible with stable contract |
| <30% | **Loosely coupled** — extraction feasible |
| <10% | **Well-separated** — clean boundary |

**Thought process:**
- **>70% cross-service co-change = merge candidate.** The teams already work as if these are one service. Making it official reduces coordination overhead
- **50-70% = the danger zone.** Extracting these services will feel clean architecturally but painful operationally. Every feature requires cross-team coordination. Invest in stable contracts/interfaces before extracting
- **Files that change alone >80% of the time** are your baseline for well-encapsulated code. Use these as reference points
- **Cross-reference with team ownership.** If two files co-change 72% of the time but are owned by the SAME team — it's internal coupling, annoying but manageable. If they're owned by DIFFERENT teams — it's cross-team coordination tax, which is the most expensive kind of coupling

**Output:** Cross-service co-change clusters with coupling strength classification

---

## Phase 4: Identify Well-Encapsulated Files

**Goal:** Find files that change in isolation — evidence of clean boundaries.

**Process:**
1. For each file, count: total commits, commits where it changes alone (no other files in same commit)
2. Calculate solo-change percentage
3. Files with >80% solo-change rate are well-encapsulated
4. Group well-encapsulated files by service — services where most files change alone have clean boundaries

**Thought process:**
- **Well-encapsulated files are your positive reference.** They prove the codebase CAN have clean boundaries. When advocating for decoupling, point to these: "this is what good separation looks like, and it already exists in your system"
- **A service where ALL files change alone is truly independent.** Consignee Service with 89% solo changes confirms the independence that Exhibits A-G already showed
- **A file that used to change alone but recently started co-changing** is a regression signal — new coupling was introduced. Track over time
- **Test files that co-change with source files are expected** (TDD). Don't count these as coupling signals. Filter test files separately

**Output:** Well-encapsulated file list, per-service encapsulation score

---

## Phase 5: Override Extraction Readiness

**Goal:** Use git evidence to confirm or override Exhibit C's extraction readiness assessment.

**Process:**
1. For each service from Exhibit C's extraction readiness report, check git co-change data
2. If Exhibit C says "ready" but git shows >50% cross-service co-change → **override to "not ready"**
3. If Exhibit C says "blocked" and git shows <30% cross-service co-change → the coupling is runtime-only, not development — **extraction may still be feasible** with async patterns
4. Produce final extraction readiness combining transaction evidence (C) and development evidence (H)

**Thought process:**
- **Git overrides "ready to extract" when development coupling is high.** Clean transactions don't help if every PR requires changes in both services. The development workflow IS the extraction bottleneck
- **Git confirms "blocked" when development coupling is also high.** Both runtime and development coupling point the same direction — strongest possible signal
- **Git contradicts "blocked" when development coupling is low.** The transaction coupling may be a specific code path (Exhibit C), but developers rarely need to change both services together. This is a candidate for saga conversion without major development disruption
- **The extraction ORDER comes from git.** Extract the least-coupled services first. The most-coupled services are extracted last because they need the most interface stabilization

**Output:** Final extraction readiness — per service, with evidence from both Exhibit C and Exhibit H

---

## Phase 6: Cross-Reference with All Exhibits

**Goal:** Complete the eight-exhibit convergence.

**Cross-reference patterns:**

| Previous finding | Git evidence to look for |
|-----------------|-------------------------|
| Exhibit A: Dead boundary (API) | Do files from both services co-change >50%? |
| Exhibit B: Shared tables | Do files accessing the shared table co-change? |
| Exhibit C: Cross-context transaction | Do files in the transaction co-change? |
| Exhibit D: Synchronous chain | Do files in the sync chain co-change? |
| Exhibit E: Incident cluster at boundary | Do files at the incident-prone boundary co-change? |
| Exhibit F: Missing propagation events | Do source and copy code co-change (forced manual sync)? |
| Exhibit G: Misplaced business rule | Does the misplaced rule's file co-change with the context it should belong to? |

**The eight-exhibit convergence:** A finding confirmed by all 8 exhibits is as close to proven as architecture analysis gets without rewriting the system. At that point, the question is no longer "is this a problem?" but "when do we fix it?"

**Output:** Eight-exhibit convergence table — the definitive architecture assessment

---

## Automation vs Human Judgment Summary

| Phase | Automatable | Needs Human/AI |
|-------|-------------|----------------|
| 1. Extract commit data | 100% — git log parsing | Filter criteria (exclude patterns) |
| 2. Co-change frequency | 100% — counting + math | — |
| 3. Cluster by boundary | 80% — directory-based tagging | Service ownership mapping |
| 4. Well-encapsulated files | 100% — counting | — |
| 5. Override extraction readiness | 60% — threshold rules | Is the override justified? |
| 6. Cross-reference | 40% — name matching | Synthesize 8 evidence sources |

---

## Technique Limitations

- **Monorepo vs multi-repo.** In a monorepo, git history captures all co-changes. In multi-repo, cross-service co-changes happen across separate repos and require PR correlation. The signal exists but extraction is harder
- **Commit granularity varies.** Small focused commits give better signal than large batched commits. If one developer commits 50 files per commit, their co-change data is noisy. Normalize across many developers
- **Refactoring noise.** Large-scale refactoring (renaming, moving files, formatting) creates false co-change signals. Filter commits by size — exclude commits touching >20 files
- **Time decay.** Code that co-changed 12 months ago may have since been decoupled. Use a 6-month window for current coupling. Use 12 months for trend analysis
- **Test coupling is expected.** Test files that co-change with source files are testing discipline (TDD), not architectural coupling. Filter test files unless you want to analyze test coverage patterns
- **This technique only works with source code access.** If you're analyzing a system without repo access (vendor-built), this exhibit is blocked. Fall back to the other 7 exhibits
