-- 0003: classes typed in by students/faculty are stored UNVERIFIED and stay out of the public pickers until an
-- admin verifies them (existing rows are all official, hence DEFAULT 1).
ALTER TABLE branches ADD COLUMN IF NOT EXISTS is_verified INTEGER NOT NULL DEFAULT 1;
ALTER TABLE departments ADD COLUMN IF NOT EXISTS is_verified INTEGER NOT NULL DEFAULT 1;
ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS is_verified INTEGER NOT NULL DEFAULT 1;
ALTER TABLE sections ADD COLUMN IF NOT EXISTS is_verified INTEGER NOT NULL DEFAULT 1;
