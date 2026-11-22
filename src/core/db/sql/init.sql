CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF to_regtype('result_type') IS NULL THEN
        CREATE TYPE result_type AS ENUM ('successful', 'failed', 'blocked');
    END IF;

    IF to_regtype('pregnancy_status') IS NULL THEN
        CREATE TYPE pregnancy_status AS ENUM ('pending', 'in_followup', 'completed');
    END IF;

    IF to_regtype('risk_level') IS NULL THEN
        CREATE TYPE risk_level AS ENUM ('low', 'medium', 'high');
    END IF;

    IF to_regtype('backup_kind') IS NULL THEN
        CREATE TYPE backup_kind AS ENUM ('manual', 'automatic');
    END IF;

    IF to_regtype('backup_status') IS NULL THEN
        CREATE TYPE backup_status AS ENUM ('running', 'completed', 'failed');
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(60) NOT NULL UNIQUE,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT roles_name_format CHECK (name ~ '^[a-z][a-z0-9_]{1,59}$')
);

CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS role_permission (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,

    role_id UUID NOT NULL REFERENCES roles(id),

    full_name VARCHAR(200) NOT NULL,
    dni VARCHAR(8),
    phone VARCHAR(30),

    active BOOLEAN NOT NULL DEFAULT TRUE,
    blocked BOOLEAN NOT NULL DEFAULT FALSE,
    blocked_reason TEXT,

    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    password_changed_at TIMESTAMPTZ,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT users_dni_format CHECK (dni IS NULL OR dni ~ '^[0-9]{8}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_dni ON users (dni) WHERE dni IS NOT NULL;

CREATE TABLE IF NOT EXISTS health_facilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(60),
    district VARCHAR(100),
    address TEXT,
    phone VARCHAR(30),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_health_facilities_name ON health_facilities (lower(name));

CREATE TABLE IF NOT EXISTS record_counters (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pregnancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,

    dni VARCHAR(8),
    first_names VARCHAR(120) NOT NULL,
    last_names VARCHAR(120) NOT NULL,
    birth_date DATE NOT NULL,
    phone VARCHAR(30),
    address TEXT,

    health_facility_id UUID NOT NULL REFERENCES health_facilities(id),

    last_menstrual_period DATE,
    expected_delivery_date DATE,
    gravida SMALLINT,
    parity SMALLINT,
    risk_level risk_level NOT NULL DEFAULT 'low',
    status pregnancy_status NOT NULL DEFAULT 'pending',
    delivery_date DATE,
    notes TEXT,

    registered_by UUID REFERENCES users(id) ON DELETE SET NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pregnancies_dni_format CHECK (dni IS NULL OR dni ~ '^[0-9]{8}$'),
    CONSTRAINT pregnancies_gravida CHECK (gravida IS NULL OR gravida BETWEEN 1 AND 30),
    CONSTRAINT pregnancies_parity CHECK (parity IS NULL OR parity BETWEEN 0 AND 30),
    CONSTRAINT pregnancies_edd_after_lmp CHECK (
        expected_delivery_date IS NULL OR last_menstrual_period IS NULL
        OR expected_delivery_date > last_menstrual_period
    ),
    CONSTRAINT pregnancies_lmp_after_birth CHECK (
        last_menstrual_period IS NULL OR last_menstrual_period > birth_date
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pregnancies_open_dni
    ON pregnancies (dni) WHERE dni IS NOT NULL AND active AND status <> 'completed';
CREATE INDEX IF NOT EXISTS idx_pregnancies_facility ON pregnancies (health_facility_id);
CREATE INDEX IF NOT EXISTS idx_pregnancies_status ON pregnancies (status) WHERE active;
CREATE INDEX IF NOT EXISTS idx_pregnancies_created ON pregnancies (created_at);
CREATE INDEX IF NOT EXISTS idx_pregnancies_name ON pregnancies (lower(last_names), lower(first_names));

CREATE TABLE IF NOT EXISTS prenatal_controls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pregnancy_id UUID NOT NULL REFERENCES pregnancies(id) ON DELETE CASCADE,

    control_date DATE NOT NULL,
    gestational_weeks NUMERIC(4, 1),
    weight_kg NUMERIC(5, 2),
    systolic_bp SMALLINT,
    diastolic_bp SMALLINT,
    fetal_heart_rate SMALLINT,
    uterine_height_cm NUMERIC(4, 1),
    hemoglobin NUMERIC(4, 1),
    next_appointment DATE,
    notes TEXT,

    registered_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT prenatal_controls_weeks CHECK (gestational_weeks IS NULL OR gestational_weeks BETWEEN 0 AND 45),
    CONSTRAINT prenatal_controls_weight CHECK (weight_kg IS NULL OR weight_kg BETWEEN 25 AND 250),
    CONSTRAINT prenatal_controls_bp CHECK (
        (systolic_bp IS NULL OR systolic_bp BETWEEN 50 AND 260)
        AND (diastolic_bp IS NULL OR diastolic_bp BETWEEN 30 AND 180)
    ),
    CONSTRAINT prenatal_controls_fhr CHECK (fetal_heart_rate IS NULL OR fetal_heart_rate BETWEEN 60 AND 220),
    CONSTRAINT prenatal_controls_uterine CHECK (uterine_height_cm IS NULL OR uterine_height_cm BETWEEN 0 AND 60),
    CONSTRAINT prenatal_controls_hb CHECK (hemoglobin IS NULL OR hemoglobin BETWEEN 3 AND 25),
    CONSTRAINT prenatal_controls_next CHECK (next_appointment IS NULL OR next_appointment >= control_date)
);

CREATE INDEX IF NOT EXISTS idx_prenatal_controls_pregnancy ON prenatal_controls (pregnancy_id, control_date);
CREATE INDEX IF NOT EXISTS idx_prenatal_controls_next ON prenatal_controls (next_appointment);

CREATE TABLE IF NOT EXISTS data_imports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name VARCHAR(255) NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::JSONB,
    imported_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_imports_created ON data_imports (created_at);

CREATE TABLE IF NOT EXISTS backups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind backup_kind NOT NULL,
    status backup_status NOT NULL DEFAULT 'running',
    file_name VARCHAR(255),
    size_bytes BIGINT,
    tables TEXT[] NOT NULL DEFAULT '{}',
    priority VARCHAR(10) NOT NULL DEFAULT 'high',
    error TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT backups_priority CHECK (priority IN ('high', 'normal', 'low'))
);

CREATE INDEX IF NOT EXISTS idx_backups_started ON backups (started_at);

CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_hash VARCHAR(64) NOT NULL,
    user_agent TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trusted BOOLEAN NOT NULL DEFAULT TRUE,
    blocked_reason TEXT,
    blocked_at TIMESTAMPTZ,
    CONSTRAINT devices_user_hash_unique UNIQUE (user_id, device_hash)
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_reason VARCHAR(50),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    affected_table VARCHAR(100),
    record_id UUID,
    record_key JSONB,
    ip_address INET,
    user_agent TEXT,
    result result_type NOT NULL DEFAULT 'successful',
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION audit_actor(OUT user_id UUID, OUT device_id UUID, OUT ip_address INET, OUT user_agent TEXT)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    BEGIN
        user_id := NULLIF(current_setting('app.user_id', true), '')::UUID;
    EXCEPTION WHEN OTHERS THEN
        user_id := NULL;
    END;

    BEGIN
        device_id := NULLIF(current_setting('app.device_id', true), '')::UUID;
    EXCEPTION WHEN OTHERS THEN
        device_id := NULL;
    END;

    BEGIN
        ip_address := NULLIF(current_setting('app.ip_address', true), '')::INET;
    EXCEPTION WHEN OTHERS THEN
        ip_address := NULL;
    END;

    user_agent := NULLIF(current_setting('app.user_agent', true), '');
END;
$$;

CREATE OR REPLACE FUNCTION audit_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_actor RECORD;
    v_row JSONB;
    v_old JSONB;
    v_new JSONB;
    v_record_id UUID;
    v_record_key JSONB;
    v_details JSONB;
    v_col TEXT;
    v_noise TEXT[] := ARRAY['updated_at', 'last_seen_at', 'last_login_at', 'failed_attempts', 'locked_until',
                            'last_activity_at', 'mfa_last_step'];
BEGIN
    SELECT * INTO v_actor FROM audit_actor();

    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        v_old := to_jsonb(OLD);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        v_new := to_jsonb(NEW);
    END IF;
    v_row := COALESCE(v_new, v_old);

    IF TG_NARGS = 0 THEN
        v_record_id := (v_row ->> 'id')::UUID;
        v_record_key := jsonb_build_object('id', v_row -> 'id');
    ELSE
        v_record_key := '{}'::JSONB;
        FOREACH v_col IN ARRAY TG_ARGV LOOP
            v_record_key := v_record_key || jsonb_build_object(v_col, v_row -> v_col);
        END LOOP;
    END IF;

    v_old := v_old - 'password_hash' - 'token_hash' - 'mfa_secret' - 'mfa_pending_secret' - 'mfa_recovery_codes';
    v_new := v_new - 'password_hash' - 'token_hash' - 'mfa_secret' - 'mfa_pending_secret' - 'mfa_recovery_codes';

    IF TG_OP = 'UPDATE' AND (v_old - v_noise) = (v_new - v_noise) THEN
        RETURN NEW;
    END IF;

    v_details := CASE TG_OP
        WHEN 'INSERT' THEN jsonb_build_object('new', v_new)
        WHEN 'DELETE' THEN jsonb_build_object('old', v_old)
        ELSE jsonb_build_object('old', v_old, 'new', v_new)
    END;

    INSERT INTO audit_log (
        user_id, device_id, action, affected_table, record_id, record_key,
        ip_address, user_agent, result, details
    )
    VALUES (
        v_actor.user_id, v_actor.device_id, TG_OP, TG_TABLE_NAME, v_record_id, v_record_key,
        v_actor.ip_address, v_actor.user_agent, 'successful', v_details
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE OR REPLACE FUNCTION log_auth_event(p_action TEXT, p_user_id UUID, p_result result_type, p_details JSONB)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_actor RECORD;
BEGIN
    IF p_action NOT IN ('LOGIN', 'LOGIN_FAILED', 'LOGOUT', 'PASSWORD_CHANGED', 'MFA_ENABLED', 'MFA_DISABLED',
                        'MFA_RESET', 'MFA_FAILED', 'SESSION_IDLE', 'SESSION_REVOKED') THEN
        RAISE EXCEPTION 'Accion de autenticacion no permitida: %', p_action;
    END IF;

    SELECT * INTO v_actor FROM audit_actor();

    INSERT INTO audit_log (user_id, device_id, action, affected_table, record_id, record_key,
                           ip_address, user_agent, result, details)
    VALUES (COALESCE(p_user_id, v_actor.user_id), v_actor.device_id, p_action, 'users', p_user_id,
            CASE WHEN p_user_id IS NULL THEN NULL ELSE jsonb_build_object('id', p_user_id) END,
            v_actor.ip_address, v_actor.user_agent, p_result, p_details);
END;
$$;

CREATE OR REPLACE FUNCTION check_prenatal_control_date()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_lmp DATE;
BEGIN
    IF NEW.control_date > CURRENT_DATE THEN
        RAISE EXCEPTION 'La fecha del control no puede estar en el futuro';
    END IF;

    SELECT last_menstrual_period INTO v_lmp FROM pregnancies WHERE id = NEW.pregnancy_id;

    IF v_lmp IS NOT NULL AND NEW.control_date < v_lmp THEN
        RAISE EXCEPTION 'La fecha del control no puede ser anterior a la FUM (%)', v_lmp;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION revoke_sessions_on_user_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF (NEW.blocked AND NOT OLD.blocked) OR (NOT NEW.active AND OLD.active) THEN
        UPDATE sessions SET revoked = TRUE, revoked_at = NOW(),
               revoked_reason = CASE WHEN NEW.blocked THEN 'user_blocked' ELSE 'user_inactive' END
        WHERE user_id = NEW.id AND NOT revoked;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION revoke_sessions_on_device_block()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT NEW.trusted AND OLD.trusted THEN
        NEW.blocked_at := NOW();
        UPDATE sessions SET revoked = TRUE, revoked_at = NOW(), revoked_reason = 'device_blocked'
        WHERE device_id = NEW.id AND NOT revoked;
    ELSIF NEW.trusted AND NOT OLD.trusted THEN
        NEW.blocked_at := NULL;
        NEW.blocked_reason := NULL;
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['roles', 'users', 'health_facilities', 'pregnancies', 'prenatal_controls'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', t);
        EXECUTE format('CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
                        FOR EACH ROW EXECUTE FUNCTION update_timestamp()', t);
    END LOOP;

    FOREACH t IN ARRAY ARRAY[
        'roles', 'users', 'permissions', 'health_facilities', 'pregnancies',
        'prenatal_controls', 'data_imports', 'backups', 'devices', 'sessions'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_audit_%1$s ON %1$I', t);
        EXECUTE format('CREATE TRIGGER trg_audit_%1$s AFTER INSERT OR UPDATE OR DELETE ON %1$I
                        FOR EACH ROW EXECUTE FUNCTION audit_changes()', t);
    END LOOP;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_role_permission ON role_permission;
CREATE TRIGGER trg_audit_role_permission
AFTER INSERT OR UPDATE OR DELETE ON role_permission
FOR EACH ROW EXECUTE FUNCTION audit_changes('role_id', 'permission_id');

DROP TRIGGER IF EXISTS trg_prenatal_controls_date ON prenatal_controls;
CREATE TRIGGER trg_prenatal_controls_date
BEFORE INSERT OR UPDATE OF control_date, pregnancy_id ON prenatal_controls
FOR EACH ROW EXECUTE FUNCTION check_prenatal_control_date();

DROP TRIGGER IF EXISTS trg_users_revoke_sessions ON users;
CREATE TRIGGER trg_users_revoke_sessions
AFTER UPDATE OF blocked, active ON users
FOR EACH ROW EXECUTE FUNCTION revoke_sessions_on_user_change();

DROP TRIGGER IF EXISTS trg_devices_block ON devices;
CREATE TRIGGER trg_devices_block
BEFORE UPDATE OF trusted ON devices
FOR EACH ROW EXECUTE FUNCTION revoke_sessions_on_device_block();

CREATE INDEX IF NOT EXISTS idx_users_role ON users (role_id);
CREATE INDEX IF NOT EXISTS idx_devices_user ON devices (user_id);
CREATE INDEX IF NOT EXISTS idx_devices_hash ON devices (device_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_revoked ON sessions (user_id, revoked);
CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions (device_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_date ON audit_log (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON audit_log (affected_table, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_date ON audit_log (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_record_key ON audit_log USING GIN (record_key);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gestasys_app') AND current_user <> 'gestasys_app' THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            roles, permissions, role_permission, users, health_facilities, record_counters,
            pregnancies, prenatal_controls, data_imports, backups, devices, sessions
        TO gestasys_app;

        GRANT SELECT ON audit_log TO gestasys_app;
        REVOKE INSERT, UPDATE, DELETE ON audit_log FROM gestasys_app;
        GRANT EXECUTE ON FUNCTION log_auth_event(TEXT, UUID, result_type, JSONB) TO gestasys_app;
    END IF;
END;
$$;
