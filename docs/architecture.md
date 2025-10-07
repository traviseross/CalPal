# CalPal Architecture

This document describes the system architecture, design patterns, and component interactions in CalPal.

## System Overview

CalPal is a database-backed calendar synchronization system that maintains bidirectional sync between CollegeNET 25Live, Google Calendar, and generates filtered ICS feeds. The PostgreSQL database serves as the single source of truth for all event data.

## Core Design Principles

### 1. Database as Single Source of Truth
All calendar events are stored in PostgreSQL with complete lifecycle tracking. This enables:
- **Conflict Resolution:** Database state determines what exists in Google Calendar
- **Audit Trail:** Complete history of all event operations
- **Idempotency:** Repeated operations produce the same result
- **Deletion Detection:** Tracks when events are manually deleted

### 2. Event Lifecycle Management
Every event has a tracked lifecycle:
```
Created → Updated (optional) → Deleted
```

Each state change is recorded with:
- `created_at` - When event was first added to database
- `updated_at` - Last modification timestamp
- `deleted_at` - Soft deletion timestamp
- `last_action` - Most recent operation type

### 3. Signature-Based Duplicate Prevention
Events use unique signatures to prevent duplicates:
- **25Live Events:** `reservation_id` from 25Live API
- **Google Calendar Events:** `ical_uid` for event identity
- **Mirror Events:** `source_event_id` linking to original

### 4. Bidirectional Sync
CalPal detects changes in both directions:
- **25Live → Database:** New/updated events from 25Live
- **Google Calendar → Database:** Manual deletions, external changes
- **Database → Google Calendar:** Event creation, updates, deletion

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      External Systems                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────┐         ┌──────────────────┐                │
│  │ 25Live API    │         │ Google Calendar  │                 │
│  │ (Classes,     │         │ API              │                 │
│  │  Events)      │         │ (Read/Write)     │                 │
│  └───────┬───────┘         └────────┬─────────┘                 │
│          │                          │                            │
│          │                          │                            │
└──────────┼──────────────────────────┼────────────────────────────┘
           │                          │
           │ Inbound                  │ Bidirectional
           │ Events                   │ Sync
           ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CalPal Core System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                        │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  calendar_events table                           │   │   │
│  │  │  - Single source of truth for all events        │   │   │
│  │  │  - Tracks lifecycle (created/updated/deleted)   │   │   │
│  │  │  - Stores event metadata and signatures         │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  event_blacklist table                          │   │   │
│  │  │  - Permanently deleted events                    │   │   │
│  │  │  - Prevents recreation after manual deletion    │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│           ┌──────────────┴──────────────┐                       │
│           │                             │                        │
│  ┌────────▼────────┐          ┌─────────▼────────┐             │
│  │ Data Ingestion  │          │ Event Processing │             │
│  │  Components     │          │   Components     │             │
│  ├─────────────────┤          ├──────────────────┤             │
│  │                 │          │                  │             │
│  │ • 25Live Sync   │          │ • Event Organizer│             │
│  │ • Calendar      │          │ • Mirror Manager │             │
│  │   Scanner       │          │ • Reconciler     │             │
│  │                 │          │ • Subcalendar    │             │
│  │                 │          │   Sync           │             │
│  └─────────────────┘          └──────────────────┘             │
│           │                             │                        │
│           └──────────────┬──────────────┘                       │
│                          │                                       │
│                 ┌────────▼────────┐                             │
│                 │ Calendar Writer │                             │
│                 │  (Google Cal)   │                             │
│                 └────────┬────────┘                             │
│                          │                                       │
│                 ┌────────▼────────┐                             │
│                 │  ICS Generator  │                             │
│                 │  & Web Server   │                             │
│                 └─────────────────┘                             │
│                          │                                       │
└──────────────────────────┼─────────────────────────────────────┘
                           │
                           ▼
               ┌────────────────────┐
               │  ICS Feed Output   │
               │  (External Access) │
               └────────────────────┘
```

## Component Architecture

### Core Components (`calpal/core/`)

#### DatabaseManager
**Responsibilities:**
- Manage PostgreSQL connections
- Execute queries with proper error handling
- Handle transactions and connection pooling
- Provide database abstraction layer

**Key Methods:**
- `get_connection()` - Get database connection from pool
- `execute_query()` - Execute parameterized SQL queries
- `get_events()` - Retrieve events with filtering
- `add_event()` - Insert new event with conflict handling
- `mark_event_deleted()` - Soft-delete event
- `add_to_blacklist()` - Permanently block event recreation

### Sync Components (`calpal/sync/`)

#### TwentyFiveLiveSync
**Purpose:** Pull events from 25Live API into database

**Operation Flow:**
1. Authenticate with 25Live API (session-based)
2. Query events by date range and type
3. Transform 25Live JSON to database schema
4. Check for existing events (by reservation_id)
5. Insert new events or update existing ones
6. Respect blacklist (skip recreating manually deleted events)

**Key Features:**
- Batched queries (25Live has 30-day max range)
- Retry logic with exponential backoff
- Event signature using `reservation_id`
- Automatic duplicate prevention

#### CalendarScanner
**Purpose:** Scan Google Calendars for changes and deletions

**Operation Flow:**
1. Connect to Google Calendar API
2. Fetch events from specified calendars
3. Compare with database state
4. Detect manually deleted events (in DB but not in calendar)
5. Mark deleted events in database
6. Remove deleted events from Google Calendar
7. Record new events found in calendar

**Key Features:**
- Bidirectional sync detection
- Deletion detection and cleanup
- Event discovery (finds manually added events)
- Respects event blacklist

#### UnifiedSyncService
**Purpose:** Coordinate all sync components

**Operation Flow:**
```python
while True:
    # 1. Pull fresh data from 25Live
    twentyfive_live_sync.run()

    # 2. Scan calendars for changes/deletions
    calendar_scanner.scan_and_cleanup()

    # 3. Mirror personal/family events
    mirror_manager.sync_mirrors()

    # 4. Organize work events into subcalendars
    event_organizer.organize_events()

    # 5. Sync subcalendars to work calendar
    subcalendar_sync.sync()

    # 6. Generate ICS feeds
    ics_generator.generate()

    sleep(300)  # 5 minutes
```

**Scheduling:**
- 25Live Sync: Every 30 minutes
- Calendar Scanner: Every 15 minutes
- Event Organization: Every 5 minutes
- ICS Generation: Every 5 minutes

### Organizer Components (`calpal/organizers/`)

#### EventOrganizer
**Purpose:** Route work calendar events to appropriate subcalendars

**Routing Logic:**
```python
if event.is_booking_type():
    route_to("Appointments")
elif event.matches_keyword("class", "lecture"):
    route_to("Classes")
elif event.matches_keyword("committee", "meeting"):
    route_to("Meetings")
elif event.is_campus_event():
    route_to("GFU Events")
else:
    route_to("Personal Events")
```

#### MirrorManager
**Purpose:** Mirror events from personal/family calendars to work calendar

**Mirroring Process:**
1. Fetch events from source calendar (e.g., Personal, Family)
2. Create "busy" placeholder in work calendar
3. Transform event details (privacy protection)
4. Link mirror to source via `source_event_id`
5. Sync updates when source changes
6. Delete mirror when source is deleted

#### Reconciler
**Purpose:** Ensure database and Google Calendar are in sync

**Reconciliation Process:**
1. Compare database events with calendar events
2. Identify discrepancies (missing, extra, mismatched)
3. Apply corrective actions based on rules
4. Log all reconciliation actions
5. Report irreconcilable conflicts

#### SubcalendarSync
**Purpose:** Sync subcalendar events back to main work calendar

**Operation:**
- Ensures events organized into subcalendars also appear in work calendar
- Maintains links between subcalendar event and work calendar copy
- Handles updates propagation
- Cleans up orphaned copies

### Generator Components (`calpal/generators/`)

#### ICSGenerator
**Purpose:** Generate filtered ICS files from database

**Filtering Process:**
1. Query database for relevant events
2. Apply privacy filters (exclude personal details)
3. Transform event data (e.g., replace titles, remove attendees)
4. Build ICS file using iCalendar library
5. Write to file system

**Customization Points:**
```python
# Filter which events to include
def should_include_event(event):
    if event.calendar == "Personal":
        return event.summary == "Busy"
    return True

# Transform event details
def transform_event(event):
    if event.is_private:
        event.summary = "Busy"
        event.description = ""
    return event
```

#### ICSServer
**Purpose:** Serve ICS files via Flask web server

**Security Features:**
- Token-based authentication
- Secure random endpoint path
- HTTPS support (with reverse proxy)
- Rate limiting
- Access logging

**Endpoints:**
```
GET /<SECURE_PATH>/schedule.ics?token=<ACCESS_TOKEN>
```

## Database Schema

### calendar_events Table

```sql
CREATE TABLE calendar_events (
    event_id TEXT PRIMARY KEY,              -- Google Calendar event ID
    current_calendar TEXT NOT NULL,         -- Calendar where event lives
    ical_uid TEXT,                          -- iCalendar UID (for identity)
    summary TEXT,                           -- Event title
    description TEXT,                       -- Event description
    start_time TIMESTAMP WITH TIME ZONE,    -- Event start
    end_time TIMESTAMP WITH TIME ZONE,      -- Event end
    location TEXT,                          -- Event location
    event_type TEXT,                        -- Event classification
    metadata JSONB,                         -- Additional data (25Live ID, etc.)
    created_at TIMESTAMP DEFAULT NOW(),     -- When added to database
    updated_at TIMESTAMP DEFAULT NOW(),     -- Last database update
    deleted_at TIMESTAMP,                   -- Soft deletion timestamp
    last_action TEXT                        -- Last operation: created, moved, deleted, etc.
);

CREATE INDEX idx_calendar_events_ical_uid ON calendar_events(ical_uid);
CREATE INDEX idx_calendar_events_calendar ON calendar_events(current_calendar);
CREATE INDEX idx_calendar_events_deleted ON calendar_events(deleted_at);
CREATE INDEX idx_calendar_events_metadata ON calendar_events USING GIN(metadata);
```

### event_blacklist Table

```sql
CREATE TABLE event_blacklist (
    blacklist_id SERIAL PRIMARY KEY,
    ical_uid TEXT NOT NULL,                 -- Event identifier
    calendar_id TEXT NOT NULL,              -- Calendar it was deleted from
    blacklisted_at TIMESTAMP DEFAULT NOW(), -- When blacklisted
    reason TEXT,                            -- Why blacklisted
    metadata JSONB                          -- Additional context
);

CREATE INDEX idx_blacklist_ical_uid ON event_blacklist(ical_uid);
```

## Data Flow

### 25Live Event Ingestion

```
25Live API
    │
    │ 1. Query events (by date range, type)
    ▼
JSON Response
    │
    │ 2. Parse and transform
    ▼
Event Object
    │
    │ 3. Check blacklist
    │ 4. Check existing (by reservation_id)
    ▼
DatabaseManager
    │
    │ 5. Insert/update event
    ▼
calendar_events table
    │
    │ 6. Queue for sync
    ▼
CalendarWriter
    │
    │ 7. Create/update in Google Calendar
    ▼
Google Calendar API
```

### Event Deletion Flow

```
User deletes event in Google Calendar
    │
    │ 1. Manual deletion via UI
    ▼
Google Calendar (event gone)
    │
    │ 2. CalendarScanner runs
    ▼
CalendarScanner
    │
    │ 3. Compare DB vs Calendar
    │ 4. Detect event missing
    ▼
DatabaseManager
    │
    │ 5. Mark event deleted_at
    │ 6. Add to blacklist (optional)
    ▼
calendar_events (soft delete)
event_blacklist (permanent block)
    │
    │ 7. Prevent recreation
    ▼
Future 25Live syncs skip this event
```

## Error Handling

### Retry Strategy

Components use exponential backoff for transient errors:

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        result = api_call()
        break
    except TransientError as e:
        if attempt == max_retries - 1:
            raise
        sleep(2 ** attempt)  # 1s, 2s, 4s
```

### Failure Modes

| Error Type | Strategy | Recovery |
|------------|----------|----------|
| Database connection lost | Retry with backoff | Reconnect on next cycle |
| Google API rate limit | Exponential backoff | Resume after delay |
| 25Live auth failure | Re-authenticate | Cache new session |
| Conflict (duplicate) | Skip/update | Log and continue |
| Network timeout | Retry | Resume from checkpoint |

## Performance Considerations

### Database Optimization
- **Indexes:** Strategic indexes on frequently queried fields
- **Connection Pooling:** Reuse connections across requests
- **Batch Operations:** Insert/update multiple events in transactions
- **JSONB Metadata:** Efficient storage and querying of flexible data

### API Rate Limiting
- **Google Calendar:** ~600 queries/minute per user
- **25Live:** Session-based, respects institution limits
- **Batching:** Group operations to minimize API calls

### Caching Strategy
- **Event Signatures:** Cache to avoid redundant DB lookups
- **Calendar Lists:** Cache calendar metadata
- **Credentials:** Cache service account tokens (1-hour expiry)

## Security Architecture

### Credential Storage
```
~/.config/calpal/
├── service-account-key.json    # Google service account (600)
├── 25live_credentials          # 25Live username/password (600)
└── db_credentials              # Database password (600)
```

### Access Control
- **Database:** User `calpal` with minimal required permissions
- **Google Calendar:** Service account with domain delegation
- **25Live:** Read-only API credentials where possible
- **ICS Server:** Token-based authentication, secure endpoints

### Data Protection
- **At Rest:** Database encryption via PostgreSQL
- **In Transit:** HTTPS for all API calls
- **Sensitive Fields:** JSONB metadata can be encrypted
- **Logging:** Sanitize logs (no passwords, minimal PII)

## Monitoring & Observability

### Logging
```
logs/
├── calpal.log              # Main service log
├── 25live_sync.log         # 25Live component
├── calendar_scanner.log    # Scanner component
└── errors.log              # All errors centralized
```

### Metrics to Monitor
- Event sync success rate
- API error rates
- Database query performance
- Queue depths (if using task queues)
- ICS generation time

### Health Checks
```python
def health_check():
    checks = {
        'database': test_db_connection(),
        'google_api': test_google_connection(),
        '25live_api': test_25live_connection(),
        'ics_files': verify_ics_freshness()
    }
    return all(checks.values())
```

## Deployment Architecture

### Production Setup

```
┌─────────────────────────────────────────────┐
│              Load Balancer/Reverse Proxy     │
│              (nginx with SSL)                │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────┐         ┌─────────────┐
│  CalPal     │         │  ICS Server │
│  Sync       │         │  (Flask)    │
│  Service    │         └─────────────┘
└─────────────┘
    │
    │ PostgreSQL Connection
    ▼
┌─────────────────────┐
│   PostgreSQL DB     │
│   (Primary)         │
│   ┌───────────┐     │
│   │ Replicas  │     │ (optional)
│   └───────────┘     │
└─────────────────────┘
```

### High Availability
- **Database:** PostgreSQL replication (primary + read replicas)
- **Application:** Multiple CalPal instances with coordination
- **ICS Server:** Multiple Flask instances behind load balancer

## Extension Points

### Adding New Event Sources
1. Create new sync component in `calpal/sync/`
2. Implement event fetching and transformation
3. Use `DatabaseManager` for storage
4. Register with `UnifiedSyncService`

### Custom Event Processing
1. Create processor in `calpal/organizers/`
2. Define routing logic or transformations
3. Hook into event lifecycle
4. Update database accordingly

### Custom ICS Filters
1. Edit `calpal/generators/ics_generator.py`
2. Add filter methods
3. Update `should_include_event()` logic
4. Customize `transform_event()` for privacy

## Further Reading

- [Getting Started Guide](getting-started.md) - Setup instructions
- [Configuration Reference](configuration.md) - All config options
- [API Reference](api-reference.md) - Developer documentation
- [Security Guide](security.md) - Security best practices
