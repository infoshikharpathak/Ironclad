-- Merchant registry and merchant payment requests.
--
-- Runs after init.sql on a fresh database (docker-compose mounts them as
-- 01-init.sql and 02-merchants.sql; initdb runs them in name order), and is
-- safe to re-run on an existing one:
--   python -m app.cli migrate          (from bank-service/)
-- Every statement is idempotent.

-- Settlement accounts: where each merchant's payments land. Not public, so
-- they don't show in the directory. A payment request's payee is always the
-- merchant's settlement account from this registry, never the request body.
INSERT INTO accounts (id, user_id, name, account_type, balance, owner_name, is_public)
VALUES
    ('acc_merchant_fooddash_settlement',  'merchant:fooddash',  'FoodDash settlement',  'checking', 0.00, 'FoodDash',  false),
    ('acc_merchant_quickmart_settlement', 'merchant:quickmart', 'QuickMart settlement', 'checking', 0.00, 'QuickMart', false)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id             TEXT PRIMARY KEY,
    display_name            TEXT NOT NULL,
    settlement_account_id   TEXT NOT NULL REFERENCES accounts(id),
    -- SHA-256 hex of the merchant's mk_ key. NULL until a key is issued
    -- (python -m app.cli merchants issue-key <merchant_id>).
    api_key_hash            TEXT UNIQUE,
    max_payment_amount      NUMERIC(12,2) NOT NULL CHECK (max_payment_amount > 0),
    agent_payments_allowed  BOOLEAN NOT NULL DEFAULT false,
    status                  TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at              TIMESTAMPTZ DEFAULT now()
);

INSERT INTO merchants (merchant_id, display_name, settlement_account_id, max_payment_amount, agent_payments_allowed, status)
VALUES
    ('fooddash',  'FoodDash',  'acc_merchant_fooddash_settlement',  200.00, true,  'active'),
    ('quickmart', 'QuickMart', 'acc_merchant_quickmart_settlement', 500.00, false, 'active')
ON CONFLICT (merchant_id) DO NOTHING;

-- Payment requests are transactions with a merchant attached.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_id  TEXT REFERENCES merchants(merchant_id);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS order_ref    TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS channel      TEXT;
-- SHA-256 of the request body, so a replayed idempotency key with a
-- different body can be told apart (409) from a true replay.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS request_hash TEXT;
-- Why a transfer ended up cancelled: expired | otp_max_attempts | declined.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS closed_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'transactions_channel_check') THEN
        ALTER TABLE transactions ADD CONSTRAINT transactions_channel_check
            CHECK (channel IS NULL OR channel IN ('checkout', 'agent'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_transactions_merchant ON transactions(merchant_id, created_at DESC)
    WHERE merchant_id IS NOT NULL;
