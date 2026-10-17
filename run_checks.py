"""Run every data quality rule against the Olist CSV files and write a JSON report."""

import json
import logging
import sys
from pathlib import Path

from checks.engine import build_report
from checks.loader import load_tables
from checks.rules import build_rules

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
REPORT_PATH = ROOT / "data" / "exports" / "dq_report.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_checks")


def main() -> int:
    try:
        tables = load_tables(RAW_DIR)
    except FileNotFoundError:
        logger.exception("Could not load the source data")
        return 1

    report = build_report(tables, build_rules())
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    logger.info(
        "Quality score %.3f%% | rules: %d total, %d passed, %d failed | %.1fs",
        summary["quality_score_pct"], summary["rules_total"], summary["rules_passed"],
        summary["rules_failed"], report["duration_seconds"],
    )
    for rule in report["rules"]:
        if rule["status"] == "fail":
            logger.warning(
                "[%s] %s: %d of %d rows failed",
                rule["severity"], rule["rule_id"], rule["rows_failed"], rule["rows_checked"],
            )
    logger.info("Report written to %s", REPORT_PATH.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
