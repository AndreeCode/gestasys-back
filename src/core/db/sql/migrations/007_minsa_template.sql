-- Formato MINSA editable (el MINSA puede cambiar la planilla). Vacia = formato original del codigo
-- (minsa_template.py). match_section/match_label/occ ubican el dato en pregnancies.clinical_data aunque se
-- renombre la columna; aliases son otros textos de cabecera que el importador reconoce para la misma columna.
CREATE TABLE IF NOT EXISTS minsa_columns (
    key VARCHAR(40) PRIMARY KEY,
    kind VARCHAR(10) NOT NULL,
    position INTEGER NOT NULL,
    section VARCHAR(150) NOT NULL,
    grp VARCHAR(150) NOT NULL DEFAULT '',
    label VARCHAR(200) NOT NULL DEFAULT '',
    aliases TEXT[] NOT NULL DEFAULT '{}',
    fill_section CHAR(6),
    fill_group CHAR(6),
    fill_label CHAR(6),
    width SMALLINT NOT NULL DEFAULT 14,
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    match_section VARCHAR(150),
    match_label VARCHAR(200),
    occ SMALLINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT minsa_columns_kind CHECK (kind IN ('id', 'fixed', 'apn', 'clinical', 'custom')),
    CONSTRAINT minsa_columns_width CHECK (width BETWEEN 4 AND 60),
    CONSTRAINT minsa_columns_fills CHECK (
        (fill_section IS NULL OR fill_section ~ '^[0-9A-F]{6}$')
        AND (fill_group IS NULL OR fill_group ~ '^[0-9A-F]{6}$')
        AND (fill_label IS NULL OR fill_label ~ '^[0-9A-F]{6}$')
    )
);

CREATE INDEX IF NOT EXISTS idx_minsa_columns_position ON minsa_columns (position);

DO $$
BEGIN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_minsa_columns_updated_at ON minsa_columns';
    EXECUTE 'CREATE TRIGGER trg_minsa_columns_updated_at BEFORE UPDATE ON minsa_columns
             FOR EACH ROW EXECUTE FUNCTION update_timestamp()';
    EXECUTE 'DROP TRIGGER IF EXISTS trg_audit_minsa_columns ON minsa_columns';
    EXECUTE 'CREATE TRIGGER trg_audit_minsa_columns AFTER INSERT OR UPDATE OR DELETE ON minsa_columns
             FOR EACH ROW EXECUTE FUNCTION audit_changes(''key'')';
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gestasys_app') AND current_user <> 'gestasys_app' THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON minsa_columns TO gestasys_app;
    END IF;
END;
$$;
