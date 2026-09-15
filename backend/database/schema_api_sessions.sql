-- Apply once on databases created before user_session_tokens existed:
--   psql "%DATABASE_URL%" -f database/schema_api_sessions.sql
-- (PowerShell: psql $env:DATABASE_URL -f database/schema_api_sessions.sql)

CREATE TABLE IF NOT EXISTS user_session_tokens (
    token VARCHAR(128) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_session_tokens_user_id ON user_session_tokens(user_id);
