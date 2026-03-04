-- Add 'excluded' to the poi status check constraint.
-- Excluded POIs are locations the generation pipeline determined are not worth an audio tour
-- (e.g. completely generic, no history, no cultural significance).
--
-- The constraint name below follows the Postgres auto-naming convention for inline CHECK constraints.
-- Verify the actual name in your DB with:
--   SELECT conname FROM pg_constraint WHERE conrelid = 'poi'::regclass AND contype = 'c';

ALTER TABLE poi
    DROP CONSTRAINT poi_status_check,
    ADD CONSTRAINT poi_status_check
        CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'excluded'));
