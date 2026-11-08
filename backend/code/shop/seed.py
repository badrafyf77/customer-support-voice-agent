"""Build a fresh ShopEasy database with fake data.

Run it from ``backend/code``:  ``python -m shop.seed``

Every date is counted from today, so "delivered 10 days ago" stays true on any
day we run the tests. The orders are chosen on purpose to cover the tricky
cases: late, lost, too late to return, items that can't be returned, and so on.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from shop.db import default_db_path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
RETURN_WINDOW_DAYS = 30

CUSTOMERS = [
    # id, first, last, phone, email, city
    ("C001", "Sara", "Benali", "07700900101", "sara.benali@example.com", "Leeds"),
    ("C002", "James", "Carter", "07700900102", "james.carter@example.com", "Bristol"),
    ("C003", "Amina", "Haddad", "07700900103", "amina.haddad@example.com", "Manchester"),
    ("C004", "Daniel", "Kim", "07700900104", "daniel.kim@example.com", "London"),
    ("C005", "Laura", "Martin", "07700900105", "laura.martin@example.com", "Cardiff"),
    ("C006", "Omar", "Farouk", "07700900106", "omar.farouk@example.com", "Glasgow"),
    ("C007", "Emily", "Watson", "07700900107", "emily.watson@example.com", "York"),
    ("C008", "Yusuf", "Alami", "07700900108", "yusuf.alami@example.com", "Birmingham"),
    ("C009", "Grace", "Lee", "07700900109", "grace.lee@example.com", "Oxford"),
    ("C010", "Noah", "Brown", "07700900110", "noah.brown@example.com", "Liverpool"),
]

# Each order: id, customer, ordered (days from today), payment, items, delivery.
# items: (product, category, quantity, unit_price, returnable)
# delivery: status + day offsets (shipped, expected, original, delivered) + last_location
ORDERS = [
    # C001 Sara: one order, on its way (the simple tracking case).
    ("SE-1042", "C001", -3, "Visa ending 4421",
     [("Wireless noise-cancelling headphones", "electronics", 1, 129.99, 1)],
     ("in_transit", -2, 2, 2, None, "Leeds sorting centre")),

    # C002 James: three orders, so "where is my order?" needs a follow-up question.
    ("SE-1051", "C002", -14, "Mastercard ending 9030",
     [("Bluetooth speaker", "electronics", 1, 59.99, 1)],
     ("delivered", -12, -10, -10, -10, "Delivered to front door")),
    ("SE-1052", "C002", -1, "Mastercard ending 9030",
     [("Oak desk lamp", "home", 1, 44.50, 1)],
     ("preparing", None, 4, 4, None, "ShopEasy warehouse")),
    ("SE-1053", "C002", -50, "Mastercard ending 9030",
     [("Trail running shoes", "sports", 1, 89.00, 1)],
     ("delivered", -47, -45, -45, -45, "Delivered to reception")),

    # C003 Amina: a late delivery, plus an older delivered order.
    ("SE-1061", "C003", -8, "PayPal",
     [("Cast iron cooking pot", "kitchen", 1, 64.00, 1)],
     ("delayed", -7, 2, -3, None, "Manchester depot, held due to high volume")),
    ("SE-1062", "C003", -18, "PayPal",
     [("Yoga mat", "sports", 1, 24.99, 1), ("Water bottle", "sports", 2, 9.99, 1)],
     ("delivered", -17, -15, -15, -15, "Delivered to neighbour at number 12")),

    # C004 Daniel: a lost package, plus a recent order.
    ("SE-1071", "C004", -14, "Visa ending 1187",
     [("Smart watch", "electronics", 1, 199.00, 1)],
     ("lost", -12, -9, -9, None, "Last scanned at London hub")),
    ("SE-1072", "C004", -5, "Visa ending 1187",
     [("Phone case", "electronics", 1, 15.99, 1)],
     ("delivered", -4, -3, -3, -3, "Delivered to parcel locker")),

    # C005 Laura: an item that can never be returned, plus a cancelled order.
    ("SE-1081", "C005", -7, "Visa ending 5560",
     [("Cotton boxer briefs, 3-pack", "underwear", 1, 19.99, 0),
      ("Linen shirt", "clothing", 1, 34.99, 1)],
     ("delivered", -6, -5, -5, -5, "Delivered to front door")),
    ("SE-1082", "C005", -9, "Visa ending 5560",
     [("Winter coat", "clothing", 1, 120.00, 1)],
     ("cancelled", None, None, None, None, None)),

    # C006 Omar: out for delivery today, software (not returnable), one in transit.
    ("SE-1091", "C006", -4, "Amex ending 3002",
     [("Coffee grinder", "kitchen", 1, 49.99, 1)],
     ("out_for_delivery", -2, 0, 0, None, "With the driver in Glasgow")),
    ("SE-1092", "C006", -22, "Amex ending 3002",
     [("Photo editing software licence", "software", 1, 79.00, 0)],
     ("delivered", -21, -20, -20, -20, "Sent by email")),
    ("SE-1093", "C006", -2, "Amex ending 3002",
     [("Desk organiser", "office", 1, 18.50, 1)],
     ("in_transit", -1, 3, 3, None, "Edinburgh hub")),

    # C007 Emily: recent delivery, one in transit, one still being prepared.
    ("SE-1101", "C007", -4, "Visa ending 7714",
     [("Ceramic plant pot", "home", 2, 14.00, 1)],
     ("delivered", -3, -2, -2, -2, "Delivered to front door")),
    ("SE-1102", "C007", -3, "Visa ending 7714",
     [("Throw blanket", "home", 1, 39.00, 1)],
     ("in_transit", -2, 1, 1, None, "York delivery station")),
    ("SE-1103", "C007", 0, "Visa ending 7714",
     [("Scented candle set", "home", 1, 22.00, 1)],
     ("preparing", None, 5, 5, None, "ShopEasy warehouse")),

    # C008 Yusuf: being prepared, plus one delivered too long ago to return.
    ("SE-1111", "C008", -1, "Mastercard ending 2268",
     [("Gaming keyboard", "electronics", 1, 89.99, 1)],
     ("preparing", None, 4, 4, None, "ShopEasy warehouse")),
    ("SE-1112", "C008", -43, "Mastercard ending 2268",
     [("Backpack", "travel", 1, 55.00, 1)],
     ("delivered", -42, -40, -40, -40, "Delivered to front door")),

    # C009 Grace: just inside and just outside the 30-day return window.
    ("SE-1121", "C009", -31, "PayPal",
     [("Electric kettle", "kitchen", 1, 34.99, 1)],
     ("delivered", -30, -28, -28, -28, "Delivered to front door")),
    ("SE-1122", "C009", -34, "PayPal",
     [("Gift card, 50 pounds", "gift_card", 1, 50.00, 0)],
     ("delivered", -33, -31, -31, -31, "Sent by email")),
    ("SE-1123", "C009", -2, "PayPal",
     [("Reading glasses", "accessories", 1, 25.00, 1)],
     ("out_for_delivery", -1, 0, 0, None, "With the driver in Oxford")),

    # C010 Noah: many orders of every kind.
    ("SE-1131", "C010", -63, "Visa ending 8890",
     [("Bike helmet", "sports", 1, 45.00, 1)],
     ("delivered", -62, -60, -60, -60, "Delivered to front door")),
    ("SE-1132", "C010", -3, "Visa ending 8890",
     [("Bike lights", "sports", 1, 19.99, 1)],
     ("in_transit", -2, 2, 2, None, "Liverpool sorting centre")),
    ("SE-1133", "C010", -6, "Visa ending 8890",
     [("Personalised mug", "personalised", 1, 12.99, 0)],
     ("cancelled", None, None, None, None, None)),
    ("SE-1134", "C010", -9, "Visa ending 8890",
     [("Cycling gloves", "sports", 1, 21.00, 1)],
     ("delivered", -8, -7, -7, -7, "Delivered to front door")),
]

ORDER_STATUS_FOR_DELIVERY = {
    "preparing": "processing",
    "in_transit": "shipped",
    "out_for_delivery": "shipped",
    "delayed": "shipped",
    "lost": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
}

CARRIERS = ["Royal Parcel", "SwiftShip"]


def last_update_offset(status: str, ordered: int, shipped: int | None, delivered: int | None) -> int:
    """Day of the last tracking update, counted from today."""
    if status == "delivered":
        return delivered
    if status == "lost":
        return shipped + 3  # the parcel stopped moving 3 days after it shipped
    if status in {"preparing", "cancelled"}:
        return ordered
    return 0  # still moving: updated today

RETURN_POLICY = [
    ("window", f"Most items can be returned within {RETURN_WINDOW_DAYS} days of delivery. "
               "After that, we can't accept the return."),
    ("condition", "Items must be unused and in their original packaging, with all labels attached."),
    ("non_returnable", "Some items can never be returned: underwear, software and digital licences, "
                       "gift cards, and personalised items."),
    ("how_to_return", "We email the customer a free prepaid return label. They drop the parcel at any "
                      "Royal Parcel point within 14 days of receiving the label."),
    ("refunds", "Refunds go back to the original payment method within 5 to 7 working days after we "
                "receive the item. Refunds are always approved by a member of our team."),
    ("exchanges", "We don't do direct exchanges. The customer returns the item and places a new order."),
    ("damaged_items", "Damaged or wrong items must be reported within 7 days of delivery. We then offer "
                      "a replacement or a full refund, and the customer doesn't pay for the return."),
    ("cancelled_orders", "Cancelled orders are refunded automatically within 3 working days."),
]

FAQ = [
    ("How much does delivery cost?",
     "Standard delivery costs 3 pounds 99 and is free on orders over 40 pounds. Next-day delivery costs 6 pounds 99.",
     "delivery cost shipping price free postage fee"),
    ("How long does delivery take?",
     "Standard delivery takes 2 to 4 working days. Next-day delivery arrives the next working day if you order before 8 pm.",
     "delivery time how long days arrive shipping speed next-day"),
    ("Do you deliver outside the UK?",
     "Not yet. We only deliver to addresses in the United Kingdom.",
     "international abroad outside uk country overseas ship"),
    ("Can I change my delivery address?",
     "You can change the address while the order is still being prepared. Once it has shipped, we can't change it.",
     "change address delivery address wrong address move"),
    ("Can I cancel my order?",
     "You can cancel an order for free while it is still being prepared. After it ships, you can return it instead.",
     "cancel cancellation stop order"),
    ("Which payment methods do you accept?",
     "We accept Visa, Mastercard, American Express and PayPal.",
     "payment pay card paypal visa mastercard amex methods"),
    ("How can I track my order?",
     "Every shipped order has a tracking number in the confirmation email. You can also ask us and we'll check it for you.",
     "track tracking where parcel number"),
    ("Do you offer gift wrapping?",
     "Yes, gift wrapping costs 2 pounds 50 per item and can be added at checkout.",
     "gift wrap wrapping present"),
    ("When is customer support open?",
     "Our phone support is open every day from 8 am to 8 pm.",
     "opening hours open support time contact when"),
    ("I forgot my password. What can I do?",
     "Use the Forgot password link on the sign-in page. We'll email you a link to set a new one.",
     "password forgot reset login sign in account"),
    ("Do you price match?",
     "No, we don't match prices from other shops.",
     "price match cheaper competitor"),
    ("Do you have a student discount?",
     "Yes. Students get 10 percent off after verifying their student email in their account.",
     "student discount offer code promo"),
    ("How do I use a gift card?",
     "Enter the gift card code at checkout. Gift cards are valid for 2 years and can't be exchanged for cash.",
     "gift card voucher code use balance"),
    ("How do I contact you by email?",
     "You can email help at shopeasy dot example and we reply within one working day.",
     "email contact write message"),
]


def build_database(path: Path | str | None = None, today: date | None = None) -> Path:
    """Delete any old database at ``path`` and build a fresh one."""
    db_path = Path(path) if path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    today = today or date.today()

    def day(offset: int | None) -> str | None:
        return None if offset is None else (today + timedelta(days=offset)).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", CUSTOMERS)

            for index, (order_id, customer_id, ordered, payment, items, delivery) in enumerate(ORDERS):
                status, shipped, expected, original, delivered, location = delivery
                total = round(sum(qty * price for _, _, qty, price, _ in items), 2)
                conn.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, customer_id, day(ordered), ORDER_STATUS_FOR_DELIVERY[status], total, payment),
                )
                conn.executemany(
                    "INSERT INTO order_items (order_id, product, category, quantity, unit_price, returnable)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    [(order_id, *item) for item in items],
                )
                shipped_at_all = shipped is not None
                conn.execute(
                    "INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        order_id,
                        CARRIERS[index % len(CARRIERS)] if shipped_at_all else None,
                        f"RP{order_id[3:]}{customer_id[1:]}GB" if shipped_at_all else None,
                        status,
                        day(shipped),
                        day(expected),
                        day(original),
                        day(delivered),
                        location,
                        day(last_update_offset(status, ordered, shipped, delivered)),
                    ),
                )

            conn.executemany("INSERT INTO return_policy VALUES (?, ?)", RETURN_POLICY)
            conn.executemany("INSERT INTO faq (question, answer, keywords) VALUES (?, ?, ?)", FAQ)
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Built {build_database(target)}")
