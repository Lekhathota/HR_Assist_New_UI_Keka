-- Recruitment Assist — PostgreSQL schema
-- Run: psql "$DATABASE_URL" -f database/schema.sql
-- Then apply stored procedures: psql "$DATABASE_URL" -f database/procedures.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(255) DEFAULT '',
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE job_descriptions (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL DEFAULT '',
    department VARCHAR(255) DEFAULT '',
    location VARCHAR(255) DEFAULT '',
    experience_required TEXT DEFAULT '',
    skills TEXT[] DEFAULT '{}',
    responsibilities TEXT[] DEFAULT '{}',
    structured_data JSONB DEFAULT '{}'::jsonb,
    raw_text TEXT DEFAULT '',
    file_name VARCHAR(500) DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE candidates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL DEFAULT '',
    email VARCHAR(255) DEFAULT '',
    phone VARCHAR(64) DEFAULT '',
    applied_roles TEXT[] DEFAULT '{}',
    structured_data JSONB DEFAULT '{}'::jsonb,
    match_score INTEGER DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending',
    screening_summary TEXT DEFAULT '',
    rejection_reason TEXT DEFAULT '',
    hiring_stage VARCHAR(100) DEFAULT '',
    resume_file VARCHAR(500) DEFAULT '',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    jd_id INTEGER REFERENCES job_descriptions(id) ON DELETE SET NULL
);

CREATE TABLE comparisons (
    id SERIAL PRIMARY KEY,
    jd_id INTEGER NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    match_score INTEGER DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending',
    strengths TEXT[] DEFAULT '{}',
    gaps TEXT[] DEFAULT '{}',
    recommendation TEXT DEFAULT '',
    failure_reason TEXT DEFAULT '',
    comparison_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (jd_id, candidate_id)
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    action VARCHAR(200) NOT NULL,
    username VARCHAR(80) DEFAULT '',
    details TEXT DEFAULT '',
    jd_id INTEGER REFERENCES job_descriptions(id) ON DELETE SET NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comparisons_jd_candidate ON comparisons (jd_id, candidate_id);
CREATE INDEX idx_candidates_status ON candidates (status);
CREATE INDEX idx_job_descriptions_status_created ON job_descriptions (status, created_at DESC);
CREATE INDEX idx_candidates_jd_id ON candidates (jd_id);

-- Survives Flask restarts (in-memory tokens alone caused 401 after reload)
CREATE TABLE user_session_tokens (
    token VARCHAR(128) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_user_session_tokens_user_id ON user_session_tokens(user_id);

-- Default admin: username admin / password admin123 (Werkzeug; scrypt or pbkdf2)
INSERT INTO users (username, password, email, role) VALUES (
    'admin',
    'scrypt:32768:8:1$cbejUzKzNw9pGRTt$b1ac7731b854dcf15515a837d245d1e28c36c621b16b5be61bf65f6340526e7cde90be6a48ea4b56777a130da86e4de507bb12f260956b896d8b7c47e727193d',
    'admin@localhost',
    'admin'
) ON CONFLICT (username) DO NOTHING;
