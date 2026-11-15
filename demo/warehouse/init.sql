-- Demo warehouse for ObservaKit screenshots and the walkthrough video.
-- customers is deliberately stale; orders is fresh. order_items is complete.

CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL,
    segment     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Customer 2 intentionally duplicates customer 1's email so the
-- "No duplicate customer emails" quality check has a real failure.
INSERT INTO customers (email, segment, created_at, updated_at)
SELECT
    CASE WHEN i = 2 THEN 'customer1@example.com' ELSE 'customer' || i || '@example.com' END,
    (ARRAY['smb', 'midmarket', 'enterprise'])[1 + (i % 3)],
    now() - interval '30 days',
    now() - interval '6 days'
FROM generate_series(1, 50) AS i;

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status      TEXT NOT NULL,
    amount      NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

INSERT INTO orders (customer_id, status, amount, created_at, updated_at)
SELECT
    1 + (i % 50),
    (ARRAY['pending', 'confirmed', 'shipped', 'delivered', 'cancelled'])[1 + (i % 5)],
    round((20 + (i % 300))::numeric, 2),
    now() - (interval '1 day' * (i % 7)) - interval '2 hours',
    now() - (interval '1 day' * (i % 7)) - interval '1 hour'
FROM generate_series(1, 500) AS i;

CREATE TABLE order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    sku         TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(10, 2) NOT NULL
);

INSERT INTO order_items (order_id, sku, quantity, unit_price)
SELECT
    1 + (i % 500),
    'SKU-' || (1000 + (i % 40)),
    1 + (i % 4),
    round((5 + (i % 90))::numeric, 2)
FROM generate_series(1, 1200) AS i;

CREATE INDEX idx_orders_updated_at ON orders (updated_at);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
