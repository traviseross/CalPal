-- Add unique constraint to prevent duplicate mirror events
-- This ensures that each source event can only have ONE mirror per target calendar

-- First, let's see what duplicates exist (for reference)
SELECT
    metadata->>'source_event_id' as source_id,
    current_calendar,
    COUNT(*) as copies
FROM calendar_events
WHERE metadata->>'source_event_id' IS NOT NULL
    AND deleted_at IS NULL
GROUP BY metadata->>'source_event_id', current_calendar
HAVING COUNT(*) > 1
ORDER BY copies DESC
LIMIT 10;

-- Create the unique index
-- This will prevent inserting duplicate mirrors at the database level
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_mirror_source
ON calendar_events ((metadata->>'source_event_id'), current_calendar)
WHERE metadata->>'source_event_id' IS NOT NULL
    AND deleted_at IS NULL;

-- Verify the index was created
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'calendar_events'
    AND indexname = 'idx_unique_mirror_source';
