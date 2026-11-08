from datetime import date, timedelta

import pytest

from shop.db import ShopDB, open_shop_db
from shop.seed import build_database

TODAY = date(2026, 11, 8)


@pytest.fixture
def db(tmp_path):
    return ShopDB(build_database(tmp_path / "shop.db", today=TODAY))


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def delivery(db, order_id):
    return db.query_one("SELECT * FROM deliveries WHERE order_id = ?", (order_id,))


def test_seed_can_run_twice(tmp_path):
    build_database(tmp_path / "shop.db", today=TODAY)
    db = ShopDB(build_database(tmp_path / "shop.db", today=TODAY))
    assert db.query_one("SELECT COUNT(*) AS n FROM customers")["n"] == 10


def test_sizes(db):
    assert db.query_one("SELECT COUNT(*) AS n FROM orders")["n"] == 25
    assert db.query_one("SELECT COUNT(*) AS n FROM deliveries")["n"] == 25
    assert 12 <= db.query_one("SELECT COUNT(*) AS n FROM faq")["n"] <= 15
    assert db.query_one("SELECT COUNT(*) AS n FROM return_policy")["n"] >= 5


def test_every_order_has_items_and_correct_total(db):
    rows = db.query(
        "SELECT o.id, o.total, SUM(i.quantity * i.unit_price) AS item_sum "
        "FROM orders o JOIN order_items i ON i.order_id = o.id GROUP BY o.id"
    )
    assert len(rows) == 25
    for row in rows:
        assert row["total"] == pytest.approx(row["item_sum"])


def test_phone_numbers_are_digits_only(db):
    for row in db.query("SELECT phone FROM customers"):
        assert row["phone"].isdigit()


def test_tricky_cases_exist(db):
    # One customer with a single order, one with several.
    assert db.query_one("SELECT COUNT(*) AS n FROM orders WHERE customer_id = 'C001'")["n"] == 1
    assert db.query_one("SELECT COUNT(*) AS n FROM orders WHERE customer_id = 'C002'")["n"] == 3

    assert delivery(db, "SE-1042")["status"] == "in_transit"

    late = delivery(db, "SE-1061")
    assert late["status"] == "delayed"
    assert late["original_date"] < TODAY.isoformat() < late["expected_date"]

    assert delivery(db, "SE-1071")["status"] == "lost"
    assert delivery(db, "SE-1052")["status"] == "preparing"
    assert delivery(db, "SE-1082")["status"] == "cancelled"

    assert delivery(db, "SE-1051")["delivered_date"] == days_ago(10)  # can still return
    assert delivery(db, "SE-1053")["delivered_date"] == days_ago(45)  # too late
    assert delivery(db, "SE-1121")["delivered_date"] == days_ago(28)  # just inside
    assert delivery(db, "SE-1122")["delivered_date"] == days_ago(31)  # just outside


def test_items_that_cannot_be_returned(db):
    rows = db.query("SELECT category FROM order_items WHERE returnable = 0")
    assert {row["category"] for row in rows} >= {"underwear", "software", "gift_card", "personalised"}


def test_order_status_matches_delivery_status(db):
    rows = db.query("SELECT o.status AS o, d.status AS d FROM orders o JOIN deliveries d ON d.order_id = o.id")
    for row in rows:
        if row["d"] == "delivered":
            assert row["o"] == "delivered"
        if row["d"] == "preparing":
            assert row["o"] == "processing"


def test_open_shop_db_builds_missing_file(tmp_path):
    db = open_shop_db(tmp_path / "new" / "shop.db")
    assert db.path.exists()
    assert db.query_one("SELECT first_name FROM customers WHERE id = 'C001'")["first_name"] == "Sara"


def test_execute_returns_row_id(db):
    row_id = db.execute(
        "INSERT INTO handoffs (customer_id, reason, created_at) VALUES ('C001', 'test', '2026-11-08')"
    )
    assert row_id == 1
