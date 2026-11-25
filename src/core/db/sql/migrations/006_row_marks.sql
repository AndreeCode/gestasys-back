-- Marcas de color del Excel MINSA: color de la fila (1 = pintada, 0 = sin color) y celdas pintadas
-- distinto a su fila ({"f:province": "FFFF00", "apn:3:date": "FF0000", ...}; las de la ficha van en clinical_data).
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS row_color CHAR(6);
ALTER TABLE pregnancies ADD COLUMN IF NOT EXISTS cell_marks JSONB NOT NULL DEFAULT '{}'::JSONB;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pregnancies_row_color_hex') THEN
        ALTER TABLE pregnancies ADD CONSTRAINT pregnancies_row_color_hex CHECK (row_color IS NULL OR row_color ~ '^[0-9A-F]{6}$');
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_pregnancies_row_color ON pregnancies (row_color) WHERE row_color IS NOT NULL;
