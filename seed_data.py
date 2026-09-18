"""
Populates store.db with a believable mid-size apparel store:
- 40 products across 5 categories
- 25 customers
- ~120 orders spread over the last 90 days (with a deliberate dip in the
  last 2 weeks so the Reporting Agent has something real to notice)
- 15 support tickets
- 5 store policies (for RAG ingestion)
"""
import random
from datetime import datetime, timedelta
from db import SessionLocal, init_db, Product, Customer, Order, OrderItem, SupportTicket, StorePolicy

random.seed(42)

CATEGORIES = {
    "Hoodies": ["Classic Hoodie", "Zip-Up Hoodie", "Oversized Hoodie", "Fleece Hoodie"],
    "Running Gear": ["Waterproof Running Jacket", "Running Shorts", "Compression Tights", "Running Cap"],
    "T-Shirts": ["Basic Tee", "Graphic Tee", "Long Sleeve Tee", "Performance Tee"],
    "Footwear": ["Trail Runner", "Casual Sneaker", "Slide Sandal", "Ankle Boot"],
    "Accessories": ["Duffel Bag", "Water Bottle", "Beanie", "Crew Socks"],
}
COLORS = ["Black", "Navy", "Grey", "Olive", "White"]
SIZES = ["S", "M", "L", "XL"]


def seed():
    init_db()
    db = SessionLocal()

    if db.query(Product).first():
        print("DB already seeded, skipping.")
        return

    # Products
    products = []
    sku_counter = 1000
    for cat, names in CATEGORIES.items():
        for name in names:
            for color in random.sample(COLORS, 2):
                sku_counter += 1
                p = Product(
                    name=f"{color} {name}",
                    sku=f"SKU-{sku_counter}",
                    price=round(random.uniform(499, 4999), 2),
                    stock=random.randint(0, 120),
                    category=cat,
                    description=f"{color} {name.lower()} from our {cat.lower()} line. "
                                 f"Machine washable, true to size.",
                )
                products.append(p)
    db.add_all(products)
    db.commit()

    # Customers
    customers = []
    for i in range(25):
        c = Customer(
            name=f"Customer {i+1}",
            email=f"customer{i+1}@example.com",
            joined_at=datetime.utcnow() - timedelta(days=random.randint(30, 500)),
        )
        customers.append(c)
    db.add_all(customers)
    db.commit()

    all_products = db.query(Product).all()
    all_customers = db.query(Customer).all()

    # Orders — normal volume for days 90->14 ago, deliberate ~35% dip in last 14 days
    for day_offset in range(90, 0, -1):
        order_date = datetime.utcnow() - timedelta(days=day_offset)
        daily_orders = random.randint(2, 5)
        if day_offset <= 14:
            daily_orders = max(0, daily_orders - 2)  # the dip

        for _ in range(daily_orders):
            cust = random.choice(all_customers)
            order = Order(customer_id=cust.id, created_at=order_date, status="completed")
            db.add(order)
            db.flush()

            items = random.sample(all_products, random.randint(1, 3))
            total = 0.0
            for prod in items:
                qty = random.randint(1, 2)
                oi = OrderItem(order_id=order.id, product_id=prod.id, quantity=qty, unit_price=prod.price)
                total += qty * prod.price
                db.add(oi)
            order.total = round(total, 2)
    db.commit()

    # A few refunds for realism
    completed = db.query(Order).filter(Order.status == "completed").all()
    for order in random.sample(completed, 6):
        order.status = "refunded"
    db.commit()

    # Support tickets
    ticket_templates = [
        ("Order hasn't arrived", "It's been 10 days and my order #{oid} hasn't shipped yet.", "Escalated to logistics, refund issued after 14 days per policy."),
        ("Wrong size received", "I ordered L but got M for order #{oid}.", "Free size-exchange label sent, no return shipping cost per policy."),
        ("Refund not received", "I returned my item 2 weeks ago, no refund for order #{oid} yet.", "Refunds process in 5-7 business days; escalated for manual review."),
        ("Product defect", "The hoodie zipper broke after one wash, order #{oid}.", "Replacement sent free of charge, defect logged for QA."),
        ("Coupon not applying", "My discount code didn't apply at checkout.", "Codes are case-sensitive and single-use; reissued a valid code."),
    ]
    for i in range(15):
        subj, body, res = random.choice(ticket_templates)
        oid = random.choice(completed).id
        t = SupportTicket(
            customer_email=random.choice(all_customers).email,
            subject=subj,
            body=body.format(oid=oid),
            resolution=res,
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 60)),
        )
        db.add(t)
    db.commit()

    # Store policies (RAG source material)
    policies = [
        ("Refund Policy", "Refunds are processed within 5-7 business days after the returned item is received. "
                           "Orders undelivered after 14 days from the expected date are automatically eligible for a full refund."),
        ("Exchange Policy", "Size and color exchanges are free within 30 days of delivery. Customers do not pay return shipping "
                             "for exchanges caused by a sizing error on our end."),
        ("Shipping Policy", "Standard shipping takes 4-7 business days. Orders placed before 2 PM ship the same day. "
                             "We do not ship internationally at this time."),
        ("Discount Code Policy", "Discount codes are case-sensitive, single-use per customer, and cannot be combined with "
                                  "other promotions. Expired codes cannot be manually reactivated."),
        ("Price Change Policy", "Any single product price change greater than 15% requires manager confirmation before "
                                 "being applied to the live store."),
    ]
    for title, content in policies:
        db.add(StorePolicy(title=title, content=content))
    db.commit()

    print(f"Seeded {len(products)} products, {len(customers)} customers, "
          f"{db.query(Order).count()} orders, 15 tickets, {len(policies)} policies.")


if __name__ == "__main__":
    seed()
