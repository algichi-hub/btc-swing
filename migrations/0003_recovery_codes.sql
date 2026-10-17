-- F4: Recovery codes, Preview-only additive schema. Never modify 0001 checksum.
CREATE TABLE IF NOT EXISTS auth_recovery_codes (
    code_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_recovery_codes_user
  ON auth_recovery_codes (user_id, used_at);
