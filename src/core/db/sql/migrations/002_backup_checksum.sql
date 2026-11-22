-- A08: SHA-256 del archivo tal como quedo en disco (cifrado o no). Se verifica antes de cada descarga.
ALTER TABLE backups ADD COLUMN IF NOT EXISTS sha256 CHAR(64);
