-- Synthetic delivery platform database schema
-- Demonstrates: shared tables, cross-boundary FKs, fat tables, lifecycle timestamps
-- This schema represents a 12-year-old delivery platform with accumulated coupling

-- ═══════════════════════════════════════════════════════════
-- SHIPMENT SCHEMA (owned by Fulfilment Squad / svc_shipment)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE orders (
    order_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buyer_id        UUID NOT NULL,       -- references customers.customer_id (cross-boundary FK)
    buyer_name      VARCHAR(200),
    buyer_email     VARCHAR(200),
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
        -- lifecycle: draft → placed → confirmed → picking → packed → shipped → in_transit → delivered → cancelled → returned
    warehouse_id    UUID,                -- references warehouses.warehouse_id (cross-boundary FK)
    warehouse_name  VARCHAR(200),
    carrier_id      UUID,                -- references carriers.carrier_id (cross-boundary FK)
    carrier_name    VARCHAR(200),
    tracking_number VARCHAR(100),
    invoice_id      UUID,                -- references invoices.invoice_id (cross-boundary FK)
    invoice_number  VARCHAR(50),
    payment_method  VARCHAR(50),
    payment_status  VARCHAR(50),
    shipping_address_line1  VARCHAR(200),
    shipping_address_city   VARCHAR(100),
    shipping_address_postal VARCHAR(20),
    shipping_address_country VARCHAR(10),
    billing_address_line1   VARCHAR(200),
    billing_address_city    VARCHAR(100),
    billing_address_postal  VARCHAR(20),
    billing_address_country VARCHAR(10),
    subtotal        DECIMAL(12,2),
    tax_amount      DECIMAL(12,2),
    shipping_cost   DECIMAL(12,2),
    total_amount    DECIMAL(12,2),
    currency        VARCHAR(3) DEFAULT 'EUR',
    notes           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at    TIMESTAMP WITH TIME ZONE,    -- implicit domain event: OrderConfirmed
    shipped_at      TIMESTAMP WITH TIME ZONE,    -- implicit domain event: OrderShipped
    delivered_at    TIMESTAMP WITH TIME ZONE,    -- implicit domain event: OrderDelivered
    cancelled_at    TIMESTAMP WITH TIME ZONE,    -- implicit domain event: OrderCancelled
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- 31 columns — FAT TABLE signal (god entity at persistence layer)

CREATE TABLE order_lines (
    line_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(order_id),
    product_id      UUID NOT NULL,
    product_name    VARCHAR(200),
    sku             VARCHAR(50),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      DECIMAL(12,2) NOT NULL,
    discount        DECIMAL(12,2) DEFAULT 0,
    line_total      DECIMAL(12,2),
    warehouse_id    UUID,               -- which warehouse fulfills this line
    stock_status    VARCHAR(50)
);

-- ═══════════════════════════════════════════════════════════
-- CONSIGNEE SCHEMA (owned by Customer Domain Team / svc_consignee)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE customers (
    customer_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(200) NOT NULL UNIQUE,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    phone           VARCHAR(50),
    date_of_birth   DATE,
    segment         VARCHAR(50) DEFAULT 'new',
    loyalty_tier    VARCHAR(50) DEFAULT 'bronze',
    loyalty_points  INTEGER DEFAULT 0,
    marketing_consent BOOLEAN DEFAULT FALSE,
    language        VARCHAR(10) DEFAULT 'en',
    currency        VARCHAR(3) DEFAULT 'EUR',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at   TIMESTAMP WITH TIME ZONE,
    last_order_at   TIMESTAMP WITH TIME ZONE,
    total_orders    INTEGER DEFAULT 0,
    total_spent     DECIMAL(12,2) DEFAULT 0
);

CREATE TABLE customer_addresses (
    address_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(customer_id),
    label           VARCHAR(50),         -- 'Home', 'Work', 'Partner'
    street_address  VARCHAR(200) NOT NULL,
    apartment_unit  VARCHAR(50),
    city            VARCHAR(100) NOT NULL,
    state_province  VARCHAR(100),
    zip_code        VARCHAR(20) NOT NULL,
    country_code    VARCHAR(2) NOT NULL,
    is_default      BOOLEAN DEFAULT FALSE,
    phone_number    VARCHAR(50)
);

-- ═══════════════════════════════════════════════════════════
-- INVENTORY SCHEMA (owned by Supply Chain Platform Team / svc_inventory)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE warehouses (
    warehouse_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    type            VARCHAR(50),
    addr            VARCHAR(200),
    city            VARCHAR(100),
    region          VARCHAR(100),
    zip             VARCHAR(20),
    country         VARCHAR(2),
    capacity        INTEGER,
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE stock_levels (
    sku             VARCHAR(50) NOT NULL,
    warehouse_id    UUID NOT NULL REFERENCES warehouses(warehouse_id),
    quantity_on_hand    INTEGER DEFAULT 0,
    quantity_reserved   INTEGER DEFAULT 0,
    reorder_threshold   INTEGER DEFAULT 0,
    last_replenished    TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (sku, warehouse_id)
);

CREATE TABLE inventory_reserved (
    reservation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL,       -- references orders.order_id (cross-boundary)
    user_id         UUID,                -- references customers.customer_id (cross-boundary, wrong name)
    sku             VARCHAR(50) NOT NULL,
    quantity        INTEGER NOT NULL,
    warehouse_id    UUID NOT NULL REFERENCES warehouses(warehouse_id),
    status          VARCHAR(50) DEFAULT 'active',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at      TIMESTAMP WITH TIME ZONE
);

-- ═══════════════════════════════════════════════════════════
-- CARRIER SCHEMA (owned by Carrier Platform Team / svc_carrier)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE carriers (
    carrier_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    code            VARCHAR(20),
    is_active       BOOLEAN DEFAULT TRUE,
    average_delivery_days INTEGER
);

CREATE TABLE shipments (
    shipment_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL,       -- references orders.order_id (cross-boundary)
    recipient_id    UUID,                -- references customers.customer_id (cross-boundary, different name)
    recipient_name  VARCHAR(200),
    carrier_id      UUID REFERENCES carriers(carrier_id),
    tracking_number VARCHAR(100),
    status          VARCHAR(50) DEFAULT 'created',
    delivery_street VARCHAR(200),
    delivery_city   VARCHAR(100),
    delivery_postal VARCHAR(20),
    delivery_country VARCHAR(2),
    weight          DECIMAL(8,2),
    package_count   INTEGER DEFAULT 1,
    shipping_cost   DECIMAL(12,2),
    estimated_delivery DATE,
    actual_delivery    DATE,
    signed_by       VARCHAR(200),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE shipment_status (
    id              SERIAL PRIMARY KEY,
    shipment_id     UUID NOT NULL,       -- references shipments.shipment_id
    status          VARCHAR(50) NOT NULL,
    description     TEXT,
    location_city   VARCHAR(100),
    location_country VARCHAR(2),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════
-- INVOICING SCHEMA (owned by Finance Platform Team / svc_invoicing)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE invoices (
    invoice_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number  VARCHAR(50) NOT NULL UNIQUE,
    order_id        UUID NOT NULL,       -- references orders.order_id (cross-boundary)
    account_id      UUID NOT NULL,       -- references customers.customer_id (cross-boundary, different name)
    account_name    VARCHAR(200),
    account_email   VARCHAR(200),
    billing_full_name   VARCHAR(200),
    billing_company     VARCHAR(200),
    billing_address1    VARCHAR(200),
    billing_city        VARCHAR(100),
    billing_postal      VARCHAR(20),
    billing_country     VARCHAR(2),
    billing_vat         VARCHAR(50),
    subtotal        DECIMAL(12,2),
    tax_rate        DECIMAL(5,4),
    tax_amount      DECIMAL(12,2),
    shipping_amount DECIMAL(12,2),
    total_amount    DECIMAL(12,2),
    currency        VARCHAR(3) DEFAULT 'EUR',
    status          VARCHAR(50) DEFAULT 'draft',
    issued_at       TIMESTAMP WITH TIME ZONE,
    due_date        DATE,
    paid_at         TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE payments (
    payment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL,
    account_id      UUID NOT NULL,
    method          VARCHAR(50) NOT NULL,
    amount          DECIMAL(12,2) NOT NULL,
    currency        VARCHAR(3) DEFAULT 'EUR',
    status          VARCHAR(50) DEFAULT 'pending',
    gateway_ref     VARCHAR(200),
    card_last4      VARCHAR(4),
    risk_score      DECIMAL(5,2),
    processed_at    TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE payment_ledger (
    ledger_id       SERIAL PRIMARY KEY,
    payment_id      UUID REFERENCES payments(payment_id),
    entry_type      VARCHAR(50) NOT NULL,  -- credit, debit, refund
    amount          DECIMAL(12,2) NOT NULL,
    currency        VARCHAR(3) DEFAULT 'EUR',
    description     TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE refunds (
    refund_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id      UUID NOT NULL REFERENCES payments(payment_id),
    order_id        UUID NOT NULL,
    account_id      UUID NOT NULL,
    amount          DECIMAL(12,2) NOT NULL,
    reason          VARCHAR(50),
    method          VARCHAR(50),
    status          VARCHAR(50) DEFAULT 'pending',
    approved_by     VARCHAR(200),
    processed_at    TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════
-- INDEXES (fossils of coupling decisions)
-- ═══════════════════════════════════════════════════════════

-- On orders table: indexes for cross-service queries
CREATE INDEX idx_orders_buyer_id ON orders(buyer_id);           -- Consignee lookups
CREATE INDEX idx_orders_warehouse_id ON orders(warehouse_id);   -- Inventory lookups
CREATE INDEX idx_orders_carrier_id ON orders(carrier_id);       -- Carrier lookups
CREATE INDEX idx_orders_invoice_id ON orders(invoice_id);       -- Invoicing lookups
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);

-- On customer_addresses: accessed by 3 services
CREATE INDEX idx_customer_addresses_customer_id ON customer_addresses(customer_id);

-- On inventory_reserved: dual-write table
CREATE INDEX idx_inventory_reserved_order_id ON inventory_reserved(order_id);
CREATE INDEX idx_inventory_reserved_sku ON inventory_reserved(sku, warehouse_id);

-- On shipments: cross-boundary queries
CREATE INDEX idx_shipments_order_id ON shipments(order_id);
CREATE INDEX idx_shipments_recipient_id ON shipments(recipient_id);
CREATE INDEX idx_shipments_carrier_id ON shipments(carrier_id);
