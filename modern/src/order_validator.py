"""
OrderValidator — clean extraction from the Northwind Logistics monolith.

Design principles applied:
- Dependency injection: repos are passed in, not imported globally
- Single responsibility: validates only, never commits state
- Early returns: no nested if-ladders
- Typed results: ValidationResult carries the full contract
"""
from __future__ import annotations

import uuid
from typing import Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class ValidationResult:
    """Outcome of a validation pass. Do not mutate attributes after construction."""

    def __init__(self, accepted: bool, reason: str = "", order_id: str = "", total: float = 0.0):
        self.accepted = accepted
        self.reason = reason
        self.order_id = order_id
        self.total = total

    @classmethod
    def accept(cls, order_id: str, total: float) -> "ValidationResult":
        return cls(accepted=True, order_id=order_id, total=round(total, 2))

    @classmethod
    def reject(cls, reason: str) -> "ValidationResult":
        return cls(accepted=False, reason=reason)

    def to_dict(self) -> dict:
        if self.accepted:
            return {"status": "accepted", "order_id": self.order_id, "total": self.total}
        return {"status": "rejected", "reason": self.reason}

    def __repr__(self) -> str:
        if self.accepted:
            return f"<ValidationResult accepted order_id={self.order_id} total={self.total}>"
        return f"<ValidationResult rejected reason={self.reason!r}>"


# ---------------------------------------------------------------------------
# Repository protocols (dependency contracts)
# ---------------------------------------------------------------------------

@runtime_checkable
class InventoryRepo(Protocol):
    def get_item(self, sku: str) -> Optional[dict]: ...


@runtime_checkable
class CustomerRepo(Protocol):
    def get_customer(self, customer_id: str) -> Optional[dict]: ...


# ---------------------------------------------------------------------------
# In-memory implementations for testing
# ---------------------------------------------------------------------------

class InMemoryInventoryRepo:
    """Test double — backed by a plain dict, no global state."""

    def __init__(self, items: dict):
        self._items = items

    def get_item(self, sku: str) -> Optional[dict]:
        return self._items.get(sku)


class InMemoryCustomerRepo:
    """Test double — backed by a plain dict, no global state."""

    def __init__(self, customers: dict):
        self._customers = customers

    def get_customer(self, customer_id: str) -> Optional[dict]:
        return self._customers.get(customer_id)


# ---------------------------------------------------------------------------
# Validator — the extracted service boundary
# ---------------------------------------------------------------------------

class OrderValidator:
    """
    Validates an order against current inventory and customer credit.

    Pure validation only: no state is committed, no emails sent,
    no HTTP calls made. The caller decides what to do with the result.
    """

    def __init__(self, inventory_repo: InventoryRepo, customer_repo: CustomerRepo):
        self._inventory = inventory_repo
        self._customers = customer_repo

    def validate(self, order_data: dict) -> ValidationResult:
        """Return a ValidationResult without modifying any external state."""
        if not order_data:
            return ValidationResult.reject("Invalid order data")

        customer_id = order_data.get("customer_id")
        if not customer_id:
            return ValidationResult.reject("Missing customer_id")

        customer = self._customers.get_customer(customer_id)
        if not customer:
            return ValidationResult.reject("Customer not found")

        if not customer.get("active"):
            return ValidationResult.reject("Customer account inactive")

        items = order_data.get("items", [])
        if not items:
            return ValidationResult.reject("No items in order")

        if not order_data.get("shipping_address"):
            return ValidationResult.reject("Missing shipping_address")

        total, error = self._validate_items(items)
        if error:
            return ValidationResult.reject(error)

        available_credit = customer["credit_limit"] - customer["balance"]
        if total > available_credit:
            return ValidationResult.reject("Credit limit exceeded")

        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        return ValidationResult.accept(order_id, total)

    def _validate_items(self, items: list) -> "tuple[float, str]":
        """Check stock availability for each line item. Returns (total, error_or_empty).

        Rounds each line before accumulating to match legacy floating-point behavior.
        """
        total = 0.0
        for item in items:
            sku = item.get("sku") or "<missing>"
            stock = self._inventory.get_item(sku)
            if stock is None:
                return 0.0, f"Unknown SKU: {sku}"
            qty = item.get("quantity", 0)
            if stock["qty"] < qty:
                return 0.0, f"Insufficient stock for {sku}"
            total += round(stock["price"] * qty, 2)
        return round(total, 2), ""
