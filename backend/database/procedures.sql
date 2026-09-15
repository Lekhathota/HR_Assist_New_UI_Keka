-- Recruitment Assist — PostgreSQL stored procedures for all writes.
-- Apply after schema.sql:  psql "$DATABASE_URL" -f database/procedures.sql

-- ── Job descriptions: create / patch / delete ───────────────────────────────

CREATE OR REPLACE PROCEDURE public.store_jd(
    OUT p_id integer,
    IN p_title text,
    IN p_department text,
    IN p_location text,
    IN p_experience_required text,
    IN p_skills text[],
    IN p_responsibilities text[],
    IN p_structured_data jsonb,
    IN p_raw_text text,
    IN p_file_name text,
    IN p_status text DEFAULT 'Active'::text
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO job_descriptions (
        title, department, location, experience_required, skills, responsibilities,
        structured_data, raw_text, file_name, status
    )
    VALUES (
        p_title, p_department, p_location, p_experience_required, p_skills, p_responsibilities,
        p_structured_data, p_raw_text, p_file_name, p_status
    )
    RETURNING id INTO p_id;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.update_jd(
    IN p_id integer,
    IN p_patch jsonb,
    OUT p_rows integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    UPDATE job_descriptions SET
        title = CASE WHEN p_patch ? 'title' THEN (p_patch->>'title')::varchar(500) ELSE title END,
        department = CASE WHEN p_patch ? 'department' THEN (p_patch->>'department')::varchar(255) ELSE department END,
        location = CASE WHEN p_patch ? 'location' THEN (p_patch->>'location')::varchar(255) ELSE location END,
        experience_required = CASE WHEN p_patch ? 'experience_required' THEN (p_patch->>'experience_required')::text ELSE experience_required END,
        skills = CASE WHEN p_patch ? 'skills' THEN
            COALESCE(ARRAY(SELECT jsonb_array_elements_text(p_patch->'skills')), ARRAY[]::text[])
            ELSE skills END,
        responsibilities = CASE WHEN p_patch ? 'responsibilities' THEN
            COALESCE(ARRAY(SELECT jsonb_array_elements_text(p_patch->'responsibilities')), ARRAY[]::text[])
            ELSE responsibilities END,
        structured_data = CASE WHEN p_patch ? 'structured_data' THEN (p_patch->'structured_data')::jsonb ELSE structured_data END,
        raw_text = CASE WHEN p_patch ? 'raw_text' THEN (p_patch->>'raw_text')::text ELSE raw_text END,
        file_name = CASE WHEN p_patch ? 'file_name' THEN (p_patch->>'file_name')::varchar(500) ELSE file_name END,
        status = CASE WHEN p_patch ? 'status' THEN (p_patch->>'status')::varchar(50) ELSE status END,
        updated_at = NOW()
    WHERE id = p_id;
    GET DIAGNOSTICS p_rows = ROW_COUNT;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.delete_jd(
    IN p_jd_id integer,
    OUT p_deleted boolean
)
LANGUAGE plpgsql
AS $procedure$
DECLARE
    n integer;
BEGIN
    UPDATE candidates SET jd_id = NULL WHERE jd_id = p_jd_id;
    DELETE FROM job_descriptions WHERE id = p_jd_id;
    GET DIAGNOSTICS n = ROW_COUNT;
    p_deleted := (n > 0);
END;
$procedure$;


-- ── Candidates: create / patch / delete ─────────────────────────────────────

CREATE OR REPLACE PROCEDURE public.store_candidate(
    OUT p_id integer,
    IN p_name text,
    IN p_email text,
    IN p_phone text,
    IN p_applied_roles text[],
    IN p_structured_data jsonb,
    IN p_match_score integer,
    IN p_status text,
    IN p_screening_summary text,
    IN p_rejection_reason text,
    IN p_hiring_stage text,
    IN p_resume_file text,
    IN p_jd_id integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO candidates (
        name, email, phone, applied_roles, structured_data, match_score, status,
        screening_summary, rejection_reason, hiring_stage, resume_file, jd_id
    )
    VALUES (
        p_name, p_email, p_phone, p_applied_roles, p_structured_data,
        p_match_score, p_status, p_screening_summary, p_rejection_reason,
        p_hiring_stage, p_resume_file, p_jd_id
    )
    RETURNING id INTO p_id;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.update_candidate(
    IN p_id integer,
    IN p_patch jsonb,
    OUT p_rows integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    UPDATE candidates SET
        name = CASE WHEN p_patch ? 'name' THEN (p_patch->>'name')::varchar(500) ELSE name END,
        email = CASE WHEN p_patch ? 'email' THEN (p_patch->>'email')::varchar(255) ELSE email END,
        phone = CASE WHEN p_patch ? 'phone' THEN (p_patch->>'phone')::varchar(64) ELSE phone END,
        applied_roles = CASE WHEN p_patch ? 'applied_roles' THEN
            COALESCE(ARRAY(SELECT jsonb_array_elements_text(p_patch->'applied_roles')), ARRAY[]::text[])
            ELSE applied_roles END,
        structured_data = CASE WHEN p_patch ? 'structured_data' THEN (p_patch->'structured_data')::jsonb ELSE structured_data END,
        match_score = CASE WHEN p_patch ? 'match_score' THEN (p_patch->>'match_score')::integer ELSE match_score END,
        status = CASE WHEN p_patch ? 'status' THEN (p_patch->>'status')::varchar(50) ELSE status END,
        screening_summary = CASE WHEN p_patch ? 'screening_summary' THEN (p_patch->>'screening_summary')::text ELSE screening_summary END,
        rejection_reason = CASE WHEN p_patch ? 'rejection_reason' THEN (p_patch->>'rejection_reason')::text ELSE rejection_reason END,
        hiring_stage = CASE WHEN p_patch ? 'hiring_stage' THEN (p_patch->>'hiring_stage')::varchar(100) ELSE hiring_stage END,
        resume_file = CASE WHEN p_patch ? 'resume_file' THEN (p_patch->>'resume_file')::varchar(500) ELSE resume_file END,
        jd_id = CASE
            WHEN NOT (p_patch ? 'jd_id') THEN jd_id
            WHEN p_patch->'jd_id' IS NULL OR jsonb_typeof(p_patch->'jd_id') = 'null' THEN NULL
            ELSE (p_patch->>'jd_id')::integer
        END
    WHERE id = p_id;
    GET DIAGNOSTICS p_rows = ROW_COUNT;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.delete_candidate(
    IN p_candidate_id integer,
    OUT p_deleted boolean
)
LANGUAGE plpgsql
AS $procedure$
DECLARE
    n integer;
BEGIN
    DELETE FROM comparisons WHERE candidate_id = p_candidate_id;
    DELETE FROM candidates WHERE id = p_candidate_id;
    GET DIAGNOSTICS n = ROW_COUNT;
    p_deleted := (n > 0);
END;
$procedure$;


-- ── Comparisons ───────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE public.upsert_comparison(
    OUT p_id integer,
    IN p_jd_id integer,
    IN p_candidate_id integer,
    IN p_match_score integer,
    IN p_status text,
    IN p_strengths text[],
    IN p_gaps text[],
    IN p_recommendation text,
    IN p_failure_reason text,
    IN p_comparison_date timestamptz
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO comparisons (
        jd_id, candidate_id, match_score, status, strengths, gaps, recommendation, failure_reason, comparison_date
    ) VALUES (
        p_jd_id, p_candidate_id, p_match_score, p_status, p_strengths, p_gaps, p_recommendation, p_failure_reason, p_comparison_date
    )
    ON CONFLICT (jd_id, candidate_id) DO UPDATE SET
        match_score = EXCLUDED.match_score,
        status = EXCLUDED.status,
        strengths = EXCLUDED.strengths,
        gaps = EXCLUDED.gaps,
        recommendation = EXCLUDED.recommendation,
        failure_reason = EXCLUDED.failure_reason,
        comparison_date = EXCLUDED.comparison_date
    RETURNING id INTO p_id;
END;
$procedure$;


-- ── Audit & users ─────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE public.insert_audit_log(
    IN p_action text,
    IN p_username text,
    IN p_details text,
    IN p_jd_id integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO audit_logs (action, username, details, jd_id)
    VALUES (p_action, COALESCE(p_username, ''), COALESCE(p_details, ''), p_jd_id);
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.update_user_email(
    IN p_user_id integer,
    IN p_email text,
    OUT p_updated boolean
)
LANGUAGE plpgsql
AS $procedure$
DECLARE
    n integer;
BEGIN
    UPDATE users SET email = p_email WHERE id = p_user_id;
    GET DIAGNOSTICS n = ROW_COUNT;
    p_updated := (n > 0);
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.update_user_password_by_username(
    IN p_username_lower text,
    IN p_password_hash text,
    OUT p_rows integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    UPDATE users SET password = p_password_hash WHERE lower(username) = lower(p_username_lower);
    GET DIAGNOSTICS p_rows = ROW_COUNT;
END;
$procedure$;


-- ── One-off migration helpers (same semantics as prior inline SQL) ────────────

CREATE OR REPLACE PROCEDURE public.migrate_upsert_user(
    IN p_username varchar,
    IN p_password varchar,
    IN p_email varchar,
    IN p_role varchar
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO users (username, password, email, role, created_at)
    VALUES (p_username, p_password, p_email, p_role, NOW())
    ON CONFLICT (username) DO UPDATE SET
        password = EXCLUDED.password,
        email = COALESCE(NULLIF(EXCLUDED.email, ''), users.email),
        role = EXCLUDED.role;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.migrate_upsert_jd(
    IN p_id integer,
    IN p_title varchar,
    IN p_department varchar,
    IN p_location varchar,
    IN p_experience_required text,
    IN p_skills text[],
    IN p_responsibilities text[],
    IN p_structured_data jsonb,
    IN p_raw_text text,
    IN p_file_name varchar,
    IN p_status varchar,
    IN p_created_at timestamptz,
    IN p_updated_at timestamptz
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO job_descriptions (
        id, title, department, location, experience_required, skills, responsibilities,
        structured_data, raw_text, file_name, status, created_at, updated_at
    ) VALUES (
        p_id, p_title, p_department, p_location, p_experience_required, p_skills, p_responsibilities,
        p_structured_data, p_raw_text, p_file_name, p_status, p_created_at, p_updated_at
    )
    ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        department = EXCLUDED.department,
        location = EXCLUDED.location,
        experience_required = EXCLUDED.experience_required,
        skills = EXCLUDED.skills,
        responsibilities = EXCLUDED.responsibilities,
        structured_data = EXCLUDED.structured_data,
        raw_text = EXCLUDED.raw_text,
        file_name = EXCLUDED.file_name,
        status = EXCLUDED.status,
        updated_at = EXCLUDED.updated_at;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.migrate_upsert_candidate(
    IN p_id integer,
    IN p_name varchar,
    IN p_email varchar,
    IN p_phone varchar,
    IN p_applied_roles text[],
    IN p_structured_data jsonb,
    IN p_match_score integer,
    IN p_status varchar,
    IN p_screening_summary text,
    IN p_rejection_reason text,
    IN p_hiring_stage varchar,
    IN p_resume_file varchar,
    IN p_uploaded_at timestamptz,
    IN p_jd_id integer
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO candidates (
        id, name, email, phone, applied_roles, structured_data, match_score, status,
        screening_summary, rejection_reason, hiring_stage, resume_file, uploaded_at, jd_id
    ) VALUES (
        p_id, p_name, p_email, p_phone, p_applied_roles, p_structured_data, p_match_score, p_status,
        p_screening_summary, p_rejection_reason, p_hiring_stage, p_resume_file, p_uploaded_at, p_jd_id
    )
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        email = EXCLUDED.email,
        phone = EXCLUDED.phone,
        applied_roles = EXCLUDED.applied_roles,
        structured_data = EXCLUDED.structured_data,
        match_score = EXCLUDED.match_score,
        status = EXCLUDED.status,
        screening_summary = EXCLUDED.screening_summary,
        rejection_reason = EXCLUDED.rejection_reason,
        hiring_stage = EXCLUDED.hiring_stage,
        resume_file = EXCLUDED.resume_file,
        uploaded_at = EXCLUDED.uploaded_at,
        jd_id = EXCLUDED.jd_id;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.migrate_upsert_comparison(
    IN p_id integer,
    IN p_jd_id integer,
    IN p_candidate_id integer,
    IN p_match_score integer,
    IN p_status varchar,
    IN p_strengths text[],
    IN p_gaps text[],
    IN p_recommendation text,
    IN p_failure_reason text,
    IN p_comparison_date timestamptz
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO comparisons (
        id, jd_id, candidate_id, match_score, status, strengths, gaps,
        recommendation, failure_reason, comparison_date
    ) VALUES (
        p_id, p_jd_id, p_candidate_id, p_match_score, p_status, p_strengths, p_gaps,
        p_recommendation, p_failure_reason, p_comparison_date
    )
    ON CONFLICT (jd_id, candidate_id) DO UPDATE SET
        match_score = EXCLUDED.match_score,
        status = EXCLUDED.status,
        strengths = EXCLUDED.strengths,
        gaps = EXCLUDED.gaps,
        recommendation = EXCLUDED.recommendation,
        failure_reason = EXCLUDED.failure_reason,
        comparison_date = EXCLUDED.comparison_date;
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.migrate_insert_audit_log(
    IN p_action text,
    IN p_username text,
    IN p_details text,
    IN p_jd_id integer,
    IN p_timestamp timestamptz
)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    INSERT INTO audit_logs (action, username, details, jd_id, "timestamp")
    VALUES (p_action, p_username, p_details, p_jd_id, p_timestamp);
END;
$procedure$;


CREATE OR REPLACE PROCEDURE public.resync_id_sequences()
LANGUAGE plpgsql
AS $procedure$
BEGIN
    PERFORM setval(
        pg_get_serial_sequence('users', 'id'),
        COALESCE((SELECT MAX(id) FROM users), 1),
        true
    );
    PERFORM setval(
        pg_get_serial_sequence('job_descriptions', 'id'),
        COALESCE((SELECT MAX(id) FROM job_descriptions), 1),
        true
    );
    PERFORM setval(
        pg_get_serial_sequence('candidates', 'id'),
        COALESCE((SELECT MAX(id) FROM candidates), 1),
        true
    );
    PERFORM setval(
        pg_get_serial_sequence('comparisons', 'id'),
        COALESCE((SELECT MAX(id) FROM comparisons), 1),
        true
    );
    PERFORM setval(
        pg_get_serial_sequence('audit_logs', 'id'),
        COALESCE((SELECT MAX(id) FROM audit_logs), 1),
        true
    );
END;
$procedure$;
