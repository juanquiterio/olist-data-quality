"""Static-data API for the Olist data quality report."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "data" / "exports" / "dq_report.json"
SEVERITIES = ["critical", "high", "medium", "low"]
STATUSES = ["pass", "fail", "skipped"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("api")

app = FastAPI(title="Olist Data Quality API", version="1.0.0")

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def load_report() -> dict:
    """Read the report from disk so a new run shows up without a restart."""
    if not REPORT_PATH.exists():
        raise HTTPException(status_code=503, detail="Report not found. Run run_checks.py first.")
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("Could not parse %s", REPORT_PATH.name)
        raise HTTPException(status_code=503, detail="Report file is not valid JSON")


@app.get("/health")
def health() -> dict:
    """Liveness check with report status."""
    report = load_report()
    return {
        "status": "ok",
        "rules_total": report["summary"]["rules_total"],
        "quality_score_pct": report["summary"]["quality_score_pct"],
        "generated_at": report["generated_at"],
    }


@app.get("/meta")
def meta() -> dict:
    """Values for building filters."""
    report = load_report()
    rules = report["rules"]
    return {
        "dimensions": sorted({r["dimension"] for r in rules}),
        "tables": sorted({r["table"] for r in rules}),
        "severities": SEVERITIES,
        "statuses": STATUSES,
    }


@app.get("/summary")
def summary() -> dict:
    """Overall score and breakdowns by dimension, table and severity."""
    report = load_report()
    return {
        "generated_at": report["generated_at"],
        "duration_seconds": report["duration_seconds"],
        "tables": report["tables"],
        "summary": report["summary"],
    }


@app.get("/rules")
def rules(
    dimension: Optional[str] = None,
    table: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
) -> list:
    """All rule results, failed first, optionally filtered."""
    if severity is not None and severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Unknown severity. Valid: {SEVERITIES}")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status. Valid: {STATUSES}")
    result = load_report()["rules"]
    if dimension:
        result = [r for r in result if r["dimension"] == dimension]
    if table:
        result = [r for r in result if r["table"] == table]
    if severity:
        result = [r for r in result if r["severity"] == severity]
    if status:
        result = [r for r in result if r["status"] == status]
    return result


@app.get("/rules/{rule_id}")
def rule_detail(rule_id: str) -> dict:
    """One rule with its failing-row sample."""
    for rule in load_report()["rules"]:
        if rule["rule_id"] == rule_id:
            return rule
    raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
