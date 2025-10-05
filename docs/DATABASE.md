# CalPal Database Setup

## Overview

CalPal uses a PostgreSQL database to track calendar events across all managed calendars, enabling intelligent bidirectional syncing and deletion detection.

## Architecture

- **Database**: PostgreSQL 15 (Alpine)
- **Deployment**: Docker container
- **Connection**: Host network (not Docker network)
- **Port**: 5433 (mapped from container's 5432)
- **Data Persistence**: Docker volume `calpal_db_data`

## Quick Reference

### Connection Details

```
Host: localhost
Port: 5433
Database: calpal_db
User: calpal
Password: [see docker-compose.yml or use environment variable]
Connection String: postgresql://calpal:your_password@localhost:5433/calpal_db
```

### Container Management

```bash
# Start database
cd /home/tradmin/CalPal
docker compose up -d

# Stop database
docker compose down

# View logs
docker compose logs -f calpal_db

# Check status
docker compose ps

# Reset database (WARNING: deletes all data)
docker compose down -v
docker compose up -d
```

### Database Access

```bash
# Connect with psql
docker exec -it calpal_db psql -U calpal -d calpal_db

# Run SQL file
docker exec -i calpal_db psql -U calpal -d calpal_db < db/migrations/001_migration.sql

# Backup database
docker exec calpal_db pg_dump -U calpal calpal_db > backup_$(date +%Y%m%d).sql

# Restore database
cat backup_20251002.sql | docker exec -i calpal_db psql -U calpal -d calpal_db
```

## Schema

### Entity Relationship Diagram

```mermaid
erDiagram
    calendar_events {
        serial id PK "Primary key"
        varchar event_id "Google Calendar event ID"
        varchar ical_uid "iCalendar universal UID"
        text summary "Event title"
        text description "Event description"
        text location "Event location"
        timestamptz start_time "Event start time"
        timestamptz end_time "Event end time"
        varchar source_calendar "Original calendar"
        varchar current_calendar "Current calendar"
        varchar destination_calendar "Moved-to calendar"
        varchar event_type "Event classification"
        boolean is_attendee_event "Attendee vs organizer"
        boolean is_recurring "Recurring event flag"
        varchar status "Lifecycle status"
        varchar last_action "Last action performed"
        timestamptz last_action_at "Last action timestamp"
        varchar organizer_email "Event organizer"
        varchar creator_email "Event creator"
        varchar response_status "RSVP status"
        timestamptz created_at "Record creation"
        timestamptz updated_at "Last update"
        timestamptz last_seen_at "Last scan detection"
        timestamptz deleted_at "Soft delete timestamp"
        jsonb metadata "Additional data"
        boolean do_not_mirror "Mirror exclusion flag"
        boolean is_all_day "All-day event flag"
        varchar mirror_event_id "Mirror link"
    }
```

### `calendar_events` Table

The central table that tracks all calendar events across CalPal's managed calendars, enabling intelligent bidirectional syncing, deletion detection, and mirror management.

#### Complete Column Reference

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | SERIAL | NO | AUTO | Primary key, auto-incrementing |
| `event_id` | VARCHAR(255) | NO | - | Google Calendar event ID (changes when event moves) |
| `ical_uid` | VARCHAR(500) | YES | NULL | iCalendar UID - universal identifier that persists across moves |
| `summary` | TEXT | YES | NULL | Event title/summary |
| `description` | TEXT | YES | NULL | Event description/notes |
| `location` | TEXT | YES | NULL | Event location |
| `start_time` | TIMESTAMPTZ | YES | NULL | Event start time with timezone |
| `end_time` | TIMESTAMPTZ | YES | NULL | Event end time with timezone |
| `source_calendar` | VARCHAR(255) | YES | NULL | Calendar where event was originally found |
| `current_calendar` | VARCHAR(255) | YES | NULL | Calendar where event currently resides |
| `destination_calendar` | VARCHAR(255) | YES | NULL | Calendar where event was moved to (if moved) |
| `event_type` | VARCHAR(50) | YES | NULL | Event classification (see Event Types) |
| `is_attendee_event` | BOOLEAN | YES | FALSE | TRUE if user is attendee, not organizer |
| `is_recurring` | BOOLEAN | YES | FALSE | TRUE if this is a recurring event |
| `status` | VARCHAR(50) | NO | 'active' | Current lifecycle status (see Status Values) |
| `last_action` | VARCHAR(50) | YES | NULL | Last action performed on event (see Actions) |
| `last_action_at` | TIMESTAMPTZ | YES | NOW() | Timestamp of last action |
| `organizer_email` | VARCHAR(255) | YES | NULL | Email address of event organizer |
| `creator_email` | VARCHAR(255) | YES | NULL | Email address of event creator |
| `response_status` | VARCHAR(50) | YES | NULL | RSVP status for attendee events |
| `created_at` | TIMESTAMPTZ | YES | NOW() | When this database record was created |
| `updated_at` | TIMESTAMPTZ | YES | NOW() | When this database record was last updated |
| `last_seen_at` | TIMESTAMPTZ | YES | NOW() | Last time event was detected during calendar scan |
| `deleted_at` | TIMESTAMPTZ | YES | NULL | Soft delete timestamp (NULL = not deleted) |
| `metadata` | JSONB | YES | '{}' | Additional event metadata (see Metadata Schema) |
| `do_not_mirror` | BOOLEAN | YES | FALSE | If TRUE, never mirror this event |
| `is_all_day` | BOOLEAN | YES | FALSE | TRUE if this is an all-day event |
| `mirror_event_id` | VARCHAR(255) | YES | NULL | Event ID of the mirror copy (if mirrored) |

#### Event Types

Enumerated values for `event_type` column:

| Value | Description | Example |
|-------|-------------|---------|
| `booking` | Meeting room bookings from 25Live | Conference room reservation |
| `meeting_invitation` | Calendar invitations where user is attendee | Team meeting invite |
| `25live_class` | Academic classes from 25Live | MATH 101 lecture |
| `25live_event` | Campus events from 25Live | Chapel service, guest speaker |
| `manual` | Manually created events | Personal appointment |
| `other` | Events that don't fit other categories | Default fallback |

#### Status Values

Enumerated values for `status` column:

| Value | Description | Lifecycle Stage |
|-------|-------------|-----------------|
| `active` | Event is currently active | Normal operation |
| `declined` | User declined meeting invitation | Terminal state |
| `deleted` | Event has been deleted | Terminal state |
| `moved` | Event was moved to another calendar | Transitional state |

#### Last Action Values

Enumerated values for `last_action` column:

| Value | Description | When Set |
|-------|-------------|----------|
| `created` | Event was newly created | Initial insert |
| `updated` | Event details were modified | Update operation |
| `moved` | Event was moved to different calendar | Move operation |
| `declined` | User declined the invitation | Decline operation |
| `deleted` | Event was removed | Delete operation |

#### Response Status Values

Enumerated values for `response_status` column (for attendee events):

| Value | Description |
|-------|-------------|
| `accepted` | User accepted the invitation |
| `declined` | User declined the invitation |
| `tentative` | User tentatively accepted |
| `needsAction` | User has not responded yet |

#### Metadata JSONB Schema

The `metadata` column stores additional structured data as JSONB. Common fields:

```json
{
  "25live_reservation_id": "string",
  "25live_event_id": "string",
  "calendar_type": "string",
  "source_event_id": "string"
}
```

**Metadata Fields:**

| Field | Type | Used By | Description |
|-------|------|---------|-------------|
| `25live_reservation_id` | string | 25Live sync | Unique reservation ID from 25Live system |
| `25live_event_id` | string | 25Live sync | Event ID from 25Live system |
| `calendar_type` | string | 25Live sync | Type of calendar: 'academic', 'booking', etc. |
| `source_event_id` | string | Mirror system | Event ID of the original source event being mirrored |

**Example metadata values:**

```sql
-- 25Live event
metadata = {
  "25live_reservation_id": "R12345",
  "25live_event_id": "E67890",
  "calendar_type": "academic"
}

-- Mirror event
metadata = {
  "source_event_id": "abc123xyz",
  "calendar_type": "work"
}
```

#### Indexes

Performance-optimized indexes for common query patterns:

| Index Name | Columns | Type | Purpose |
|------------|---------|------|---------|
| `idx_event_id` | event_id | B-tree | Fast event lookup by Google Calendar ID |
| `idx_ical_uid` | ical_uid | B-tree | Fast lookup by universal iCal UID |
| `idx_current_calendar` | current_calendar | B-tree | Filter events by calendar |
| `idx_status` | status | B-tree | Filter by lifecycle status |
| `idx_event_type` | event_type | B-tree | Filter by event classification |
| `idx_last_seen` | last_seen_at | B-tree | Find stale/orphaned events |
| `idx_start_time` | start_time | B-tree | Time-based queries, sorting |
| `idx_calendar_status` | current_calendar, status | Composite | Calendar-specific active events |
| `idx_status_type` | status, event_type | Composite | Filter by status and type |
| `idx_event_calendar_unique` | event_id, current_calendar | Unique partial | Prevent duplicate events (where deleted_at IS NULL) |
| `idx_unique_mirror_source` | metadata->>'source_event_id', current_calendar | Unique partial | Prevent duplicate mirrors (where source_event_id IS NOT NULL AND deleted_at IS NULL) |
| `idx_do_not_mirror` | ical_uid, do_not_mirror | Composite | Mirror exclusion checks |
| `idx_mirror_event` | mirror_event_id | B-tree | Find mirror relationships |

**Key Index Details:**

- **Unique Partial Indexes**: Use `WHERE` clauses to enforce uniqueness only on active records, allowing soft-deleted duplicates
- **JSONB Indexes**: `idx_unique_mirror_source` uses JSONB extraction operator `->>`
- **Composite Indexes**: Optimize common multi-column queries

#### Triggers

**update_calendar_events_updated_at**
- Trigger: BEFORE UPDATE on calendar_events
- Function: update_updated_at_column()
- Purpose: Automatically sets updated_at = NOW() on every UPDATE
- Implementation: PL/pgSQL function

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';
```

#### Views

**active_events**
```sql
CREATE OR REPLACE VIEW active_events AS
SELECT * FROM calendar_events
WHERE status = 'active' AND deleted_at IS NULL;
```
Purpose: Quick access to all currently active events (most common query)

**deleted_events**
```sql
CREATE OR REPLACE VIEW deleted_events AS
SELECT * FROM calendar_events
WHERE status = 'deleted' OR deleted_at IS NOT NULL;
```
Purpose: Audit trail of deleted events for reconciliation and debugging

#### Event Lifecycle

Events flow through the following states:

```
[Created] -> active (last_action: 'created')
    |
    v
[Normal Operations]
    - Updates: status stays 'active', last_action: 'updated'
    - Regular scans update last_seen_at
    |
    v
[Terminal States]
    - Deleted: status='deleted', deleted_at=NOW(), last_action='deleted'
    - Declined: status='declined', last_action='declined'
    - Moved: status='moved', destination_calendar set, last_action='moved'
```

**Soft Delete Pattern:**
- Never physically DELETE rows
- Set deleted_at timestamp and status='deleted'
- Unique indexes use `WHERE deleted_at IS NULL` to ignore deleted records
- Deleted events remain in database for audit trail

**Mirror Relationship Tracking:**
- Source event stores `mirror_event_id` pointing to mirror copy
- Mirror event stores `metadata->>'source_event_id'` pointing back to source
- Unique constraint prevents duplicate mirrors per calendar
- `do_not_mirror` flag prevents re-mirroring of user-deleted mirrors

#### Foreign Key Relationships

This schema currently has no foreign keys. All relationships are managed at the application level through:
- event_id and ical_uid references to Google Calendar
- metadata fields for 25Live integration
- Mirror relationships through metadata->>'source_event_id'

#### Constraints

1. **Primary Key**: id (auto-incrementing serial)

2. **NOT NULL Constraints**:
   - event_id (required for all events)
   - status (must always have lifecycle state)

3. **Unique Constraints**:
   - One event_id per calendar (active records only)
   - One mirror per source event per calendar (active records only)

4. **Check Constraints**: None currently defined

5. **Default Values**:
   - is_attendee_event: FALSE
   - is_recurring: FALSE
   - status: 'active'
   - last_action_at: NOW()
   - created_at: NOW()
   - updated_at: NOW()
   - last_seen_at: NOW()
   - metadata: '{}'::jsonb
   - do_not_mirror: FALSE
   - is_all_day: FALSE

## Python Usage

```python
from src.db_manager import DatabaseManager

# Initialize
db = DatabaseManager()

# Test connection
if db.test_connection():
    print("Connected!")

# Record an event
event_data = {
    'event_id': 'abc123',
    'current_calendar': 'tross@georgefox.edu',
    'summary': 'Test Event',
    'start_time': datetime.now(),
    'end_time': datetime.now() + timedelta(hours=1),
    'event_type': 'manual',
    'status': 'active'
}
db.record_event(event_data)

# Get event
event = db.get_event_by_id('abc123', 'tross@georgefox.edu')

# Mark as deleted
db.mark_as_deleted('abc123', 'tross@georgefox.edu')

# Get stats
stats = db.get_stats()
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs calpal_db

# Check if port 5433 is in use
lsof -i :5433

# Remove and recreate
docker compose down -v
docker compose up -d
```

### Connection refused

```bash
# Verify container is running
docker ps | grep calpal_db

# Check health
docker inspect calpal_db | grep -A 10 Health

# Test from container
docker exec calpal_db psql -U calpal -d calpal_db -c "SELECT 1"
```

### Schema issues

```bash
# Rerun init script
docker exec -i calpal_db psql -U calpal -d calpal_db < db/init/01_schema.sql
```

## Migrations

### Migration File Structure

CalPal uses sequential numbered migration files stored in `/home/tradmin/CalPal/db/migrations/`:

```
db/
├── init/
│   └── 01_schema.sql          # Initial schema (run once on new DB)
├── migrations/
│   └── 002_add_mirror_fields.sql  # Sequential migrations
└── add_unique_mirror_constraint.sql  # Ad-hoc fixes
```

### Migration Naming Convention

Format: `NNN_descriptive_name.sql`

- `NNN`: Three-digit sequential number (002, 003, 004...)
- Use underscores for spaces
- Be descriptive but concise
- Examples:
  - `002_add_mirror_fields.sql`
  - `003_add_timezone_support.sql`
  - `004_create_recurring_event_table.sql`

### Creating a New Migration

1. **Determine next number**: Check existing migrations
   ```bash
   ls -1 /home/tradmin/CalPal/db/migrations/
   ```

2. **Create migration file**:
   ```bash
   nano /home/tradmin/CalPal/db/migrations/003_your_migration.sql
   ```

3. **Write idempotent SQL**: Use `IF EXISTS` / `IF NOT EXISTS`
   ```sql
   -- Good: Idempotent
   ALTER TABLE calendar_events
   ADD COLUMN IF NOT EXISTS new_field VARCHAR(100);

   CREATE INDEX IF NOT EXISTS idx_new_field
   ON calendar_events(new_field);

   -- Bad: Will fail if run twice
   ALTER TABLE calendar_events ADD COLUMN new_field VARCHAR(100);
   ```

4. **Add comments**:
   ```sql
   -- Migration 003: Add timezone tracking
   -- Date: 2025-10-04
   -- Purpose: Store explicit timezone for each event

   ALTER TABLE calendar_events
   ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Los_Angeles';

   COMMENT ON COLUMN calendar_events.timezone IS 'IANA timezone identifier';
   ```

### Applying Migrations

**Apply single migration:**
```bash
docker exec -i calpal_db psql -U calpal -d calpal_db < db/migrations/003_migration.sql
```

**Apply all migrations in order:**
```bash
for file in db/migrations/*.sql; do
  echo "Applying $file..."
  docker exec -i calpal_db psql -U calpal -d calpal_db < "$file"
done
```

**Verify migration applied:**
```bash
docker exec -it calpal_db psql -U calpal -d calpal_db -c "\d calendar_events"
```

### Migration Best Practices

1. **Always use IF EXISTS / IF NOT EXISTS**: Migrations should be idempotent
2. **Add comments**: Document purpose and any special considerations
3. **Test on copy first**: Test migrations on database backup before production
4. **One logical change per file**: Don't combine unrelated changes
5. **Include rollback notes**: Comment how to undo if needed
6. **Preserve data**: Use ALTER, not DROP/CREATE when modifying tables
7. **Update constraints carefully**: Be aware of existing data

### Rollback Procedures

Migrations don't have automatic rollback. For each migration, document rollback:

```sql
-- Migration 003: Add timezone field
-- ROLLBACK: ALTER TABLE calendar_events DROP COLUMN IF EXISTS timezone;

ALTER TABLE calendar_events
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Los_Angeles';
```

**To rollback:**
```bash
# Extract rollback command from migration file
grep "ROLLBACK:" db/migrations/003_migration.sql

# Run manually
docker exec -it calpal_db psql -U calpal -d calpal_db \
  -c "ALTER TABLE calendar_events DROP COLUMN IF EXISTS timezone;"
```

### Migration Checklist

Before applying migration in production:

- [ ] Migration file uses IF EXISTS / IF NOT EXISTS
- [ ] Migration is idempotent (can run multiple times safely)
- [ ] Comments explain purpose and rollback
- [ ] Tested on local database copy
- [ ] Schema documentation updated (this file)
- [ ] Python code updated to use new fields
- [ ] No data loss from existing records
- [ ] Indexes added for new columns if needed
- [ ] Default values set appropriately

## Query Patterns

### Common Queries

#### Finding Duplicates

**Duplicate events in same calendar:**
```sql
SELECT
    event_id,
    current_calendar,
    COUNT(*) as copies
FROM calendar_events
WHERE deleted_at IS NULL
GROUP BY event_id, current_calendar
HAVING COUNT(*) > 1;
```

**Duplicate mirror events:**
```sql
SELECT
    metadata->>'source_event_id' as source_id,
    current_calendar,
    COUNT(*) as copies,
    ARRAY_AGG(event_id) as mirror_ids
FROM calendar_events
WHERE metadata->>'source_event_id' IS NOT NULL
    AND deleted_at IS NULL
GROUP BY metadata->>'source_event_id', current_calendar
HAVING COUNT(*) > 1
ORDER BY copies DESC;
```

**Duplicate 25Live events:**
```sql
SELECT
    metadata->>'25live_reservation_id' as reservation_id,
    current_calendar,
    COUNT(*) as copies,
    ARRAY_AGG(summary) as event_names
FROM calendar_events
WHERE metadata->>'25live_reservation_id' IS NOT NULL
    AND deleted_at IS NULL
GROUP BY metadata->>'25live_reservation_id', current_calendar
HAVING COUNT(*) > 1;
```

#### Getting Events by Type

**All booking events:**
```sql
SELECT
    event_id,
    summary,
    location,
    start_time,
    current_calendar
FROM calendar_events
WHERE event_type = 'booking'
    AND status = 'active'
    AND deleted_at IS NULL
ORDER BY start_time;
```

**Meeting invitations where user is attendee:**
```sql
SELECT
    event_id,
    summary,
    organizer_email,
    response_status,
    start_time
FROM calendar_events
WHERE event_type = 'meeting_invitation'
    AND is_attendee_event = TRUE
    AND status = 'active'
    AND deleted_at IS NULL
    AND response_status = 'needsAction'
ORDER BY start_time;
```

**25Live academic classes:**
```sql
SELECT
    event_id,
    summary,
    location,
    start_time,
    metadata->>'25live_reservation_id' as reservation_id
FROM calendar_events
WHERE event_type = '25live_class'
    AND status = 'active'
    AND deleted_at IS NULL
    AND start_time >= NOW()
ORDER BY start_time;
```

#### Mirror Relationship Queries

**Find source event for a mirror:**
```sql
SELECT
    source.event_id,
    source.summary,
    source.current_calendar as source_calendar,
    mirror.event_id as mirror_id,
    mirror.current_calendar as mirror_calendar
FROM calendar_events mirror
JOIN calendar_events source
    ON mirror.metadata->>'source_event_id' = source.event_id
WHERE mirror.event_id = 'specific_mirror_id'
    AND mirror.deleted_at IS NULL
    AND source.deleted_at IS NULL;
```

**Find all mirrors of a source event:**
```sql
SELECT
    event_id as mirror_id,
    current_calendar as mirror_calendar,
    summary,
    status,
    created_at
FROM calendar_events
WHERE metadata->>'source_event_id' = 'source_event_id'
    AND deleted_at IS NULL
ORDER BY created_at;
```

**Events marked do_not_mirror:**
```sql
SELECT
    ical_uid,
    summary,
    current_calendar,
    event_type,
    deleted_at
FROM calendar_events
WHERE do_not_mirror = TRUE
ORDER BY updated_at DESC;
```

#### Soft Delete Queries

**Recently deleted events:**
```sql
SELECT
    event_id,
    summary,
    current_calendar,
    deleted_at,
    last_action
FROM calendar_events
WHERE deleted_at IS NOT NULL
ORDER BY deleted_at DESC
LIMIT 50;
```

**Events deleted in last 24 hours:**
```sql
SELECT
    event_id,
    summary,
    current_calendar,
    event_type,
    deleted_at
FROM calendar_events
WHERE deleted_at >= NOW() - INTERVAL '24 hours'
ORDER BY deleted_at DESC;
```

**Restore soft-deleted event:**
```sql
UPDATE calendar_events
SET
    deleted_at = NULL,
    status = 'active',
    last_action = 'restored',
    last_action_at = NOW(),
    updated_at = NOW()
WHERE event_id = 'event_to_restore'
    AND current_calendar = 'calendar_id';
```

#### Orphaned/Stale Event Detection

**Events not seen in last 7 days:**
```sql
SELECT
    event_id,
    summary,
    current_calendar,
    last_seen_at,
    AGE(NOW(), last_seen_at) as time_since_seen
FROM calendar_events
WHERE last_seen_at < NOW() - INTERVAL '7 days'
    AND status = 'active'
    AND deleted_at IS NULL
ORDER BY last_seen_at;
```

**Events with missing Google Calendar data:**
```sql
-- These might be orphaned in database
SELECT
    event_id,
    summary,
    current_calendar,
    last_seen_at,
    status
FROM calendar_events
WHERE last_seen_at < NOW() - INTERVAL '1 hour'
    AND status = 'active'
    AND deleted_at IS NULL
    AND event_type != 'manual'
ORDER BY last_seen_at;
```

#### Statistics and Analytics

**Events per calendar:**
```sql
SELECT
    current_calendar,
    COUNT(*) as total_events,
    COUNT(*) FILTER (WHERE status = 'active') as active,
    COUNT(*) FILTER (WHERE status = 'deleted') as deleted
FROM calendar_events
WHERE deleted_at IS NULL
GROUP BY current_calendar
ORDER BY total_events DESC;
```

**Events by type and status:**
```sql
SELECT
    event_type,
    status,
    COUNT(*) as count
FROM calendar_events
WHERE deleted_at IS NULL
GROUP BY event_type, status
ORDER BY event_type, status;
```

**Mirror statistics:**
```sql
SELECT
    COUNT(*) FILTER (WHERE metadata->>'source_event_id' IS NOT NULL) as total_mirrors,
    COUNT(DISTINCT metadata->>'source_event_id') as unique_sources,
    COUNT(DISTINCT current_calendar) as calendars_with_mirrors
FROM calendar_events
WHERE deleted_at IS NULL;
```

**Event creation rate over time:**
```sql
SELECT
    DATE(created_at) as date,
    COUNT(*) as events_created,
    COUNT(*) FILTER (WHERE event_type = 'booking') as bookings,
    COUNT(*) FILTER (WHERE event_type = '25live_class') as classes
FROM calendar_events
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Performance Optimization Tips

1. **Always filter on indexed columns first:**
   ```sql
   -- Good: Uses idx_status
   WHERE status = 'active' AND summary LIKE '%meeting%'

   -- Bad: Scans all rows first
   WHERE summary LIKE '%meeting%' AND status = 'active'
   ```

2. **Use composite indexes efficiently:**
   ```sql
   -- Good: Uses idx_calendar_status
   WHERE current_calendar = 'cal_id' AND status = 'active'

   -- Good: Uses idx_status_type
   WHERE status = 'active' AND event_type = 'booking'
   ```

3. **Leverage partial indexes:**
   ```sql
   -- Good: Uses idx_event_calendar_unique efficiently
   WHERE deleted_at IS NULL AND event_id = 'xyz'

   -- Suboptimal: Index can't help with deleted events
   WHERE deleted_at IS NOT NULL AND event_id = 'xyz'
   ```

4. **Use JSONB operators efficiently:**
   ```sql
   -- Good: Uses idx_unique_mirror_source
   WHERE metadata->>'source_event_id' = 'xyz' AND deleted_at IS NULL

   -- Bad: Can't use index (IS NOT NULL on JSONB field)
   WHERE metadata->>'source_event_id' IS NOT NULL
   ```

5. **Count efficiently:**
   ```sql
   -- Fast: Uses index-only scan
   SELECT COUNT(*) FROM calendar_events WHERE status = 'active';

   -- Slower: Requires table scan
   SELECT COUNT(*) FROM calendar_events WHERE summary LIKE '%test%';
   ```

6. **Use EXPLAIN ANALYZE to verify:**
   ```bash
   docker exec -it calpal_db psql -U calpal -d calpal_db

   EXPLAIN ANALYZE
   SELECT * FROM calendar_events
   WHERE current_calendar = 'cal_id' AND status = 'active';
   ```

### Inspecting Data

```sql
-- View all active events
SELECT * FROM active_events ORDER BY start_time DESC LIMIT 10;

-- Count events by calendar
SELECT current_calendar, COUNT(*)
FROM calendar_events
WHERE deleted_at IS NULL
GROUP BY current_calendar;

-- Recent deletions
SELECT * FROM deleted_events ORDER BY deleted_at DESC LIMIT 10;

-- Events that need syncing
SELECT * FROM calendar_events
WHERE last_seen_at < NOW() - INTERVAL '1 hour'
AND status = 'active';
```

## Schema Consistency & Drift Prevention

### Schema Validation Checklist

Run this checklist periodically to detect schema drift:

**1. Verify column consistency:**
```sql
-- Check for unexpected columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'calendar_events'
ORDER BY ordinal_position;
```

**2. Verify index consistency:**
```sql
-- List all indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'calendar_events'
ORDER BY indexname;
```

**3. Verify constraint consistency:**
```sql
-- List all constraints
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'calendar_events'::regclass
ORDER BY conname;
```

**4. Verify trigger consistency:**
```sql
-- List all triggers
SELECT trigger_name, event_manipulation, action_statement
FROM information_schema.triggers
WHERE event_object_table = 'calendar_events';
```

### Common Schema Drift Issues

**Issue: Missing indexes after schema recreation**
- **Detection**: Slow queries, EXPLAIN shows sequential scans
- **Fix**: Run `/home/tradmin/CalPal/db/init/01_schema.sql`

**Issue: Metadata field inconsistencies**
- **Detection**: JSONB queries fail or return unexpected results
- **Query to detect**:
  ```sql
  -- Find all unique metadata keys
  SELECT DISTINCT jsonb_object_keys(metadata) as key
  FROM calendar_events
  ORDER BY key;
  ```
- **Fix**: Standardize metadata structure in application code

**Issue: Duplicate constraints not enforced**
- **Detection**: Duplicate events found in queries
- **Query to detect**: See "Finding Duplicates" section
- **Fix**: Run `/home/tradmin/CalPal/db/add_unique_mirror_constraint.sql`

**Issue: Soft-deleted records not excluded**
- **Detection**: Deleted events appear in active queries
- **Query to detect**:
  ```sql
  SELECT COUNT(*) FROM calendar_events
  WHERE deleted_at IS NOT NULL AND status = 'active';
  ```
- **Fix**: Add `WHERE deleted_at IS NULL` to all active queries

### Metadata Schema Governance

**Required metadata fields by event type:**

| Event Type | Required Metadata Keys | Optional Keys |
|------------|------------------------|---------------|
| `booking` | `25live_reservation_id`, `calendar_type` | `25live_event_id` |
| `25live_class` | `25live_reservation_id`, `calendar_type` | `25live_event_id` |
| `25live_event` | `25live_reservation_id`, `calendar_type` | `25live_event_id` |
| `meeting_invitation` | - | - |
| `manual` | - | - |
| Mirror events | `source_event_id` | `calendar_type` |

**Metadata validation query:**
```sql
-- Find 25Live events missing reservation_id
SELECT event_id, summary, event_type, metadata
FROM calendar_events
WHERE event_type IN ('booking', '25live_class', '25live_event')
    AND metadata->>'25live_reservation_id' IS NULL
    AND deleted_at IS NULL;

-- Find mirror events missing source_event_id
SELECT event_id, summary, current_calendar, metadata
FROM calendar_events
WHERE metadata ? 'source_event_id'  -- Has the key
    AND metadata->>'source_event_id' IS NULL  -- But value is NULL
    AND deleted_at IS NULL;
```

### Schema Documentation Maintenance

When making schema changes, update the following:

1. **This file** (`/home/tradmin/CalPal/docs/DATABASE.md`)
   - Add new columns to "Complete Column Reference"
   - Update ER diagram
   - Add new indexes to "Indexes" section
   - Update metadata schema if applicable

2. **Migration file** (`/home/tradmin/CalPal/db/migrations/NNN_*.sql`)
   - Document the change
   - Include rollback instructions
   - Add column comments

3. **Python code** (`/home/tradmin/CalPal/src/db_manager.py`)
   - Update queries to use new fields
   - Add validation for new constraints
   - Update method signatures if needed

4. **Application code**
   - Update event_data dictionaries
   - Add new metadata fields where applicable
   - Update validation logic

### Migration Version Tracking

Currently, CalPal doesn't track applied migrations. To add migration tracking:

```sql
-- Create migrations table (future enhancement)
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    checksum VARCHAR(64)
);

-- Example entries
INSERT INTO schema_migrations (version, name, checksum)
VALUES
    ('001', 'initial_schema', 'abc123...'),
    ('002', 'add_mirror_fields', 'def456...');
```

### Data Quality Checks

Run these queries regularly to maintain data quality:

**1. Orphaned mirrors (source deleted):**
```sql
SELECT m.event_id, m.summary, m.metadata->>'source_event_id' as source_id
FROM calendar_events m
LEFT JOIN calendar_events s
    ON m.metadata->>'source_event_id' = s.event_id
    AND s.deleted_at IS NULL
WHERE m.metadata->>'source_event_id' IS NOT NULL
    AND m.deleted_at IS NULL
    AND s.id IS NULL;
```

**2. Events with invalid status:**
```sql
SELECT event_id, summary, status
FROM calendar_events
WHERE status NOT IN ('active', 'declined', 'deleted', 'moved')
    AND deleted_at IS NULL;
```

**3. Events with inconsistent soft-delete state:**
```sql
SELECT event_id, summary, status, deleted_at
FROM calendar_events
WHERE (status = 'deleted' AND deleted_at IS NULL)
    OR (status != 'deleted' AND deleted_at IS NOT NULL);
```

**4. Events with future last_seen_at:**
```sql
SELECT event_id, summary, last_seen_at
FROM calendar_events
WHERE last_seen_at > NOW()
    AND deleted_at IS NULL;
```

**5. Events missing required fields:**
```sql
SELECT event_id, summary, event_type, start_time, end_time
FROM calendar_events
WHERE (start_time IS NULL OR end_time IS NULL)
    AND deleted_at IS NULL
    AND event_type NOT IN ('manual');
```

### Schema Normalization Notes

Current schema is intentionally denormalized for performance:

**Why not separate tables for:**
- **Calendars**: Calendar IDs are strings (email addresses), no need for lookup table
- **Event types**: Only 6 values, not worth separate table overhead
- **Status values**: Only 4 values, VARCHAR is more efficient than FK
- **Metadata**: JSONB provides schema flexibility for varying event types

**If CalPal scales, consider normalizing:**
- Create `calendars` table if calendar metadata needed
- Create `event_types` table if types exceed 10-15 values
- Create `25live_reservations` table for 25Live-specific fields
- Create `mirror_relationships` table to track mirror families

## Security Notes

- **Change default password**: The default password in `docker-compose.yml` is for development only
- **For production**: Use environment variables or Docker secrets for password management
- **Network isolation**: Database should only be accessible from localhost (not 0.0.0.0)
- **Connection pooling**: Prevents connection exhaustion and improves performance
- **Soft deletes**: Maintains complete audit trail of all deleted events
- **Data sensitivity**: Calendar events may contain sensitive scheduling information
- **User permissions**: Database user `calpal` should only have access to `calpal_db`

**Production Security Checklist:**
- [ ] Change database password from default
- [ ] Use environment variables for credentials
- [ ] Bind database to localhost only
- [ ] Enable SSL/TLS for database connections
- [ ] Regular backup schedule established
- [ ] Backups encrypted at rest
- [ ] Database access logged and monitored

## Backup and Recovery

### Backup Procedures

**Full database backup:**
```bash
# Create backup with timestamp
docker exec calpal_db pg_dump -U calpal calpal_db > \
  /home/tradmin/CalPal/backups/calpal_db_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker exec calpal_db pg_dump -U calpal calpal_db | \
  gzip > /home/tradmin/CalPal/backups/calpal_db_$(date +%Y%m%d_%H%M%S).sql.gz
```

**Schema-only backup:**
```bash
docker exec calpal_db pg_dump -U calpal --schema-only calpal_db > \
  /home/tradmin/CalPal/backups/schema_$(date +%Y%m%d).sql
```

**Data-only backup:**
```bash
docker exec calpal_db pg_dump -U calpal --data-only calpal_db > \
  /home/tradmin/CalPal/backups/data_$(date +%Y%m%d).sql
```

### Recovery Procedures

**Full database restore:**
```bash
# Drop and recreate database
docker exec -it calpal_db psql -U calpal -c "DROP DATABASE IF EXISTS calpal_db;"
docker exec -it calpal_db psql -U calpal -c "CREATE DATABASE calpal_db;"

# Restore from backup
cat /home/tradmin/CalPal/backups/calpal_db_20251004.sql | \
  docker exec -i calpal_db psql -U calpal -d calpal_db
```

**Restore from compressed backup:**
```bash
gunzip -c /home/tradmin/CalPal/backups/calpal_db_20251004.sql.gz | \
  docker exec -i calpal_db psql -U calpal -d calpal_db
```

**Restore specific table:**
```bash
# Extract calendar_events table only
pg_restore -U calpal -d calpal_db -t calendar_events backup.dump
```

### Automated Backup Strategy

**Daily backups (recommended):**
```bash
# Add to crontab
0 2 * * * /home/tradmin/CalPal/scripts/backup_database.sh
```

**Example backup script:**
```bash
#!/bin/bash
# /home/tradmin/CalPal/scripts/backup_database.sh

BACKUP_DIR="/home/tradmin/CalPal/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup
docker exec calpal_db pg_dump -U calpal calpal_db | \
  gzip > "$BACKUP_DIR/calpal_db_$DATE.sql.gz"

# Remove old backups
find "$BACKUP_DIR" -name "calpal_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: calpal_db_$DATE.sql.gz"
```

## Next Steps

After database is set up:
1. Implement event scanner service
2. Add bidirectional sync logic
3. Handle deletion detection
4. Implement decline/delete actions for attendee events
5. Set up automated backups
6. Create migration tracking table
7. Add data quality monitoring alerts
