-- ShopEasy: a made-up online shop for the support agent.

CREATE TABLE customers (
    id          TEXT PRIMARY KEY,          -- C001
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,      -- digits only, e.g. 07700900101
    email       TEXT NOT NULL,
    city        TEXT NOT NULL
);

CREATE TABLE orders (
    id           TEXT PRIMARY KEY,         -- SE-1042
    customer_id  TEXT NOT NULL REFERENCES customers(id),
    order_date   TEXT NOT NULL,            -- ISO date
    status       TEXT NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled')),
    total        REAL NOT NULL,            -- GBP
    payment      TEXT NOT NULL             -- e.g. "Visa ending 4421"
);

CREATE TABLE order_items (
    id           INTEGER PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(id),
    product      TEXT NOT NULL,
    category     TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    unit_price   REAL NOT NULL,
    returnable   INTEGER NOT NULL          -- 1 = can be returned, 0 = never
);

CREATE TABLE deliveries (
    order_id        TEXT PRIMARY KEY REFERENCES orders(id),
    carrier         TEXT,
    tracking_number TEXT,
    status          TEXT NOT NULL CHECK (status IN (
                        'preparing', 'in_transit', 'out_for_delivery',
                        'delivered', 'delayed', 'lost', 'cancelled')),
    shipped_date    TEXT,
    expected_date   TEXT,                  -- the date we promise now
    original_date   TEXT,                  -- the first promised date (differs when late)
    delivered_date  TEXT,
    last_location   TEXT,
    last_update     TEXT
);

CREATE TABLE return_policy (
    topic  TEXT PRIMARY KEY,
    text   TEXT NOT NULL
);

CREATE TABLE faq (
    id        INTEGER PRIMARY KEY,
    question  TEXT NOT NULL,
    answer    TEXT NOT NULL,
    keywords  TEXT NOT NULL                -- space-separated search words
);

CREATE TABLE tickets (
    id           INTEGER PRIMARY KEY,
    number       INTEGER NOT NULL UNIQUE,  -- the short number we say to the customer
    customer_id  TEXT REFERENCES customers(id),
    order_id     TEXT,
    subject      TEXT NOT NULL,
    details      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',
    session_id   TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE handoffs (
    id           INTEGER PRIMARY KEY,
    customer_id  TEXT REFERENCES customers(id),
    reason       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'waiting',
    session_id   TEXT,
    created_at   TEXT NOT NULL
);
