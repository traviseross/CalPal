-- CalPal Event Tracking Schema
-- This database tracks all calendar events across CalPal's managed calendars
-- to enable intelligent bidirectional syncing and deletion detection

CREATE TABLE IF NOT EXISTS calendar_events (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Event identifiers
    event_id VARCHAR(255) NOT NULL,
    ical_uid VARCHAR(500),  -- iCalUID can be long

    -- Event details
    summary TEXT,
    description TEXT,
    location TEXT,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,

    -- Calendar tracking
    source_calendar VARCHAR(255),      -- Where it was originally found
    current_calendar VARCHAR(255),      -- Where it currently lives
    destination_calendar VARCHAR(255),  -- Where it was moved to (if moved)

    -- Event classification
    event_type VARCHAR(50),  -- 'booking', 'meeting_invitation', '25live_class', '25live_event', 'manual', 'other'
    is_attendee_event BOOLEAN DEFAULT FALSE,  -- True if Travis is an attendee (not organizer)
    is_recurring BOOLEAN DEFAULT FALSE,

    -- State tracking
    status VARCHAR(50) NOT NULL DEFAULT 'active',  -- 'active', 'declined', 'deleted', 'moved'
    last_action VARCHAR(50),  -- 'created', 'moved', 'declined', 'deleted', 'updated'
    last_action_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Organizer info
    organizer_email VARCHAR(255),
    creator_email VARCHAR(255),

    -- Response tracking (for attendee events)
    response_status VARCHAR(50),  -- 'accepted', 'declined', 'tentative', 'needsAction'

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- Last time we saw this event during scan

    -- Soft delete
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Additional metadata as JSON
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_event_id ON calendar_events(event_id);
CREATE INDEX IF NOT EXISTS idx_ical_uid ON calendar_events(ical_uid);
CREATE INDEX IF NOT EXISTS idx_current_calendar ON calendar_events(current_calendar);
CREATE INDEX IF NOT EXISTS idx_status ON calendar_events(status);
CREATE INDEX IF NOT EXISTS idx_event_type ON calendar_events(event_type);
CREATE INDEX IF NOT EXISTS idx_last_seen ON calendar_events(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_start_time ON calendar_events(start_time);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_calendar_status ON calendar_events(current_calendar, status);
CREATE INDEX IF NOT EXISTS idx_status_type ON calendar_events(status, event_type);

-- Unique constraint: same event_id can appear in different calendars
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_calendar_unique
    ON calendar_events(event_id, current_calendar)
    WHERE deleted_at IS NULL;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_calendar_events_updated_at
    BEFORE UPDATE ON calendar_events
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE calendar_events IS 'Tracks all calendar events across CalPal managed calendars for intelligent syncing';
COMMENT ON COLUMN calendar_events.event_id IS 'Google Calendar event ID (varies by calendar context)';
COMMENT ON COLUMN calendar_events.ical_uid IS 'iCalendar UID - universal identifier that persists across moves';
COMMENT ON COLUMN calendar_events.status IS 'Current lifecycle status: active, declined, deleted, moved';
COMMENT ON COLUMN calendar_events.event_type IS 'Classification: booking, meeting_invitation, 25live_class, 25live_event, manual, other';
COMMENT ON COLUMN calendar_events.last_seen_at IS 'Last time this event was detected during a calendar scan';
COMMENT ON COLUMN calendar_events.response_status IS 'For attendee events: accepted, declined, tentative, needsAction';

-- Create a view for active events
CREATE OR REPLACE VIEW active_events AS
SELECT * FROM calendar_events
WHERE status = 'active' AND deleted_at IS NULL;

-- Create a view for deleted events (for audit trail)
CREATE OR REPLACE VIEW deleted_events AS
SELECT * FROM calendar_events
WHERE status = 'deleted' OR deleted_at IS NOT NULL;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO calpal;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO calpal;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO calpal;
