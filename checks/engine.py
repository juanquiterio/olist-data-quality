"""Rule model and the engine that runs rules and builds the report."""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

SAMPLE_SIZE = 5
SEVERITIES = ["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    table: str
    dimension: str
    severity: str
    description: str
    check: Callable[[dict], tuple]


def run_rule(rule: Rule, tables: dict) -> dict:
    """Run one rule and return its result record."""
    started = time.time()
    checked, failed = rule.check(tables)
    rows_failed = len(failed)
    pass_rate = round(100 * (checked - rows_failed) / checked, 3) if checked else None
    if checked == 0:
        status = "skipped"
    else:
        status = "pass" if rows_failed == 0 else "fail"
    return {
        "rule_id": rule.rule_id,
        "table": rule.table,
        "dimension": rule.dimension,
        "severity": rule.severity,
        "description": rule.description,
        "rows_checked": int(checked),
        "rows_failed": int(rows_failed),
        "pass_rate_pct": pass_rate,
        "status": status,
        "sample": failed.head(SAMPLE_SIZE).astype(str).to_dict("records"),
        "duration_seconds": round(time.time() - started, 3),
    }


def _group_summary(results: list, field: str) -> dict:
    summary: dict = {}
    for name in sorted({r[field] for r in results}):
        group = [r for r in results if r[field] == name and r["pass_rate_pct"] is not None]
        summary[name] = {
            "rules": len(group),
            "rules_failed": sum(1 for r in group if r["status"] == "fail"),
            "score_pct": (
                round(sum(r["pass_rate_pct"] for r in group) / len(group), 3) if group else None
            ),
        }
    return summary


def summarize(results: list) -> dict:
    """Overall score plus breakdowns by dimension, table and severity."""
    scored = [r for r in results if r["pass_rate_pct"] is not None]
    failed = [r for r in results if r["status"] == "fail"]
    return {
        "quality_score_pct": (
            round(sum(r["pass_rate_pct"] for r in scored) / len(scored), 3) if scored else None
        ),
        "rules_total": len(results),
        "rules_passed": sum(1 for r in results if r["status"] == "pass"),
        "rules_failed": len(failed),
        "rules_skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed_by_severity": {s: sum(1 for r in failed if r["severity"] == s) for s in SEVERITIES},
        "by_dimension": _group_summary(results, "dimension"),
        "by_table": _group_summary(results, "table"),
    }


def build_report(tables: dict, rules: list) -> dict:
    """Run every rule and assemble the full report."""
    started = time.time()
    results = [run_rule(rule, tables) for rule in rules]
    results.sort(
        key=lambda r: (
            r["status"] != "fail",
            SEVERITIES.index(r["severity"]),
            r["pass_rate_pct"] if r["pass_rate_pct"] is not None else 100,
        )
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 2),
        "tables": {name: int(len(df)) for name, df in tables.items()},
        "summary": summarize(results),
        "rules": results,
    }
