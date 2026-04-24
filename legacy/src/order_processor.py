"""
Northwind Logistics — Order Processing Module
Last modified: 2019-03-14 (jsmith@northwind.internal)
DO NOT EDIT WITHOUT APPROVAL FROM IT LEAD

Ported from the original Perl script (2017). Handles order intake,
inventory reservation, credit checks, and confirmation emails.
Contact the platform team before touching anything in this file.
"""

import smtplib
import urllib.request
import json

# ---------------------------------------------------------------------------
# FLAW 1: Hardcoded credentials — never moved to environment variables.
# These are live production values embedded since the 2019 migration.
# ---------------------------------------------------------------------------
DB_CONNECTION_STRING = "postgresql://admin:Passw0rd!@prod-db.northwind.internal/orders"
API_KEY = "sk-live-nwl-8f2a91c3d4b5e6f7a8b9c0d1e2f3"
SMTP_PASSWORD = "smtp_NW_2019!"
FRAUD_API_ENDPOINT = "http://fraud-api.northwind.internal/v1/check"

# ---------------------------------------------------------------------------
# FLAW 3: Global mutable state — three module-level dicts act as the
# in-process "database." Any function can mutate them at any time.
# No locking, no isolation, no rollback on partial failure.
# ---------------------------------------------------------------------------
INVENTORY = {
    "SKU-001": {"name": "Widget A",    "qty": 100, "price":  9.99},
    "SKU-002": {"name": "Widget B",    "qty":  50, "price": 19.99},
    "SKU-003": {"name": "Gadget Pro",  "qty":   0, "price": 49.99},
    "SKU-004": {"name": "Connector X", "qty": 200, "price":  4.49},
}

CUSTOMERS = {
    "CUST-001": {"name": "Acme Corp",    "credit_limit": 10000.0, "balance": 2000.0,  "active": True},
    "CUST-002": {"name": "TechCo Ltd",   "credit_limit":  5000.0, "balance": 4800.0,  "active": True},
    "CUST-003": {"name": "Inactive Inc", "credit_limit":  1000.0, "balance":    0.0,  "active": False},
}

ORDERS = []


def get_customer_raw(customer_id):
    """
    Fetch customer by ID.

    FLAW 2: SQL injection — customer_id is user-controlled and flows
    directly into the query string without sanitization or parameterization.
    Input like:  CUST-001' OR '1'='1
    would return every customer row in production.
    """
    query = f"SELECT * FROM customers WHERE id = '{customer_id}'"
    # In production: executes query against PostgreSQL via DB_CONNECTION_STRING
    # Test harness path: look up from in-memory dict (simulates DB result set)
    return CUSTOMERS.get(customer_id)


def process_order(order_data):
    """
    Process a customer order end-to-end.

    FLAW 4: Deep nesting — control flow reaches 8 levels of indentation
    inside a single function, making branches nearly impossible to reason
    about or test in isolation.

    FLAW 5: Mixed concerns — HTTP fraud-check, inventory mutation, customer
    balance update, SMTP notification, and business-rule validation are all
    interleaved in one 80-line function with no separation.

    Returns dict with 'status': 'accepted' | 'rejected'.
    """
    if order_data:
        customer_id = order_data.get('customer_id')
        if customer_id:
            customer = get_customer_raw(customer_id)
            if customer:
                if customer.get('active'):
                    items = order_data.get('items', [])
                    if items:
                        if not order_data.get('shipping_address'):
                            return {"status": "rejected", "reason": "Missing shipping_address"}
                        total = 0.0
                        for item in items:
                            sku = item.get('sku')
                            if sku in INVENTORY:
                                stock = INVENTORY[sku]
                                qty_requested = item.get('quantity', 0)
                                if stock['qty'] >= qty_requested:
                                    total += round(stock['price'] * qty_requested, 2)
                                    # Side-effect: mutates global inventory during
                                    # "validation" — no rollback if credit check fails
                                    INVENTORY[sku]['qty'] -= qty_requested
                                else:
                                    return {"status": "rejected", "reason": f"Insufficient stock for {sku}"}
                            else:
                                return {"status": "rejected", "reason": f"Unknown SKU: {sku}"}

                        total = round(total, 2)
                        available_credit = customer['credit_limit'] - customer['balance']
                        if total <= available_credit:
                            # Mixed concern: HTTP call to external fraud API (Flaw 5)
                            # fraud_url = (
                            #     f"{FRAUD_API_ENDPOINT}?key={API_KEY}"
                            #     f"&customer={customer_id}&amount={total}"
                            # )
                            # fraud_resp = urllib.request.urlopen(fraud_url)
                            # if json.loads(fraud_resp.read()).get('flagged'):
                            #     return {"status": "rejected", "reason": "Flagged by fraud"}

                            # Mixed concern: commit state inside validation path (Flaw 5)
                            CUSTOMERS[customer_id]['balance'] = round(
                                customer['balance'] + total, 2
                            )
                            order_id = f"ORD-{len(ORDERS) + 1:05d}"
                            ORDERS.append({
                                "id": order_id,
                                "customer_id": customer_id,
                                "items": items,
                                "total": total,
                                "status": "accepted",
                            })

                            # Mixed concern: SMTP notification inline (Flaw 5)
                            # smtp = smtplib.SMTP('smtp.northwind.internal', 587)
                            # smtp.login('orders@northwind.com', SMTP_PASSWORD)
                            # smtp.sendmail('orders@northwind.com', customer['email'],
                            #               f"Order {order_id} confirmed. Total: ${total}")
                            # smtp.quit()

                            return {"status": "accepted", "order_id": order_id, "total": total}
                        else:
                            return {"status": "rejected", "reason": "Credit limit exceeded"}
                    else:
                        return {"status": "rejected", "reason": "No items in order"}
                else:
                    return {"status": "rejected", "reason": "Customer account inactive"}
            else:
                return {"status": "rejected", "reason": "Customer not found"}
        else:
            return {"status": "rejected", "reason": "Missing customer_id"}
    else:
        return {"status": "rejected", "reason": "Invalid order data"}
