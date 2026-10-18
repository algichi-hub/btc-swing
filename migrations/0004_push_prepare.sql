-- F5-E0 PREPARATION ONLY. Do not apply until G3/G4 are GO and privileges reviewed.
-- No public endpoints or dispatcher are enabled by this migration.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint_hash CHAR(64) NOT NULL UNIQUE,
    endpoint_ciphertext BYTEA NOT NULL,
    p256dh_ciphertext BYTEA NOT NULL,
    auth_ciphertext BYTEA NOT NULL,
    device_label VARCHAR(100),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_active ON push_subscriptions(user_id,active);
CREATE TABLE IF NOT EXISTS push_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_key CHAR(64) NOT NULL UNIQUE,
    kind VARCHAR(50) NOT NULL,
    public_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(12) NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENT','FAILED','EXPIRED')),
    attempts SMALLINT NOT NULL DEFAULT 0 CHECK(attempts>=0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_push_outbox_due ON push_outbox(next_attempt_at,id)
  WHERE status='PENDING';
CREATE TABLE IF NOT EXISTS push_deliveries (
    event_id BIGINT NOT NULL REFERENCES push_outbox(id) ON DELETE CASCADE,
    subscription_id BIGINT NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
    state VARCHAR(12) NOT NULL DEFAULT 'PENDING'
      CHECK(state IN ('PENDING','SENT','FAILED','EXPIRED')),
    attempts SMALLINT NOT NULL DEFAULT 0,
    last_error_code VARCHAR(48),
    delivered_at TIMESTAMPTZ,
    PRIMARY KEY(event_id,subscription_id)
);
-- Store only encrypted endpoints/keys. Production encryption/key rotation and grants are G5 requirements.
