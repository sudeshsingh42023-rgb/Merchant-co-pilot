"""
Every tool here is a thin wrapper over the FastAPI mock-store endpoints
(app/main.py). This is the seam where a real WooCommerce REST integration
would plug in — swap API_BASE and auth headers, keep every tool signature
identical, and the whole agent layer works unchanged against a real store.
"""
import requests
from langchain_core.tools import tool
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "rag"))
from retriever import retrieve_context

API_BASE = "http://localhost:8000"


@tool
def search_products(query: str) -> str:
    """Search the store catalog by product name or category keyword."""
    r = requests.get(f"{API_BASE}/products/search", params={"q": query})
    r.raise_for_status()
    products = r.json()
    if not products:
        return f"No products found matching '{query}'."
    return "\n".join(
        f"[{p['id']}] {p['name']} (SKU {p['sku']}) — ₹{p['price']} — stock: {p['stock']}"
        for p in products
    )


@tool
def update_product_stock(product_id: int, new_stock: int) -> str:
    """Update a product's stock quantity. Provide the numeric product_id
    (from search_products) and the new absolute stock count."""
    r = requests.patch(f"{API_BASE}/products/{product_id}/stock", json={"stock": new_stock})
    if r.status_code == 404:
        return f"Product {product_id} not found."
    r.raise_for_status()
    data = r.json()
    return f"Updated {data['name']} to stock={data['new_stock']}."


@tool
def update_product_price(product_id: int, new_price: float, confirmed: bool = False) -> str:
    """Update a product's price. If the change exceeds 15%, this will be
    REJECTED unless confirmed=true is explicitly passed — this mirrors the
    store's price-change guardrail policy and requires human sign-off in
    the graph before confirmed=true is ever set."""
    r = requests.patch(
        f"{API_BASE}/products/{product_id}/price",
        json={"price": new_price, "confirmed": confirmed},
    )
    if r.status_code == 409:
        return f"BLOCKED: {r.json()['detail']} — ask the merchant to confirm before retrying."
    if r.status_code == 404:
        return f"Product {product_id} not found."
    r.raise_for_status()
    data = r.json()
    return f"Updated {data['name']} price: ₹{data['old_price']} -> ₹{data['new_price']}."


@tool
def get_sales_summary(days: int = 7) -> str:
    """Get order count, completed revenue, and refund count for the last N days."""
    r = requests.get(f"{API_BASE}/orders/summary", params={"days": days})
    r.raise_for_status()
    d = r.json()
    return (f"Last {d['period_days']} days: {d['order_count']} orders, "
            f"₹{d['completed_revenue']} completed revenue, {d['refund_count']} refunds.")


@tool
def get_sales_trend(weeks: int = 4) -> str:
    """Get weekly order count + revenue for the last N weeks, most recent first.
    Use this to spot and explain trends like a recent sales dip."""
    r = requests.get(f"{API_BASE}/orders/trend", params={"weeks": weeks})
    r.raise_for_status()
    rows = r.json()
    return "\n".join(
        f"Week of {row['week_starting']}: {row['order_count']} orders, ₹{row['revenue']} revenue"
        for row in rows
    )


@tool
def get_dormant_customers(days: int = 60) -> str:
    """List customers with no order in the last N days — candidates for a win-back campaign."""
    r = requests.get(f"{API_BASE}/customers/dormant", params={"days": days})
    r.raise_for_status()
    customers = r.json()
    if not customers:
        return "No dormant customers found."
    return "\n".join(f"{c['name']} ({c['email']}) — last order: {c['last_order'] or 'never'}"
                      for c in customers[:15])


@tool
def retrieve_policy_or_ticket_context(question: str) -> str:
    """Semantic search over store policies and past resolved support tickets.
    ALWAYS call this before answering a customer support question so the
    answer is grounded in actual policy rather than guessed."""
    return retrieve_context(question)
