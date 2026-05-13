# DDD Archaeology

Toolkit for reverse-engineering DDD bounded contexts from API contracts.

## Structure
- `src/ddd_archaeology/` — Python package with CLI phases
- `examples/delivery/` — Synthetic delivery platform contracts (6 OpenAPI, 2 AsyncAPI, 1 GraphQL)
- `docs/` — Chain-of-thought process, story scripts (some gitignored)
- `.claude/skills/` — Agent skills for Phases 7-8 (boundary inference, gap analysis)
- `.claude/rules/` — DDD reasoning conventions for agent skills

## CLI Pipeline
```bash
python -m ddd_archaeology collect examples/delivery/ -o output/inventory.json
python -m ddd_archaeology extract-vocab output/inventory.json -o output/vocabulary.json
python -m ddd_archaeology discover-entities output/inventory.json -o output/entities.json
python -m ddd_archaeology compare output/entities.json -o output/comparison.json
python -m ddd_archaeology analyze-coupling output/entities.json -o output/coupling.json --html output/heatmap.html
```

Then invoke agent skills:
- `/infer-boundaries` — Phase 7, reads output/*.json
- `/gap-analysis` — Phase 8, compares inferred map to documented architecture

## Conventions
- All output to `output/` directory (gitignored)
- JSON for machine-readable data, Markdown for human reports
- Neo-brutalist style for HTML visualizations
- Tests in `tests/`, run with `pytest`
