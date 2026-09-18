"""
Mock WooCommerce-style REST API.
In production this file is exactly what would be replaced by real WooCommerce
REST API calls (wc/v3/products, wc/v3/orders, etc). Every agent tool in
agents/tools.py hits one of these endpoints, so swapping the backend later
means changing only the base URL, not any agent logic.
"""
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

from db import get_db, init_db, Product, Order, OrderItem, Customer, SupportTicket, StorePolicy

app = FastAPI(title="Mock Store API (WooCommerce-style)")
init_db()


# ---------- Schemas ----------
class StockUpdate(BaseModel):
    stock: int


class PriceUpdate(BaseModel):
    price: float
    confirmed: bool = False  # required if change > 15%, mirrors the price-change policy


class ProductOut(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    stock: int
    category: str

    class Config:
        from_attributes = True


# ---------- Products ----------
@app.get("/products", response_model=list[ProductOut])
def list_products(category: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Product)
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))
    return q.all()


@app.get("/products/search")
def search_products(q: str, db: Session = Depends(get_db)):
    results = db.query(Product).filter(
        (Product.name.ilike(f"%{q}%")) | (Product.category.ilike(f"%{q}%"))
    ).all()
    return [ProductOut.model_validate(p) for p in results]


@app.patch("/products/{product_id}/stock")
def update_stock(product_id: int, payload: StockUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.stock = payload.stock
    db.commit()
    return {"id": product.id, "name": product.name, "new_stock": product.stock}


@app.patch("/products/{product_id}/price")
def update_price(product_id: int, payload: PriceUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    change_pct = abs(payload.price - product.price) / product.price * 100
    if change_pct > 15 and not payload.confirmed:
        raise HTTPException(
            status_code=409,
            detail=f"Price change of {change_pct:.1f}% exceeds 15% guardrail. "
                   f"Resend with confirmed=true to override.",
        )
    old_price = product.price
    product.price = payload.price
    db.commit()
    return {"id": product.id, "name": product.name, "old_price": old_price, "new_price": product.price}


# ---------- Orders / Reporting ----------
@app.get("/orders/summary")
def orders_summary(days: int = 7, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    orders = db.query(Order).filter(Order.created_at >= since).all()
    revenue = sum(o.total for o in orders if o.status == "completed")
    refunds = sum(1 for o in orders if o.status == "refunded")
    return {
        "period_days": days,
        "order_count": len(orders),
        "completed_revenue": round(revenue, 2),
        "refund_count": refunds,
    }


@app.get("/orders/trend")
def orders_trend(weeks: int = 4, db: Session = Depends(get_db)):
    """Weekly order counts + revenue, most recent week first — what the
    Reporting Agent uses to notice and explain the sales dip."""
    trend = []
    for w in range(weeks):
        start = datetime.utcnow() - timedelta(days=7 * (w + 1))
        end = datetime.utcnow() - timedelta(days=7 * w)
        orders = db.query(Order).filter(Order.created_at >= start, Order.created_at < end).all()
        revenue = sum(o.total for o in orders if o.status == "completed")
        trend.append({
            "week_starting": start.date().isoformat(),
            "order_count": len(orders),
            "revenue": round(revenue, 2),
        })
    return trend


@app.get("/customers/dormant")
def dormant_customers(days: int = 60, db: Session = Depends(get_db)):
    """Customers with no order in `days` — used by both Reporting and
    Content agents (e.g. to draft a win-back email)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = []
    for c in db.query(Customer).all():
        last_order = (
            db.query(Order).filter(Order.customer_id == c.id).order_by(Order.created_at.desc()).first()
        )
        if not last_order or last_order.created_at < cutoff:
            result.append({"id": c.id, "name": c.name, "email": c.email,
                            "last_order": last_order.created_at.isoformat() if last_order else None})
    return result


# ---------- Support ----------
@app.get("/tickets/recent")
def recent_tickets(limit: int = 20, db: Session = Depends(get_db)):
    tickets = db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(limit).all()
    return [
        {"id": t.id, "subject": t.subject, "body": t.body, "resolution": t.resolution,
         "customer_email": t.customer_email}
        for t in tickets
    ]


@app.get("/policies")
def list_policies(db: Session = Depends(get_db)):
    return [{"title": p.title, "content": p.content} for p in db.query(StorePolicy).all()]


@app.get("/health")
def health():
    return {"status": "ok"}
