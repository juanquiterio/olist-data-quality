"""Tests for the rule builders and the report engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from checks import rules  # noqa: E402
from checks.engine import Rule, run_rule, summarize  # noqa: E402


def test_unique_key_flags_extra_rows():
    df = pd.DataFrame({"id": [1, 2, 2, 3, 3, 3]})
    checked, failed = rules.unique_key("t", ["id"])({"t": df})
    assert checked == 6
    assert len(failed) == 3


def test_foreign_key_flags_orphans_and_ignores_nulls():
    tables = {
        "child": pd.DataFrame({"ref": [1, 2, 9, None]}),
        "parent": pd.DataFrame({"id": [1, 2, 3]}),
    }
    checked, failed = rules.foreign_key("child", "ref", "parent", "id")(tables)
    assert checked == 3
    assert len(failed) == 1
    assert failed.iloc[0]["ref"] == 9


def test_not_null_respects_scope():
    df = pd.DataFrame({"k": [1, 2, 3], "status": ["a", "a", "b"], "v": [1.0, None, None]})
    check = rules.not_null("t", ["v"], ["k"], where=lambda d: d["status"] == "a")
    checked, failed = check({"t": df})
    assert checked == 2
    assert list(failed["k"]) == [2]


def test_has_children_flags_parents_without_children():
    tables = {
        "parent": pd.DataFrame({"id": [1, 2, 3]}),
        "child": pd.DataFrame({"pid": [1, 1, 3]}),
    }
    checked, failed = rules.has_children("parent", "id", "child", "pid")(tables)
    assert checked == 3
    assert list(failed["id"]) == [2]


def test_row_rule_only_checks_rows_in_scope():
    df = pd.DataFrame({"k": [1, 2, 3, 4], "price": [10.0, -1.0, 0.0, 5.0], "on": [True, True, True, False]})
    check = rules.row_rule("t", ["k"], lambda d: d["price"] > 0, where=lambda d: d["on"])
    checked, failed = check({"t": df})
    assert checked == 3
    assert list(failed["k"]) == [2, 3]


def test_payments_match_items_flags_mismatch():
    tables = {
        "order_items": pd.DataFrame({
            "order_id": ["a", "b"], "price": [10.0, 5.0], "freight_value": [2.0, 1.0],
        }),
        "order_payments": pd.DataFrame({
            "order_id": ["a", "b", "c"], "payment_value": [12.0, 7.0, 3.0],
        }),
    }
    checked, failed = rules.payments_match_items()(tables)
    assert checked == 2
    assert list(failed["order_id"]) == ["b"]


def test_run_rule_computes_pass_rate_and_sample():
    rule = Rule("r1", "t", "validity", "high", "demo",
                lambda tables: (4, pd.DataFrame({"k": [7]})))
    result = run_rule(rule, {})
    assert result["pass_rate_pct"] == 75.0
    assert result["status"] == "fail"
    assert result["sample"] == [{"k": "7"}]


def test_run_rule_skips_when_nothing_to_check():
    rule = Rule("r2", "t", "validity", "low", "demo",
                lambda tables: (0, pd.DataFrame({"k": []})))
    result = run_rule(rule, {})
    assert result["status"] == "skipped"
    assert result["pass_rate_pct"] is None


def test_summarize_scores_and_counts():
    results = [
        {"dimension": "uniqueness", "table": "a", "severity": "critical", "status": "pass", "pass_rate_pct": 100.0},
        {"dimension": "validity", "table": "a", "severity": "high", "status": "fail", "pass_rate_pct": 90.0},
    ]
    summary = summarize(results)
    assert summary["quality_score_pct"] == 95.0
    assert summary["rules_passed"] == 1
    assert summary["rules_failed"] == 1
    assert summary["failed_by_severity"]["high"] == 1
    assert summary["by_dimension"]["validity"]["score_pct"] == 90.0


def test_rule_ids_are_unique():
    ids = [r.rule_id for r in rules.build_rules()]
    assert len(ids) == len(set(ids))
