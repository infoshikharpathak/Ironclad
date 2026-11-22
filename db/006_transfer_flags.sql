-- Output-scan flags on pending transfers and payment requests.
--
-- When Anvil blocks the banking assistant's reply, a transfer that turn
-- started is left pending (the block may be a false positive) and flagged,
-- so the OTP modal can warn the user before they approve it. Idempotent:
--   python -m app.cli migrate          (from bank-service/)
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS flagged_by_output_scan BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS flag_reason TEXT;
