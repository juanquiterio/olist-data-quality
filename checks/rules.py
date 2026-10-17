"""Data quality rules for the Olist dataset.

Every builder returns a check: tables -> (rows_checked, failed_rows_dataframe).
"""

import pandas as pd

from checks.engine import Rule

# Max difference (BRL) between money paid and items + freight before an order is flagged.
PAYMENT_TOLERANCE = 0.01

ORDER_STATUSES = {
    "delivered", "shipped", "canceled", "unavailable",
    "invoiced", "processing", "created", "approved",
}
PROGRESSED = {"approved", "invoiced", "processing", "shipped", "delivered"}
SHIPPED = {"shipped", "delivered"}
PAYMENT_TYPES = {"credit_card", "boleto", "voucher", "debit_card"}


def unique_key(table: str, cols: list):
    """Rows whose key already appeared earlier in the table."""
    def check(tables):
        df = tables[table]
        return len(df), df.loc[df.duplicated(subset=cols, keep="first"), cols]
    return check


def not_null(table: str, cols: list, key: list, where=None):
    """Rows in scope where any of the given columns is null."""
    def check(tables):
        df = tables[table]
        scope = df[where(df)] if where else df
        return len(scope), scope.loc[scope[cols].isna().any(axis=1), key]
    return check


def foreign_key(child: str, col: str, parent: str, parent_col: str):
    """Non-null child values that do not exist in the parent table."""
    def check(tables):
        df = tables[child]
        scope = df[df[col].notna()]
        missing = ~scope[col].isin(tables[parent][parent_col])
        return len(scope), scope.loc[missing, [col]]
    return check


def has_children(parent: str, parent_col: str, child: str, child_col: str, where=None):
    """Parent rows in scope with no matching row in the child table."""
    def check(tables):
        df = tables[parent]
        scope = df[where(df)] if where else df
        missing = ~scope[parent_col].isin(tables[child][child_col])
        return len(scope), scope.loc[missing, [parent_col]]
    return check


def row_rule(table: str, key: list, valid, where=None):
    """Rows in scope for which the validity function returns False."""
    def check(tables):
        df = tables[table]
        scope = df[where(df)] if where else df
        return len(scope), scope.loc[~valid(scope), key]
    return check


def present(*cols):
    return lambda df: df[list(cols)].notna().all(axis=1)


def payments_match_items():
    """Orders where money paid differs from items plus freight."""
    def check(tables):
        items = tables["order_items"]
        pays = tables["order_payments"]
        expected = (items["price"] + items["freight_value"]).groupby(items["order_id"]).sum()
        paid = pays["payment_value"].groupby(pays["order_id"]).sum()
        both = pd.concat([expected.rename("expected"), paid.rename("paid")], axis=1, join="inner")
        both.index.name = "order_id"
        both["difference"] = (both["paid"] - both["expected"]).abs()
        failed = both.loc[both["difference"] > PAYMENT_TOLERANCE].round(2).reset_index()
        return len(both), failed
    return check


def build_rules() -> list:
    """All rules, grouped by quality dimension."""
    U, C, R, V, K = "uniqueness", "completeness", "referential_integrity", "validity", "consistency"
    return [
        # Uniqueness
        Rule("uniq_customers_id", "customers", U, "critical", "customer_id is unique",
             unique_key("customers", ["customer_id"])),
        Rule("uniq_orders_id", "orders", U, "critical", "order_id is unique",
             unique_key("orders", ["order_id"])),
        Rule("uniq_products_id", "products", U, "critical", "product_id is unique",
             unique_key("products", ["product_id"])),
        Rule("uniq_sellers_id", "sellers", U, "critical", "seller_id is unique",
             unique_key("sellers", ["seller_id"])),
        Rule("uniq_order_items_pk", "order_items", U, "critical",
             "(order_id, order_item_id) is unique",
             unique_key("order_items", ["order_id", "order_item_id"])),
        Rule("uniq_order_payments_pk", "order_payments", U, "critical",
             "(order_id, payment_sequential) is unique",
             unique_key("order_payments", ["order_id", "payment_sequential"])),
        Rule("uniq_reviews_id", "order_reviews", U, "high", "review_id is unique",
             unique_key("order_reviews", ["review_id"])),
        Rule("uniq_translation_category", "category_translation", U, "medium",
             "product_category_name is unique",
             unique_key("category_translation", ["product_category_name"])),
        # Completeness
        Rule("null_orders_approved_at", "orders", C, "medium",
             "Orders past 'created' have an approval timestamp",
             not_null("orders", ["order_approved_at"], ["order_id"],
                      where=lambda d: d["order_status"].isin(PROGRESSED))),
        Rule("null_orders_carrier_date", "orders", C, "medium",
             "Shipped or delivered orders have a carrier handoff date",
             not_null("orders", ["order_delivered_carrier_date"], ["order_id"],
                      where=lambda d: d["order_status"].isin(SHIPPED))),
        Rule("null_orders_customer_date", "orders", C, "high",
             "Delivered orders have a customer delivery date",
             not_null("orders", ["order_delivered_customer_date"], ["order_id"],
                      where=lambda d: d["order_status"] == "delivered")),
        Rule("null_products_category", "products", C, "medium",
             "Products have a category",
             not_null("products", ["product_category_name"], ["product_id"])),
        Rule("null_products_content", "products", C, "medium",
             "Products have name length, description length and photo count",
             not_null("products",
                      ["product_name_lenght", "product_description_lenght", "product_photos_qty"],
                      ["product_id"])),
        Rule("null_products_dimensions", "products", C, "medium",
             "Products have weight and dimensions",
             not_null("products",
                      ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
                      ["product_id"])),
        # Referential integrity
        Rule("fk_orders_customer", "orders", R, "critical", "Every order has a customer",
             foreign_key("orders", "customer_id", "customers", "customer_id")),
        Rule("fk_items_order", "order_items", R, "critical", "Every item belongs to an order",
             foreign_key("order_items", "order_id", "orders", "order_id")),
        Rule("fk_items_product", "order_items", R, "high", "Every item references a known product",
             foreign_key("order_items", "product_id", "products", "product_id")),
        Rule("fk_items_seller", "order_items", R, "high", "Every item references a known seller",
             foreign_key("order_items", "seller_id", "sellers", "seller_id")),
        Rule("fk_payments_order", "order_payments", R, "critical", "Every payment belongs to an order",
             foreign_key("order_payments", "order_id", "orders", "order_id")),
        Rule("fk_reviews_order", "order_reviews", R, "high", "Every review belongs to an order",
             foreign_key("order_reviews", "order_id", "orders", "order_id")),
        Rule("fk_products_category", "products", R, "medium",
             "Product categories exist in the translation table",
             foreign_key("products", "product_category_name",
                         "category_translation", "product_category_name")),
        Rule("orders_delivered_have_items", "orders", R, "high",
             "Delivered orders have at least one item",
             has_children("orders", "order_id", "order_items", "order_id",
                          where=lambda d: d["order_status"] == "delivered")),
        Rule("orders_have_payments", "orders", R, "high", "Every order has at least one payment",
             has_children("orders", "order_id", "order_payments", "order_id")),
        # Validity
        Rule("valid_order_status", "orders", V, "high", "Order status is a known value",
             row_rule("orders", ["order_id", "order_status"],
                      lambda d: d["order_status"].isin(ORDER_STATUSES))),
        Rule("valid_item_price", "order_items", V, "high", "Item price is positive",
             row_rule("order_items", ["order_id", "order_item_id", "price"],
                      lambda d: d["price"] > 0)),
        Rule("valid_item_freight", "order_items", V, "medium", "Freight value is not negative",
             row_rule("order_items", ["order_id", "order_item_id", "freight_value"],
                      lambda d: d["freight_value"] >= 0)),
        Rule("valid_payment_value", "order_payments", V, "medium", "Payment value is positive",
             row_rule("order_payments", ["order_id", "payment_sequential", "payment_value"],
                      lambda d: d["payment_value"] > 0)),
        Rule("valid_payment_installments", "order_payments", V, "medium",
             "Payments have at least one installment",
             row_rule("order_payments", ["order_id", "payment_sequential", "payment_installments"],
                      lambda d: d["payment_installments"] >= 1)),
        Rule("valid_payment_type", "order_payments", V, "medium", "Payment type is a known value",
             row_rule("order_payments", ["order_id", "payment_sequential", "payment_type"],
                      lambda d: d["payment_type"].isin(PAYMENT_TYPES))),
        Rule("valid_review_score", "order_reviews", V, "high", "Review score is between 1 and 5",
             row_rule("order_reviews", ["review_id", "review_score"],
                      lambda d: d["review_score"].between(1, 5))),
        # Consistency
        Rule("cons_approved_after_purchase", "orders", K, "medium",
             "Approval happens on or after purchase",
             row_rule("orders", ["order_id"],
                      lambda d: d["order_approved_at"] >= d["order_purchase_timestamp"],
                      where=present("order_approved_at", "order_purchase_timestamp"))),
        Rule("cons_carrier_after_purchase", "orders", K, "medium",
             "Carrier handoff happens on or after purchase",
             row_rule("orders", ["order_id"],
                      lambda d: d["order_delivered_carrier_date"] >= d["order_purchase_timestamp"],
                      where=present("order_delivered_carrier_date", "order_purchase_timestamp"))),
        Rule("cons_delivery_after_carrier", "orders", K, "medium",
             "Customer delivery happens on or after carrier handoff",
             row_rule("orders", ["order_id"],
                      lambda d: d["order_delivered_customer_date"] >= d["order_delivered_carrier_date"],
                      where=present("order_delivered_customer_date", "order_delivered_carrier_date"))),
        Rule("cons_delivery_after_purchase", "orders", K, "high",
             "Customer delivery happens on or after purchase",
             row_rule("orders", ["order_id"],
                      lambda d: d["order_delivered_customer_date"] >= d["order_purchase_timestamp"],
                      where=present("order_delivered_customer_date", "order_purchase_timestamp"))),
        Rule("cons_undelivered_no_delivery_date", "orders", K, "medium",
             "Orders not marked delivered have no customer delivery date",
             row_rule("orders", ["order_id", "order_status"],
                      lambda d: d["order_delivered_customer_date"].isna(),
                      where=lambda d: d["order_status"] != "delivered")),
        Rule("cons_payments_match_items", "order_payments", K, "high",
             "Money paid matches items plus freight per order",
             payments_match_items()),
    ]
