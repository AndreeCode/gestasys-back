-- Jerarquia Red -> Microred -> Establecimiento (EE.SS.) y ficha de seguimiento de gestantes del MINSA.
-- Alcance de los usuarios: sin microred ni establecimiento = toda la red (superadmin); con microred = todos
-- los EE.SS. de esa microred (admin); con establecimiento = solo ese EE.SS. (admin de sede o registrador).

CREATE TABLE IF NOT EXISTS micro_networks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    network VARCHAR(150) NOT NULL DEFAULT 'Red de Salud Huamanga',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_micro_networks_name ON micro_networks (lower(name));

ALTER TABLE health_facilities ADD COLUMN IF NOT EXISTS micro_network_id UUID;
ALTER TABLE health_facilities ADD COLUMN IF NOT EXISTS renaes VARCHAR(20);
ALTER TABLE health_facilities ADD COLUMN IF NOT EXISTS province VARCHAR(100);

ALTER TABLE users ADD COLUMN IF NOT EXISTS micro_network_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'health_facilities_micro_network_id_fkey') THEN
        ALTER TABLE health_facilities
            ADD CONSTRAINT health_facilities_micro_network_id_fkey
            FOREIGN KEY (micro_network_id) REFERENCES micro_networks(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_micro_network_id_fkey') THEN
        ALTER TABLE users
            ADD CONSTRAINT users_micro_network_id_fkey
            FOREIGN KEY (micro_network_id) REFERENCES micro_networks(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_single_scope') THEN
        ALTER TABLE users
            ADD CONSTRAINT users_single_scope
            CHECK (micro_network_id IS NULL OR health_facility_id IS NULL);
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_health_facilities_renaes ON health_facilities (renaes) WHERE renaes IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_health_facilities_micro_network ON health_facilities (micro_network_id);
CREATE INDEX IF NOT EXISTS idx_users_micro_network ON users (micro_network_id);

COMMENT ON COLUMN users.micro_network_id IS
    'Microred a cargo del usuario (ve todos sus establecimientos). Excluyente con health_facility_id.';

ALTER TABLE data_imports ADD COLUMN IF NOT EXISTS format VARCHAR(20) NOT NULL DEFAULT 'csv';
ALTER TABLE data_imports ADD COLUMN IF NOT EXISTS ip_address INET;
ALTER TABLE data_imports ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE data_imports ADD COLUMN IF NOT EXISTS health_facility_id UUID REFERENCES health_facilities(id);
ALTER TABLE data_imports ADD COLUMN IF NOT EXISTS micro_network_id UUID REFERENCES micro_networks(id);

ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS clinical_record VARCHAR(30);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS insurance VARCHAR(60);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS province VARCHAR(100);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS district VARCHAR(100);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS locality VARCHAR(150);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS obstetric_formula VARCHAR(30);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS birth_date_estimated BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS clinical_data JSONB NOT NULL DEFAULT '[]'::JSONB;
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'manual';
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS import_id UUID REFERENCES data_imports(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pregnancies_registered_by ON pregnancies (registered_by);
CREATE INDEX IF NOT EXISTS idx_pregnancies_clinical_record ON pregnancies (health_facility_id, clinical_record);

ALTER TABLE prenatal_controls ADD COLUMN IF NOT EXISTS control_number SMALLINT;
ALTER TABLE prenatal_controls ADD COLUMN IF NOT EXISTS supplementation VARCHAR(60);
ALTER TABLE prenatal_controls ADD COLUMN IF NOT EXISTS risk_factor TEXT;
ALTER TABLE prenatal_controls ADD COLUMN IF NOT EXISTS performed_at VARCHAR(150);

-- Auditoria: el ambito (EE.SS. y microred del registro, y desde donde actuo el usuario) va dentro de
-- details, que ya cubre el HMAC de la cadena (003), asi que no se puede alterar sin romperla. Las columnas
-- generadas solo lo exponen para filtrar e indexar.
CREATE OR REPLACE FUNCTION audit_setting_uuid(p_name TEXT)
RETURNS UUID
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN NULLIF(current_setting(p_name, true), '')::UUID;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION audit_scope(p_table TEXT, p_row JSONB)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_facility UUID;
    v_network UUID;
    v_actor_facility UUID := audit_setting_uuid('app.health_facility_id');
    v_actor_network UUID := audit_setting_uuid('app.micro_network_id');
BEGIN
    BEGIN
        IF p_table IN ('pregnancies', 'users', 'data_imports') THEN
            v_facility := NULLIF(p_row ->> 'health_facility_id', '')::UUID;
            v_network := NULLIF(p_row ->> 'micro_network_id', '')::UUID;
        ELSIF p_table = 'prenatal_controls' THEN
            SELECT health_facility_id INTO v_facility FROM pregnancies
            WHERE id = NULLIF(p_row ->> 'pregnancy_id', '')::UUID;
        ELSIF p_table = 'health_facilities' THEN
            v_facility := NULLIF(p_row ->> 'id', '')::UUID;
            v_network := NULLIF(p_row ->> 'micro_network_id', '')::UUID;
        ELSIF p_table = 'micro_networks' THEN
            v_network := NULLIF(p_row ->> 'id', '')::UUID;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        v_facility := NULL;
    END;

    v_facility := COALESCE(v_facility, v_actor_facility);
    IF v_network IS NULL AND v_facility IS NOT NULL THEN
        SELECT micro_network_id INTO v_network FROM health_facilities WHERE id = v_facility;
    END IF;
    v_network := COALESCE(v_network, v_actor_network);

    RETURN jsonb_strip_nulls(jsonb_build_object(
        'health_facility_id', v_facility,
        'micro_network_id', v_network,
        'actor_health_facility_id', v_actor_facility,
        'actor_micro_network_id', v_actor_network
    ));
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
    END || jsonb_build_object('scope', audit_scope(TG_TABLE_NAME, v_row));

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
    v_scope JSONB;
BEGIN
    IF p_action NOT IN ('LOGIN', 'LOGIN_FAILED', 'LOGOUT', 'PASSWORD_CHANGED', 'MFA_ENABLED', 'MFA_DISABLED',
                        'MFA_RESET', 'MFA_FAILED', 'SESSION_IDLE', 'SESSION_REVOKED', 'ACCESS_DENIED') THEN
        RAISE EXCEPTION 'Accion de autenticacion no permitida: %', p_action;
    END IF;

    SELECT * INTO v_actor FROM audit_actor();

    SELECT jsonb_strip_nulls(jsonb_build_object(
               'health_facility_id', u.health_facility_id,
               'micro_network_id', COALESCE(u.micro_network_id, f.micro_network_id)))
    INTO v_scope
    FROM users u LEFT JOIN health_facilities f ON f.id = u.health_facility_id
    WHERE u.id = COALESCE(p_user_id, v_actor.user_id);

    INSERT INTO audit_log (user_id, device_id, action, affected_table, record_id, record_key,
                           ip_address, user_agent, result, details)
    VALUES (COALESCE(p_user_id, v_actor.user_id), v_actor.device_id, p_action, 'users', p_user_id,
            CASE WHEN p_user_id IS NULL THEN NULL ELSE jsonb_build_object('id', p_user_id) END,
            v_actor.ip_address, v_actor.user_agent, p_result,
            CASE WHEN v_scope IS NULL OR v_scope = '{}'::JSONB THEN p_details
                 ELSE COALESCE(p_details, '{}'::JSONB) || jsonb_build_object('scope', v_scope) END);
END;
$$;

CREATE OR REPLACE FUNCTION audit_jsonb_uuid(p_details JSONB, p_key TEXT)
RETURNS UUID
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE WHEN (p_details -> 'scope' ->> p_key) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN (p_details -> 'scope' ->> p_key)::UUID END
$$;

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS scope_health_facility_id UUID
    GENERATED ALWAYS AS (audit_jsonb_uuid(details, 'health_facility_id')) STORED;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS scope_micro_network_id UUID
    GENERATED ALWAYS AS (audit_jsonb_uuid(details, 'micro_network_id')) STORED;

CREATE INDEX IF NOT EXISTS idx_audit_log_scope_facility ON audit_log (scope_health_facility_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_scope_network ON audit_log (scope_micro_network_id, created_at);

DO $$
BEGIN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_micro_networks_updated_at ON micro_networks';
    EXECUTE 'CREATE TRIGGER trg_micro_networks_updated_at BEFORE UPDATE ON micro_networks
             FOR EACH ROW EXECUTE FUNCTION update_timestamp()';
    EXECUTE 'DROP TRIGGER IF EXISTS trg_audit_micro_networks ON micro_networks';
    EXECUTE 'CREATE TRIGGER trg_audit_micro_networks AFTER INSERT OR UPDATE OR DELETE ON micro_networks
             FOR EACH ROW EXECUTE FUNCTION audit_changes()';

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gestasys_app') AND current_user <> 'gestasys_app' THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON micro_networks TO gestasys_app;
    END IF;
END;
$$;
