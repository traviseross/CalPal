-- Add fields for mirror tracking and recurring event handling

-- Add do_not_mirror flag for events user has deleted and don't want re-mirrored
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS do_not_mirror BOOLEAN DEFAULT FALSE;

-- Add is_all_day flag to identify all-day events
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS is_all_day BOOLEAN DEFAULT FALSE;

-- Add mirror_event_id to link mirrors to originals
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS mirror_event_id VARCHAR(255);

-- Add index for do_not_mirror queries
CREATE INDEX IF NOT EXISTS idx_do_not_mirror ON calendar_events(ical_uid, do_not_mirror);

-- Add index for mirror lookups
CREATE INDEX IF NOT EXISTS idx_mirror_event ON calendar_events(mirror_event_id);

-- Add comments
COMMENT ON COLUMN calendar_events.do_not_mirror IS 'If TRUE, this event should never be mirrored (user deleted recurring all-day event)';
COMMENT ON COLUMN calendar_events.is_all_day IS 'TRUE if this is an all-day event';
COMMENT ON COLUMN calendar_events.mirror_event_id IS 'Event ID of the mirror event (if this is a source being mirrored)';
