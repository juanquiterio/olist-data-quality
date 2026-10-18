# Olist Data Quality Lab

A rule-based data quality framework for the Olist Brazilian e-commerce dataset. It runs 36 checks in five quality dimensions over eight tables, ranks the failures by severity, and exposes the report through a FastAPI backend and a web dashboard.

<!-- DEMO (uncomment when live)
- Live demo: https://olist-dq-web.onrender.com/
- The demo runs on a free server that sleeps when idle. The first load can take 30-60 seconds.
-->

<!-- SCREENSHOT (uncomment when it exists)
![Data quality dashboard](docs/img/dashboard.png)
-->

<!-- VIDEO (uncomment when it exists)
Video walkthrough: UNLISTED_YOUTUBE_URL
-->

## Contents

1. [Problem](#problem)
2. [Solution](#solution)
3. [Dataset](#dataset)
4. [Rule catalog](#rule-catalog)
5. [How the engine works](#how-the-engine-works)
6. [Findings](#findings)
7. [Architecture](#architecture)
8. [API reference](#api-reference)
9. [Dashboard](#dashboard)
10. [Repository structure](#repository-structure)
11. [Run locally](#run-locally)
12. [Tests](#tests)
13. [Deployment](#deployment)
14. [Technical decisions](#technical-decisions)
15. [Challenges and learnings](#challenges-and-learnings)
16. [Limitations and next steps](#limitations-and-next-steps)
17. [License](#license)

## Problem

E-commerce data usually fails in quiet ways: repeated keys, delivered orders without a delivery date, items pointing to products that do not exist, payments that do not add up to what was sold. A single overall quality percentage hides which of these matter, because a handful of bad rows in a table of 100,000 barely moves an average.

## Solution

The project defines each expectation as a small, named rule with a severity, runs all of them against the raw files, and produces one report that answers three questions: what is broken, how badly, and which records show it.

- **36 rules** in five dimensions: uniqueness, completeness, referential integrity, validity and consistency.
- **Each rule reports** rows checked, rows failed, pass rate, severity, status and a sample of five failing records.
- **A severity-first report.** Failing rules are listed first, ordered by severity, and the overall score is kept as a secondary figure.
- **Served through an API** and a dashboard where every rule expands to show its evidence.

## Dataset

Olist Brazilian E-Commerce Public Dataset (Kaggle). Eight tables are used:

| Table | Rows | Used for |
|---|---|---|
| `customers` | 99,441 | Customer keys |
| `sellers` | 3,095 | Seller keys |
| `products` | 32,951 | Product attributes and category |
| `orders` | 99,441 | Order status and timestamps |
| `order_items` | 112,650 | Items, prices and freight |
| `order_payments` | 103,886 | Payment type, installments and value |
| `order_reviews` | 99,224 | Review keys and score |
| `category_translation` | 71 | Category names in English |
| **Total** | **550,759** | |

The geolocation table (over a million rows) is not loaded, because no rule needs it. Only the columns each rule needs are read.

## Rule catalog

Severity reflects the damage a failure would do downstream: **critical** for broken primary keys and relationships that break joins, **high** for failures that distort business metrics, **medium** for incomplete or inconsistent attributes.

### Uniqueness (8)

| Rule | Table | Severity | Checks that |
|---|---|---|---|
| `uniq_customers_id` | customers | critical | `customer_id` is unique |
| `uniq_orders_id` | orders | critical | `order_id` is unique |
| `uniq_products_id` | products | critical | `product_id` is unique |
| `uniq_sellers_id` | sellers | critical | `seller_id` is unique |
| `uniq_order_items_pk` | order_items | critical | (`order_id`, `order_item_id`) is unique |
| `uniq_order_payments_pk` | order_payments | critical | (`order_id`, `payment_sequential`) is unique |
| `uniq_reviews_id` | order_reviews | high | `review_id` is unique |
| `uniq_translation_category` | category_translation | medium | `product_category_name` is unique |

### Completeness (6)

| Rule | Table | Severity | Checks that |
|---|---|---|---|
| `null_orders_approved_at` | orders | medium | Orders past "created" have an approval timestamp |
| `null_orders_carrier_date` | orders | medium | Shipped or delivered orders have a carrier handoff date |
| `null_orders_customer_date` | orders | high | Delivered orders have a customer delivery date |
| `null_products_category` | products | medium | Products have a category |
| `null_products_content` | products | medium | Products have name length, description length and photo count |
| `null_products_dimensions` | products | medium | Products have weight and dimensions |

### Referential integrity (9)

| Rule | Table | Severity | Checks that |
|---|---|---|---|
| `fk_orders_customer` | orders | critical | Every order has a customer |
| `fk_items_order` | order_items | critical | Every item belongs to an order |
| `fk_items_product` | order_items | high | Every item references a known product |
| `fk_items_seller` | order_items | high | Every item references a known seller |
| `fk_payments_order` | order_payments | critical | Every payment belongs to an order |
| `fk_reviews_order` | order_reviews | high | Every review belongs to an order |
| `fk_products_category` | products | medium | Product categories exist in the translation table |
| `orders_delivered_have_items` | orders | high | Delivered orders have at least one item |
| `orders_have_payments` | orders | high | Every order has at least one payment |

### Validity (7)

| Rule | Table | Severity | Checks that |
|---|---|---|---|
| `valid_order_status` | orders | high | Status is one of delivered, shipped, canceled, unavailable, invoiced, processing, created, approved |
| `valid_item_price` | order_items | high | Price is positive |
| `valid_item_freight` | order_items | medium | Freight value is not negative |
| `valid_payment_value` | order_payments | medium | Payment value is positive |
| `valid_payment_installments` | order_payments | medium | At least one installment |
| `valid_payment_type` | order_payments | medium | Type is credit_card, boleto, voucher or debit_card |
| `valid_review_score` | order_reviews | high | Score is between 1 and 5 |

### Consistency (6)

| Rule | Table | Severity | Checks that |
|---|---|---|---|
| `cons_approved_after_purchase` | orders | medium | Approval is on or after purchase |
| `cons_carrier_after_purchase` | orders | medium | Carrier handoff is on or after purchase |
| `cons_delivery_after_carrier` | orders | medium | Customer delivery is on or after carrier handoff |
| `cons_delivery_after_purchase` | orders | high | Customer delivery is on or after purchase |
| `cons_undelivered_no_delivery_date` | orders | medium | Orders not marked delivered have no customer delivery date |
| `cons_payments_match_items` | order_payments | high | Money paid matches items plus freight per order (tolerance 0.01 BRL) |

Optional fields, such as the review comment title and message, are deliberately not treated as errors: counting them would inflate the failures without saying anything useful.

## How the engine works

Every rule is a `Rule` record (id, table, dimension, severity, description) plus a check function that returns `(rows_checked, failing_rows)`. Six reusable builders cover the catalog:

| Builder | Failing rows are |
|---|---|
| `unique_key` | Rows whose key already appeared earlier in the table |
| `not_null` | Rows in scope where any of the given columns is null |
| `foreign_key` | Non-null child values that do not exist in the parent table |
| `has_children` | Parent rows in scope with no matching row in the child table |
| `row_rule` | Rows in scope for which a validity function returns false |
| `payments_match_items` | Orders where money paid differs from items plus freight |

**Scoped rules.** Rules only check the rows where they make sense. The delivery-date rule, for example, looks only at orders marked as delivered. This keeps the denominator honest and avoids false failures.

**Result fields:**

| Field | Meaning |
|---|---|
| `rows_checked` | Rows in the rule's scope |
| `rows_failed` | Rows that break the rule |
| `pass_rate_pct` | (checked - failed) / checked, 3 decimals |
| `status` | `pass`, `fail`, or `skipped` when there is nothing to check |
| `sample` | Up to 5 failing records, as text |

**Scoring.** The overall quality score is the average pass rate across rules, and the same average is computed per dimension and per table. The report also counts failures by severity.

## Findings

Latest run: **36 rules, 20 pass, 16 fail, no critical failures** (4 high, 12 medium). Overall score: **99.85%**. The run takes a few seconds on a 2-core, 4 GB machine.

| Rule | Severity | Rows failed |
|---|---|---|
| `uniq_reviews_id` | high | 814 of 99,224 |
| `cons_payments_match_items` | high | 378 of 98,665 orders |
| `null_orders_customer_date` | high | 8 of 96,478 |
| `orders_have_payments` | high | 1 of 99,441 |
| `null_products_category` | medium | 610 of 32,951 |
| `null_products_content` | medium | 610 of 32,951 |
| `cons_carrier_after_purchase` | medium | 166 of 97,658 |
| `cons_delivery_after_carrier` | medium | 23 of 96,475 |
| `null_orders_approved_at` | medium | 14 of 98,202 |
| `fk_products_category` | medium | 13 of 32,341 |
| `valid_payment_value` | medium | 9 of 103,886 |
| `cons_undelivered_no_delivery_date` | medium | 6 of 2,963 |
| `valid_payment_type` | medium | 3 of 103,886 |
| `null_products_dimensions` | medium | 2 of 32,951 |
| `null_orders_carrier_date` | medium | 2 of 97,585 |
| `valid_payment_installments` | medium | 2 of 103,886 |

What the evidence shows:

- **Repeated review ids (814).** The key is not unique, so any join on `review_id` can multiply rows.
- **Payments that do not match items plus freight (378 orders).** The gaps are real money, not rounding. Three sampled orders differ by 21.98, 30.64 and 1.92 BRL. The cause was not investigated, so the report only flags them.
- **Delivered orders without a delivery date (8).** They would be dropped from any delivery-time metric.
- **Products without category (610).** The category, name length, description length and photo count rules fail with the same count, which suggests the same products (not verified row by row). Another 13 products have a category that is missing from the translation table (for example `pc_gamer`).
- **Why the score is not enough.** 99.85% sounds clean, yet four high-severity rules fail. Failures are tiny against 100,000-row tables, so an average hides them.

## Architecture

```text
data/raw/*.csv
      |
checks/loader.py     reads only the needed columns, parses dates
      |
checks/rules.py      36 rules built from six reusable builders
checks/engine.py     runs rules, scores, summarizes, sorts
      |
run_checks.py   --->  data/exports/dq_report.json
                              |
                      api/main.py (FastAPI, reads the report from disk)
                              |
                      frontend/index.html (dashboard)
```

The report is precomputed. The API only reads one JSON file, so the hosted service needs neither pandas nor the raw data.

## API reference

Base URL: `http://localhost:8006` locally. CORS allows `GET` only.

| Endpoint | Description |
|---|---|
| `GET /health` | Status, number of rules, quality score and report timestamp. 503 if the report is missing |
| `GET /meta` | Dimensions, tables, severities and statuses for building filters |
| `GET /summary` | Overall score, counts by severity, breakdown by dimension and by table, rows per table |
| `GET /rules?dimension=&table=&severity=&status=` | All rule results, failing first. 400 for an invalid severity or status |
| `GET /rules/{rule_id}` | One rule with its failing-row sample. 404 if unknown |

Each rule result has: `rule_id`, `table`, `dimension`, `severity`, `description`, `rows_checked`, `rows_failed`, `pass_rate_pct`, `status`, `sample` and `duration_seconds`.

Example from `/health`:

```json
{
  "status": "ok",
  "rules_total": 36,
  "quality_score_pct": 99.85,
  "generated_at": "2026-10-16T14:18:10.489290+00:00"
}
```

## Dashboard

A single static page with no build step. It opens on what is broken:

- A headline count of failing rules with a severity breakdown, and the overall score as a secondary figure with a note explaining why the score alone can mislead.
- One tile per dimension showing how many of its rules fail. Clicking a tile filters the list.
- Filters for status (failing, all, passing), severity and table.
- Expandable rule rows that show the rule id, the share of rows affected and a table with the sample of failing records.
- A collapsible list of source tables with their row counts.

It handles free-tier cold starts by polling `/health` every 3 seconds, changing the message after 25 seconds and offering a retry after 2 minutes, so a visitor never sees a blank page.

## Repository structure

```text
.
├── api/
│   ├── main.py                 # read-only API over the report
│   └── requirements.txt        # runtime dependencies for the API only
├── checks/
│   ├── engine.py               # Rule model, run, score and summarize
│   ├── loader.py               # CSV loading
│   └── rules.py                # builders and the 36 rules
├── data/
│   └── exports/dq_report.json  # committed report
├── frontend/
│   └── index.html
├── tests/
│   └── test_rules.py
├── run_checks.py
├── requirements.txt            # pinned versions
├── requirements-dev.txt        # adds pytest
├── .env.example
└── LICENSE
```

Not tracked: `.venv/` and `data/raw/` (the dataset is not redistributed).

## Run locally

Requirements: Python 3.14 (developed on 3.14.4), git and the dataset.

1. Download the Brazilian E-Commerce Public Dataset by Olist from Kaggle.
2. Place these files in `data/raw/`: the customers, order items, order payments, order reviews, orders, products and sellers CSV files, plus `product_category_name_translation.csv`. The geolocation file is not needed.

```bash
git clone https://github.com/juanquiterio/olist-data-quality.git
cd olist-data-quality
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python run_checks.py          # runs the rules, writes data/exports/dq_report.json
pytest -q                     # rule and engine tests

uvicorn main:app --app-dir api --port 8006     # API at http://localhost:8006
cd frontend && python -m http.server 3001      # dashboard at http://localhost:3001
```

The repository already includes a report, so you can start the API and the dashboard without the dataset. The committed frontend points to the hosted API: for local use, change the `API_BASE` constant at the top of the script in `frontend/index.html` to `http://localhost:8006`.

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` | Comma-separated origins allowed by CORS |

Pinned versions: pandas 3.0.6, NumPy 2.5.4, FastAPI 0.143.2, Uvicorn 0.54.0, pytest 9.1.1.

## Tests

Ten pytest tests in `tests/test_rules.py` use small synthetic tables: one per rule builder (including orphan keys with nulls, scoped rules, parents without children and payment reconciliation), the pass-rate and sample logic, the skipped status, the scoring and counts, and a check that every rule id is unique.

## Deployment

Hosted on Render's free plan with two services:

| Service | Type | Configuration |
|---|---|---|
| `olist-dq-api` | Web Service | Build `pip install -r api/requirements.txt`, start `uvicorn main:app --app-dir api --host 0.0.0.0 --port $PORT`, health check `/health` |
| `olist-dq-web` | Static Site | Publish directory `frontend` |

The API installs only FastAPI and Uvicorn, which keeps it inside the 512 MB instance. The free instance sleeps after 15 minutes without traffic, so the first request can take around a minute.

## Technical decisions

| Decision | Why | Trade-off |
|---|---|---|
| Rules as data (`Rule` records) plus reusable builders | Adding a rule is one declaration, and every rule gets the same result format | Complex rules need a custom builder, like the payment reconciliation |
| Precomputed JSON report | The API stays tiny and the demo needs neither pandas nor the dataset | The report is as fresh as the last run |
| Rules scoped to the relevant rows | Honest denominators and no false failures | Each scope has to be chosen carefully |
| Severity as a first-class field | The report can answer "what matters first" | Severities are my judgment, constants in `checks/rules.py` |
| 0.01 BRL tolerance in payment reconciliation | Ignores floating-point noise | An arbitrary threshold |
| Optional fields excluded from completeness | Review comments are naturally empty | Real gaps in those fields are not reported |
| Geolocation table left out | Over a million rows and no rule needs it, which keeps memory low on a 4 GB machine | Location quality is not checked |
| Dataset not redistributed | Respects the dataset's own license | A user has to download it from Kaggle |
| Score as a secondary figure | An average of pass rates hides rare but serious failures | Less useful as a single headline number |

## Challenges and learnings

- **Averages hide failures.** The score is 99.85% while four high-severity rules fail, which led to a dashboard that leads with failing rules and severity instead of a single percentage.
- **Choosing the denominator is half of the work.** A delivery date is only expected on delivered orders, and a foreign key only applies to non-null values. Scoping rules changed their numbers more than any threshold did.
- **Money checks need a tolerance and an owner for the cause.** The payment rule flags real differences. Explaining them would need business context the dataset does not have, so the report states what it found and nothing more.
- **Source quirks stay as they are.** Some column names carry the original typos (for example `product_name_lenght`), so the code uses them unchanged instead of renaming and breaking the link with the source.
- **Keep the heavy work offline.** Running the rules locally and committing the result let the hosted API stay minimal.

## Limitations and next steps

- Rules run in memory with pandas, which suits a dataset of this size. Larger data would need SQL pushdown or chunking.
- There is no history of reports, so quality over time is not tracked.
- The causes of failures (for example the payment gaps) are not diagnosed.
- Severities and the payment tolerance are judgment calls.
- Ideas for later: storing report history, a rule for freight against product weight, and exporting failing records as CSV.

## License

Code: MIT, see `LICENSE`. Data: see the license on the Kaggle dataset page, which is not redistributed here.
