"""Load the Olist CSV files, keeping only the columns the rules need."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("loader")

ORDER_DATES = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

# name -> (file, columns to read or None for all, date columns)
SOURCES = {
    "customers": ("olist_customers_dataset.csv", ["customer_id"], []),
    "sellers": ("olist_sellers_dataset.csv", ["seller_id"], []),
    "products": ("olist_products_dataset.csv", None, []),
    "orders": ("olist_orders_dataset.csv", None, ORDER_DATES),
    "order_items": (
        "olist_order_items_dataset.csv",
        ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"],
        [],
    ),
    "order_payments": ("olist_order_payments_dataset.csv", None, []),
    "order_reviews": ("olist_order_reviews_dataset.csv", ["review_id", "order_id", "review_score"], []),
    "category_translation": ("product_category_name_translation.csv", None, []),
}


def load_tables(raw_dir: Path) -> dict:
    """Read every source file into a DataFrame."""
    tables: dict = {}
    for name, (filename, usecols, dates) in SOURCES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing source file: {path}")
        tables[name] = pd.read_csv(path, usecols=usecols, parse_dates=dates)
        logger.info("Loaded %s: %d rows", name, len(tables[name]))
    return tables
