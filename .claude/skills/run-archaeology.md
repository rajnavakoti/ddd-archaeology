---
name: run-archaeology
description: "Run the full Forensic DDD pipeline — all 8 exhibits against a target system's artifacts. Orchestrates CLI tools and produces combined output for interpretation."
model: sonnet
argument-hint: "<contracts-dir> [--db-access-log path] [--db-schema path] [--db-service-users path] [--transactions path] [--logs path] [--log-frequency path] [--incidents path] [--data-lineage path] [--error-codes path] [--git-co-changes path]"
---

# Run Full Forensic DDD Archaeology

You are an architecture analyst orchestrating the full Forensic DDD pipeline. Run all available exhibits against the provided artifacts and produce a combined output directory.

## Process

### Step 1: Check what artifacts are available

Not every system will have all 8 data sources. Check which input files exist from $ARGUMENTS and determine which exhibits can run.

**Minimum required:** A contracts directory (for Exhibit A). Everything else is optional and adds depth.

### Step 2: Run exhibits in order

Run each available exhibit using the CLI tools. Each exhibit's output feeds into the `output/` directory.

```bash
# Exhibit A: Contract Archaeology (REQUIRED)
python -m ddd_archaeology collect <contracts-dir> -o output/inventory.json
python -m ddd_archaeology extract-vocab output/inventory.json -o output/vocabulary.json
python -m ddd_archaeology discover-entities output/inventory.json -o output/entities.json
python -m ddd_archaeology compare output/entities.json -o output/comparison.json
python -m ddd_archaeology analyze-coupling output/entities.json -o output/coupling.json --html output/heatmap.html

# Exhibit B: Schema Archaeology (if DB artifacts provided)
python -m ddd_archaeology schema-archaeology <access_log> <service_users> --schema-sql <schema.sql> -o output/schema_archaeology.json

# Exhibit C: Transaction Boundaries (if transaction data provided)
python -m ddd_archaeology transaction-boundaries <transactions> -o output/transaction_boundaries.json

# Exhibit D: Log Mining (if log traces provided)
python -m ddd_archaeology log-mining <logs> --frequency <log_frequency> -o output/log_mining.json

# Exhibit E: Incident Clustering (if incident data provided)
python -m ddd_archaeology incident-clustering <incidents> -o output/incident_clustering.json

# Exhibit F: Data Lineage (if lineage data provided)
python -m ddd_archaeology data-lineage <data_lineage> -o output/data_lineage.json

# Exhibit G: Error Codes (if error data provided)
python -m ddd_archaeology error-codes <error_codes> -o output/error_codes.json

# Exhibit H: Change Velocity (if git data provided)
python -m ddd_archaeology change-velocity <git_co_changes> -o output/change_velocity.json
```

### Step 3: Report what ran and what didn't

After running all available exhibits, produce a summary:
- Which exhibits ran successfully
- Which exhibits were skipped (missing input data)
- File paths for all outputs
- Total artifacts analyzed (contracts, tables, transactions, incidents, etc.)

### Step 4: Suggest next steps

If exhibits were skipped due to missing data, explain what data is needed and how to collect it. Point to the chain-of-thought docs for each missing exhibit.

## Output

All outputs go to `output/` directory:
- JSON files for each exhibit's structured data
- `output/heatmap.html` for the coupling visualization
- Print a summary table of what ran

## After Running

Tell the user: "Run `/interpret-findings` to get the full forensic DDD report — the reconciliation between the remembered domain and the encoded domain."

## Rules
- Follow `.claude/rules/ddd-archaeology.md` for all reasoning
- Don't interpret the results — that's `/interpret-findings`'s job
- If a CLI tool fails, report the error and continue with the next exhibit
- Always run Exhibit A first — it's the foundation
