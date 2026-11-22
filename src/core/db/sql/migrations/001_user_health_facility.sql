ALTER TABLE users ADD COLUMN IF NOT EXISTS health_facility_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_health_facility_id_fkey') THEN
        ALTER TABLE users
            ADD CONSTRAINT users_health_facility_id_fkey
            FOREIGN KEY (health_facility_id) REFERENCES health_facilities(id);
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_users_facility ON users (health_facility_id);

COMMENT ON COLUMN users.health_facility_id IS
    'Establecimiento al que esta limitado el usuario. NULL = ve todos los establecimientos.';
