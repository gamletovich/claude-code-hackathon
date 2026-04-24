"""
Characterization tests for Northwind Logistics order processing.

These tests pin the OBSERVABLE BEHAVIOR of the legacy monolith before
any refactoring touches it. The same contract is then enforced against
the modern OrderValidator, proving behavioral equivalence.

Run against legacy:  python -m pytest tests/characterization/ -v
Run against modern:  python -m pytest tests/characterization/ -v
(both suites run automatically — the test runner discovers both classes)
"""

import sys
import os
import copy
import unittest

# Make both source trees importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'legacy', 'src'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'modern', 'src'))

# ---------------------------------------------------------------------------
# Shared test data — identical for both implementations
# ---------------------------------------------------------------------------

_INVENTORY = {
    "SKU-001": {"name": "Widget A",    "qty": 100, "price":  9.99},
    "SKU-002": {"name": "Widget B",    "qty":  50, "price": 19.99},
    "SKU-003": {"name": "Gadget Pro",  "qty":   0, "price": 49.99},
    "SKU-004": {"name": "Connector X", "qty": 200, "price":  4.49},
}

_CUSTOMERS = {
    "CUST-001": {"name": "Acme Corp",    "credit_limit": 10000.0, "balance": 2000.0,  "active": True},
    "CUST-002": {"name": "TechCo Ltd",   "credit_limit":  5000.0, "balance": 4800.0,  "active": True},
    "CUST-003": {"name": "Inactive Inc", "credit_limit":  1000.0, "balance":    0.0,  "active": False},
}


# ---------------------------------------------------------------------------
# Behavioral contract — shared test logic
# ---------------------------------------------------------------------------

class OrderProcessorContract:
    """
    Mixin defining the behavioral contract for order processing.

    Concrete test classes supply self.call(order_data) -> dict.
    All tests run against both the legacy and modern implementations.
    """

    def call(self, order_data: dict) -> dict:
        raise NotImplementedError

    # -- Happy path ----------------------------------------------------------

    def test_valid_order_is_accepted(self):
        order = {
            "customer_id": "CUST-001",
            "items": [
                {"sku": "SKU-001", "quantity": 2},
                {"sku": "SKU-002", "quantity": 1},
            ],
            "shipping_address": "123 Main St, Springfield",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result.get("order_id"), "order_id must be a non-empty string")
        self.assertAlmostEqual(result["total"], 39.97, places=2)

    # -- Customer guard-rails ------------------------------------------------

    def test_unknown_customer_is_rejected(self):
        order = {
            "customer_id": "CUST-999",
            "items": [{"sku": "SKU-001", "quantity": 1}],
            "shipping_address": "1 Nowhere Rd",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Customer not found")

    def test_inactive_customer_is_rejected(self):
        order = {
            "customer_id": "CUST-003",
            "items": [{"sku": "SKU-001", "quantity": 1}],
            "shipping_address": "1 Inactive Ave",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Customer account inactive")

    # -- Inventory guard-rails -----------------------------------------------

    def test_out_of_stock_item_is_rejected(self):
        # SKU-003 has qty=0 in test data
        order = {
            "customer_id": "CUST-001",
            "items": [{"sku": "SKU-003", "quantity": 1}],
            "shipping_address": "123 Main St",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Insufficient stock for SKU-003")

    def test_unknown_sku_is_rejected(self):
        order = {
            "customer_id": "CUST-001",
            "items": [{"sku": "SKU-999", "quantity": 1}],
            "shipping_address": "123 Main St",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Unknown SKU: SKU-999")

    # -- Credit guard-rail ---------------------------------------------------

    def test_order_exceeding_credit_limit_is_rejected(self):
        # CUST-002 has balance=4800 on a 5000 limit → 200 available
        # 25 × SKU-001 @ 9.99 = 249.75 > 200
        order = {
            "customer_id": "CUST-002",
            "items": [{"sku": "SKU-001", "quantity": 25}],
            "shipping_address": "99 Tech Blvd",
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Credit limit exceeded")

    # -- Input validation ----------------------------------------------------

    def test_missing_shipping_address_is_rejected(self):
        order = {
            "customer_id": "CUST-001",
            "items": [{"sku": "SKU-001", "quantity": 1}],
            # no shipping_address key
        }
        result = self.call(order)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Missing shipping_address")

    def test_none_order_data_is_rejected(self):
        result = self.call(None)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Invalid order data")

    def test_empty_order_data_is_rejected(self):
        # {} is falsy in Python, so both implementations treat it as None
        result = self.call({})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "Invalid order data")


# ---------------------------------------------------------------------------
# Legacy implementation under test
# ---------------------------------------------------------------------------

class TestLegacyOrderProcessor(OrderProcessorContract, unittest.TestCase):
    """Run the contract against the legacy monolith (order_processor.py)."""

    def setUp(self):
        import order_processor as m
        self._module = m
        # Reset global state before each test — the monolith mutates these in-place
        self._module.INVENTORY = copy.deepcopy(_INVENTORY)
        self._module.CUSTOMERS = copy.deepcopy(_CUSTOMERS)
        self._module.ORDERS = []

    def call(self, order_data: dict) -> dict:
        return self._module.process_order(order_data)


# ---------------------------------------------------------------------------
# Modern implementation under test
# ---------------------------------------------------------------------------

class TestModernOrderValidator(OrderProcessorContract, unittest.TestCase):
    """Run the same contract against the extracted OrderValidator service."""

    def setUp(self):
        from order_validator import OrderValidator, InMemoryInventoryRepo, InMemoryCustomerRepo
        self.validator = OrderValidator(
            inventory_repo=InMemoryInventoryRepo(copy.deepcopy(_INVENTORY)),
            customer_repo=InMemoryCustomerRepo(copy.deepcopy(_CUSTOMERS)),
        )

    def call(self, order_data: dict) -> dict:
        return self.validator.validate(order_data).to_dict()


if __name__ == "__main__":
    unittest.main(verbosity=2)
