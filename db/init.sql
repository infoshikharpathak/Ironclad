-- Accounts
CREATE TABLE accounts (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL CHECK (account_type IN ('checking', 'savings')),
    balance         NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    currency        TEXT NOT NULL DEFAULT 'USD',
    created_at      TIMESTAMPTZ DEFAULT now(),
    is_demo         BOOLEAN DEFAULT true
);
CREATE INDEX idx_accounts_user ON accounts(user_id);

-- Transactions (transfers between accounts)
CREATE TABLE transactions (
    id              TEXT PRIMARY KEY,
    from_account    TEXT NOT NULL REFERENCES accounts(id),
    to_account      TEXT NOT NULL REFERENCES accounts(id),
    amount          NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    status          TEXT NOT NULL DEFAULT 'pending_otp'
                    CHECK (status IN ('pending_otp', 'confirmed', 'cancelled', 'failed')),
    description     TEXT DEFAULT '',
    otp_hash        TEXT,
    otp_attempts    INT DEFAULT 0,
    otp_expires_at  TIMESTAMPTZ,
    idempotency_key TEXT UNIQUE,
    initiated_by    TEXT NOT NULL DEFAULT 'user',
    user_id         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    confirmed_at    TIMESTAMPTZ
);
CREATE INDEX idx_transactions_user ON transactions(user_id, created_at DESC);
CREATE INDEX idx_transactions_status ON transactions(status) WHERE status = 'pending_otp';

-- Seed function: creates demo accounts for a user
CREATE OR REPLACE FUNCTION seed_demo_user(p_user_id TEXT) RETURNS void AS $$
BEGIN
    INSERT INTO accounts (id, user_id, name, account_type, balance)
    VALUES
        ('acc_' || p_user_id || '_checking', p_user_id, 'Checking', 'checking', 10000.00),
        ('acc_' || p_user_id || '_savings', p_user_id, 'Savings', 'savings', 5000.00)
    ON CONFLICT (id) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- Seed a default demo user
SELECT seed_demo_user('demo_user');
