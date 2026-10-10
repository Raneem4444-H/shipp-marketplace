-- SHIPP DEVELOPMENT RESET — reservation + quote foundation
-- Save locally as lakebase/migrations/011_reservation_quote_foundation_DEV.sql
-- Expected live precondition: shipp.reservations exists, contains ZERO rows,
-- and no dependent foreign keys/views; shipp.delivery_quotes does not exist.
-- REVIEW BEFORE EXECUTING. This changes only SHIPP reservation/quote objects.
-- DO NOT run the older incompatible 011/011a draft migrations afterward.
-- This is for a disposable development reservation table, NOT production.
BEGIN;
-- Serialize against any new writes while rechecking the zero-row condition.
LOCK TABLE shipp.reservations IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN IF EXISTS (
    SELECT 1
    FROM shipp.reservations
    LIMIT 1
) THEN RAISE EXCEPTION 'Refusing to reset: shipp.reservations contains records';
END IF;
IF to_regclass('shipp.delivery_quotes') IS NOT NULL THEN RAISE EXCEPTION 'Refusing to reset: shipp.delivery_quotes already exists';
END IF;
IF to_regclass('shipp.reservation_events') IS NOT NULL THEN RAISE EXCEPTION 'Refusing to reset: shipp.reservation_events already exists';
END IF;
END $$;
-- RESTRICT prevents silently removing dependent foreign keys or views.
-- Indexes attached to the OLD reservations table disappear with that table.
DROP TABLE shipp.reservations RESTRICT;
CREATE TABLE shipp.reservations (
    reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id VARCHAR(50) NOT NULL REFERENCES shipp.listings(listing_id) ON DELETE RESTRICT,
    request_id VARCHAR(50) NOT NULL REFERENCES shipp.requests(request_id) ON DELETE RESTRICT,
    requester_id VARCHAR(50) NOT NULL REFERENCES shipp.users(user_id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'HELD' CONSTRAINT chk_shipp_reservation_status CHECK (
        status IN (
            'HELD',
            'CONFIRMED',
            'DECLINED',
            'CANCELLED',
            'EXPIRED',
            'COMPLETED'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    hold_expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
    donor_confirmed_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_shipp_hold_after_creation CHECK (hold_expires_at > created_at)
);
-- Critical concurrency invariant: only ONE HELD/CONFIRMED reservation per listing.
CREATE UNIQUE INDEX ux_shipp_one_active_reservation_per_listing ON shipp.reservations (listing_id)
WHERE status IN ('HELD', 'CONFIRMED');
CREATE INDEX ix_shipp_reservations_requester ON shipp.reservations (requester_id, created_at DESC);
CREATE INDEX ix_shipp_reservations_request ON shipp.reservations (request_id);
CREATE INDEX ix_shipp_reservations_expiry ON shipp.reservations (hold_expires_at)
WHERE status = 'HELD';
-- Preserve an append-only audit of reservation status decisions.
CREATE TABLE shipp.reservation_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES shipp.reservations(reservation_id) ON DELETE RESTRICT,
    actor_user_id VARCHAR(50) REFERENCES shipp.users(user_id) ON DELETE RESTRICT,
    actor_type VARCHAR(20) NOT NULL CHECK (
        actor_type IN ('SYSTEM', 'DONOR', 'REQUESTER', 'ADMIN')
    ),
    event_type VARCHAR(20) NOT NULL CHECK (
        event_type IN (
            'HELD',
            'CONFIRMED',
            'DECLINED',
            'CANCELLED',
            'EXPIRED',
            'COMPLETED'
        )
    ),
    note TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_shipp_reservation_events_timeline ON shipp.reservation_events (reservation_id, occurred_at, event_id);
-- Route quotation: duration in whole SECONDS, distance in whole METERS.
-- $5.00 for the first 900 seconds; $2.00 per additional STARTED 900 seconds.
-- The provider's response must be validated by trusted server code first.
CREATE TABLE shipp.delivery_quotes (
    quote_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES shipp.reservations(reservation_id) ON DELETE RESTRICT,
    pickup_lat NUMERIC(9, 6) NOT NULL CHECK (
        pickup_lat BETWEEN -90 AND 90
    ),
    pickup_lon NUMERIC(9, 6) NOT NULL CHECK (
        pickup_lon BETWEEN -180 AND 180
    ),
    dropoff_lat NUMERIC(9, 6) NOT NULL CHECK (
        dropoff_lat BETWEEN -90 AND 90
    ),
    dropoff_lon NUMERIC(9, 6) NOT NULL CHECK (
        dropoff_lon BETWEEN -180 AND 180
    ),
    distance_meters INTEGER NOT NULL CHECK (distance_meters >= 0),
    duration_seconds INTEGER NOT NULL CHECK (
        duration_seconds BETWEEN 1 AND 86400
    ),
    routing_provider VARCHAR(20) NOT NULL DEFAULT 'ORS' CHECK (routing_provider = 'ORS'),
    currency CHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    pricing_version VARCHAR(30) NOT NULL DEFAULT 'USD_V1_5_2_15' CHECK (pricing_version = 'USD_V1_5_2_15'),
    extra_intervals INTEGER GENERATED ALWAYS AS (
        (GREATEST(duration_seconds - 900, 0) + 899) / 900
    ) STORED,
    total_fee_cents INTEGER GENERATED ALWAYS AS (
        500 + 200 * (
            (GREATEST(duration_seconds - 900, 0) + 899) / 900
        )
    ) STORED,
    status VARCHAR(20) NOT NULL DEFAULT 'OFFERED' CHECK (
        status IN ('OFFERED', 'ACCEPTED', 'EXPIRED', 'SUPERSEDED')
    ),
    quoted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '15 minutes'),
    accepted_at TIMESTAMPTZ,
    CHECK (valid_until > quoted_at),
    UNIQUE (reservation_id, quote_id),
    UNIQUE (quote_id, total_fee_cents)
);
CREATE UNIQUE INDEX ux_shipp_active_quote_per_reservation ON shipp.delivery_quotes (reservation_id)
WHERE status IN ('OFFERED', 'ACCEPTED');
COMMIT;
-- Read-only checks after COMMIT (these do not create reservation records):
SELECT to_regclass('shipp.reservations') AS reservations,
    to_regclass('shipp.reservation_events') AS reservation_events,
    to_regclass('shipp.delivery_quotes') AS delivery_quotes;
SELECT column_name,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema = 'shipp'
    AND table_name = 'delivery_quotes'
    AND column_name IN ('extra_intervals', 'total_fee_cents')
ORDER BY column_name;
SELECT duration_seconds,
    500 + 200 * (
        (GREATEST(duration_seconds - 900, 0) + 899) / 900
    ) AS expected_fee_cents
FROM (
        VALUES (900),
            (901),
            (1800),
            (1801),
            (2280)
    ) AS samples(duration_seconds);
-- IMPORTANT: Expiration is NOT automatic. A trusted service must transition
-- old HELD rows to EXPIRED before a new hold can be granted. App endpoints
-- must verify requester role/ownership and serialize concurrent claims.
-- Lakebase CDF replication and app grants need separate review after reset.