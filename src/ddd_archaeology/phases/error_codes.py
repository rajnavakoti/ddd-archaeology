"""Exhibit G: Error Code Reverse-Engineering — decode fossilized business rules."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ddd_archaeology.output.writer import print_table, write_json


@dataclass
class DecodedRule:
    """A business rule decoded from an error code."""

    code: str
    message: str
    decoded_rule: str
    aggregate: str
    service: str
    occurrences: int
    threshold: str | None = None
    category: str = ""
    first_seen: str = ""
    last_seen: str = ""
    is_misplaced: bool = False
    should_be_in: str = ""
    is_escape_hatch: bool = False
    governance: str = ""
    is_cross_context: bool = False
    contexts_referenced: list[str] = field(default_factory=list)


@dataclass
class ErrorCodeResult:
    """Full output of Exhibit G analysis."""

    total_error_codes: int = 0
    total_occurrences: int = 0
    rules: list[DecodedRule] = field(default_factory=list)
    misplaced_rules: list[DecodedRule] = field(default_factory=list)
    escape_hatches: list[DecodedRule] = field(default_factory=list)
    cross_context_rules: list[DecodedRule] = field(default_factory=list)
    rules_with_thresholds: list[DecodedRule] = field(default_factory=list)
    prefix_ownership: dict[str, str] = field(default_factory=dict)


def run(args: argparse.Namespace) -> int:
    """Analyze error codes for fossilized business rules."""
    errors_path = Path(args.errors)
    if not errors_path.exists():
        print(f"Error: {errors_path} not found")
        return 1

    error_data = json.loads(errors_path.read_text())
    result = analyze_error_codes(error_data)

    print(f"\n  ═══ ERROR CODE REVERSE-ENGINEERING ═══\n")
    print(f"  Total error codes: {result.total_error_codes}")
    print(f"  Total occurrences (12 months): {result.total_occurrences:,}\n")

    # All rules
    print("  ═══ DOMAIN INVARIANT CATALOG ═══\n")
    rows = []
    for r in result.rules:
        flags = []
        if r.is_misplaced:
            flags.append(f"MISPLACED → {r.should_be_in}")
        if r.is_escape_hatch:
            flags.append(f"ESCAPE HATCH ({r.governance})")
        if r.is_cross_context:
            flags.append(f"CROSS-CONTEXT ({', '.join(r.contexts_referenced)})")
        flag_str = " | ".join(flags) if flags else "—"
        threshold = r.threshold or "—"
        rows.append([r.code, r.decoded_rule[:60], str(r.occurrences), r.aggregate, r.service, threshold, flag_str])
    print_table(["Code", "Rule", "Count", "Aggregate", "Service", "Threshold", "Flags"], rows)

    # Prefix analysis
    if result.prefix_ownership:
        print(f"\n  ═══ ERROR CODE PREFIX OWNERSHIP ═══\n")
        for prefix, service in sorted(result.prefix_ownership.items()):
            print(f"    {prefix}-* → {service}")

    # Misplaced rules
    if result.misplaced_rules:
        print(f"\n  ⚠ MISPLACED RULES ({len(result.misplaced_rules)}):")
        for r in result.misplaced_rules:
            print(f"    {r.code}: lives in {r.service}, should be in {r.should_be_in}")

    # Escape hatches
    if result.escape_hatches:
        print(f"\n  🔴 ESCAPE HATCHES ({len(result.escape_hatches)}):")
        for r in result.escape_hatches:
            print(f"    {r.code}: {r.occurrences} bypasses/year, governance: {r.governance}")

    # Thresholds
    if result.rules_with_thresholds:
        print(f"\n  ═══ UNDOCUMENTED THRESHOLDS ═══\n")
        for r in result.rules_with_thresholds:
            print(f"    {r.code}: {r.threshold} — {r.decoded_rule[:60]}")

    write_json(result, args.output)
    print(f"\n  Results written to {args.output}")
    return 0


def analyze_error_codes(error_data: list[dict]) -> ErrorCodeResult:
    """Analyze error codes for business rules."""
    result = ErrorCodeResult()
    result.total_error_codes = len(error_data)

    # Parse and classify
    prefix_services: dict[str, set[str]] = defaultdict(set)

    for entry in error_data:
        rule = DecodedRule(
            code=entry.get("code", ""),
            message=entry.get("message", ""),
            decoded_rule=entry.get("decoded_rule", ""),
            aggregate=entry.get("aggregate", ""),
            service=entry.get("service", ""),
            occurrences=entry.get("occurrences", 0),
            threshold=entry.get("threshold"),
            category=entry.get("category", ""),
            first_seen=entry.get("first_seen", ""),
            last_seen=entry.get("last_seen", ""),
            is_misplaced=entry.get("misplaced", False),
            should_be_in=entry.get("should_be_in", ""),
            is_escape_hatch=entry.get("category") == "escape_hatch",
            governance=entry.get("governance", ""),
            is_cross_context=entry.get("cross_context", False),
            contexts_referenced=entry.get("contexts_referenced", []),
        )

        result.total_occurrences += rule.occurrences
        result.rules.append(rule)

        if rule.is_misplaced:
            result.misplaced_rules.append(rule)
        if rule.is_escape_hatch:
            result.escape_hatches.append(rule)
        if rule.is_cross_context:
            result.cross_context_rules.append(rule)
        if rule.threshold:
            result.rules_with_thresholds.append(rule)

        # Track prefix ownership
        prefix = rule.code.split("-")[0] if "-" in rule.code else rule.code
        prefix_services[prefix].add(rule.service)

    # Determine prefix ownership
    for prefix, services in prefix_services.items():
        if len(services) == 1:
            result.prefix_ownership[prefix] = next(iter(services))
        else:
            result.prefix_ownership[prefix] = f"shared ({', '.join(sorted(services))})"

    # Sort rules by occurrences
    result.rules.sort(key=lambda r: -r.occurrences)

    return result
