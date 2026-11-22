-- A08/A09: cadena de hashes en audit_log para detectar registros borrados o editados.
-- Las filas se insertan sin hash y la app las "sella" en lote cada pocos segundos con
-- seal_audit_log(clave): encadenar en cada INSERT obligaria a serializar todas las transacciones
-- que auditan algo (una importacion larga frenaria al resto). El hash es HMAC-SHA256 con una
-- clave que tiene la app (AUDIT_CHAIN_KEY) y no la BD, asi quien solo accede a la BD no puede
-- recalcular la cadena para ocultar un cambio.
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS chain_seq BIGINT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS prev_hash CHAR(64);
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS row_hash CHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_log_chain_seq ON audit_log (chain_seq);
CREATE INDEX IF NOT EXISTS idx_audit_log_unsealed ON audit_log (created_at, id) WHERE chain_seq IS NULL;
CREATE SEQUENCE IF NOT EXISTS audit_log_chain_seq;

CREATE OR REPLACE FUNCTION audit_row_digest(p_key TEXT, p_seq BIGINT, p_prev TEXT, r audit_log)
RETURNS TEXT
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT encode(hmac(
        jsonb_build_object(
            'seq', p_seq, 'prev', p_prev, 'id', r.id, 'user_id', r.user_id, 'device_id', r.device_id,
            'action', r.action, 'affected_table', r.affected_table, 'record_id', r.record_id,
            'record_key', r.record_key, 'ip_address', host(r.ip_address), 'user_agent', r.user_agent,
            'result', r.result, 'details', r.details,
            'created_at', to_char(r.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US')
        )::text, p_key, 'sha256'), 'hex')
$$;

CREATE OR REPLACE FUNCTION seal_audit_log(p_key TEXT, p_limit INTEGER DEFAULT 5000)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_prev TEXT;
    v_row audit_log;
    v_seq BIGINT;
    v_hash TEXT;
    v_count INTEGER := 0;
BEGIN
    IF p_key IS NULL OR length(p_key) < 32 THEN
        RAISE EXCEPTION 'La clave de la cadena de auditoria es invalida';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('audit_log_chain'));
    SELECT row_hash INTO v_prev FROM audit_log WHERE chain_seq IS NOT NULL ORDER BY chain_seq DESC LIMIT 1;
    FOR v_row IN SELECT * FROM audit_log WHERE chain_seq IS NULL ORDER BY created_at, id LIMIT p_limit LOOP
        v_seq := nextval('audit_log_chain_seq');
        v_hash := audit_row_digest(p_key, v_seq, v_prev, v_row);
        UPDATE audit_log SET chain_seq = v_seq, prev_hash = v_prev, row_hash = v_hash WHERE id = v_row.id;
        v_prev := v_hash;
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION verify_audit_chain(p_key TEXT)
RETURNS TABLE (ok BOOLEAN, checked BIGINT, unsealed BIGINT, last_seq BIGINT, last_hash TEXT, broken_seq BIGINT, reason TEXT)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row audit_log;
    v_prev TEXT := NULL;
    v_count BIGINT := 0;
    v_unsealed BIGINT;
BEGIN
    SELECT count(*) INTO v_unsealed FROM audit_log WHERE chain_seq IS NULL;
    FOR v_row IN SELECT * FROM audit_log WHERE chain_seq IS NOT NULL ORDER BY chain_seq LOOP
        v_count := v_count + 1;
        IF v_row.prev_hash IS DISTINCT FROM v_prev THEN
            RETURN QUERY SELECT FALSE, v_count, v_unsealed, NULL::BIGINT, NULL::TEXT, v_row.chain_seq,
                'Falta un registro anterior o se altero el enlace con el registro previo';
            RETURN;
        END IF;
        IF v_row.row_hash IS DISTINCT FROM audit_row_digest(p_key, v_row.chain_seq, v_row.prev_hash, v_row) THEN
            RETURN QUERY SELECT FALSE, v_count, v_unsealed, NULL::BIGINT, NULL::TEXT, v_row.chain_seq,
                'El contenido del registro fue modificado (o la clave AUDIT_CHAIN_KEY cambio)';
            RETURN;
        END IF;
        v_prev := v_row.row_hash;
    END LOOP;
    RETURN QUERY SELECT TRUE, v_count, v_unsealed,
        (SELECT max(a.chain_seq) FROM audit_log a), v_prev, NULL::BIGINT, NULL::TEXT;
END;
$$;

CREATE OR REPLACE FUNCTION audit_log_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_log es de solo escritura: no se pueden borrar registros';
    END IF;
    IF OLD.chain_seq IS NOT NULL
       OR (to_jsonb(NEW) - 'chain_seq' - 'prev_hash' - 'row_hash')
          IS DISTINCT FROM (to_jsonb(OLD) - 'chain_seq' - 'prev_hash' - 'row_hash') THEN
        RAISE EXCEPTION 'audit_log es de solo escritura: no se pueden modificar registros';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;
CREATE TRIGGER trg_audit_log_immutable
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
