# CalPal Services Documentation

Complete reference for all CalPal service components and their APIs.

## Table of Contents

- [Service Overview](#service-overview)
- [Unified Service](#unified-service)
- [Database Manager](#database-manager)
- [25Live Sync Service](#25live-sync-service)
- [Calendar Scanner](#calendar-scanner)
- [Work Event Organizer](#work-event-organizer)
- [Personal/Family Mirror](#personal-family-mirror)
- [Subcalendar Sync](#subcalendar-sync)
- [ICS Generator](#ics-generator)
- [Flask Web Server](#flask-web-server)
- [Service Dependencies](#service-dependencies)
- [Troubleshooting](#troubleshooting)

## Service Overview

CalPal consists of multiple coordinated services that work together to sync, organize, and publish calendar events.

### Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Unified CalPal Service Coordinator            │
│                (unified_db_calpal_service.py)           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │   25Live Sync    │  │  Calendar        │            │
│  │   (30 min)       │  │  Scanner         │            │
│  │                  │  │  (15 min)        │            │
│  └────────┬─────────┘  └─────────┬────────┘            │
│           │                       │                      │
│           └───────────┬───────────┘                     │
│                       ▼                                  │
│           ┌────────────────────┐                        │
│           │  PostgreSQL DB     │                        │
│           │  Event Tracking    │                        │
│           └────────┬───────────┘                        │
│                    │                                     │
│        ┌───────────┼───────────┐                        │
│        │           │           │                         │
│        ▼           ▼           ▼                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                   │
│  │Personal │ │  Work   │ │Subcal   │                    │
│  │Mirror   │ │Organizer│ │Sync     │                    │
│  │(10 min) │ │(5 min)  │ │(10 min) │                    │
│  └────┬────┘ └────┬────┘ └────┬────┘                    │
│       │           │           │                          │
│       └───────────┼───────────┘                         │
│                   ▼                                      │
│         ┌──────────────────┐                            │
│         │  ICS Generator   │                            │
│         │  (5 min)         │                            │
│         └─────────┬────────┘                            │
│                   │                                      │
│                   ▼                                      │
│         ┌──────────────────┐                            │
│         │  Flask Server    │                            │
│         │  (continuous)    │                            │
│         └──────────────────┘                            │
└─────────────────────────────────────────────────────────┘
```

### Service Responsibilities

| Service | Responsibility | Input | Output | Run Frequency |
|---------|---------------|-------|--------|---------------|
| **Unified Service** | Coordinates all components | Config | Logs, metrics | Continuous |
| **Database Manager** | Database operations | SQL queries | Query results | On-demand |
| **25Live Sync** | Pull events from 25Live API | 25Live API | Database records | 30 minutes |
| **Calendar Scanner** | Scan Google Calendars | Google API | Database records | 15 minutes |
| **Work Organizer** | Sort/move work events | Database | Updated events | 5 minutes |
| **Personal Mirror** | Mirror personal/family | Google API | Mirror events | 10 minutes |
| **Subcalendar Sync** | Sync subcalendars to work | Database | Mirror events | 10 minutes |
| **ICS Generator** | Generate ICS files | Database | ICS file | 5 minutes |
| **Flask Server** | Serve ICS via HTTP | HTTP requests | ICS data | Continuous |

## Unified Service

**File:** `src/unified_db_calpal_service.py`

The unified service coordinates all CalPal components in a single process with scheduled intervals.

### Features

- **Centralized Coordination**: Single entry point for all services
- **Interval-Based Execution**: Each component runs on its own schedule
- **Lazy Loading**: Components initialized only when needed
- **Graceful Shutdown**: Handles signals (SIGINT, SIGTERM)
- **Error Resilience**: Component failures don't crash entire system

### Usage

```bash
# Start unified service
python3 src/unified_db_calpal_service.py

# With logging
python3 src/unified_db_calpal_service.py --log-level DEBUG

# Run once (no loop)
python3 src/unified_db_calpal_service.py --once

# Run specific components only
python3 src/unified_db_calpal_service.py --ics-only
```

### Configuration

```python
# Component intervals (in config.py or service file)
self.intervals = {
    '25live_sync': 30 * 60,       # 30 minutes
    'calendar_scan': 15 * 60,     # 15 minutes
    'personal_family': 10 * 60,   # 10 minutes
    'work_organizer': 5 * 60,     # 5 minutes
    'subcalendar_sync': 10 * 60,  # 10 minutes
    'wife_ics': 5 * 60            # 5 minutes
}
```

### API

```python
from src.unified_db_calpal_service import UnifiedCalPalService

# Initialize service
service = UnifiedCalPalService()

# Run continuous loop
service.run()

# Run single iteration
service.run_once()

# Check if component should run
should_run = service.should_run('25live_sync')

# Run specific component
service.run_component('calendar_scan')
```

## Database Manager

**File:** `src/db_manager.py`

Handles all database operations for event tracking.

### Features

- **Connection Pooling**: Efficient connection reuse
- **Context Managers**: Safe session handling
- **Upsert Operations**: Insert or update in single operation
- **Soft Deletes**: Mark records deleted without physical removal
- **Query Helpers**: Common queries as methods

### Usage

```python
from src.db_manager import DatabaseManager

# Initialize
db = DatabaseManager()

# Test connection
if db.test_connection():
    print("Database connected")

# Record an event
event_data = {
    'event_id': 'abc123',
    'current_calendar': 'user@example.edu',
    'summary': 'Meeting',
    'start_time': datetime.now(),
    'end_time': datetime.now() + timedelta(hours=1),
    'event_type': 'manual',
    'status': 'active'
}
db.record_event(event_data)

# Get event
event = db.get_event_by_id('abc123', 'user@example.edu')

# Mark as deleted
db.mark_as_deleted('abc123', 'user@example.edu')

# Get statistics
stats = db.get_stats()
print(f"Total events: {stats['total_events']}")
```

### API Reference

#### Connection Management

```python
# Test database connection
db.test_connection() -> bool

# Get database session (context manager)
with db.get_session() as session:
    # Use session
    pass
```

#### Event Operations

```python
# Record/update event (upsert)
db.record_event(event_data: Dict) -> None

# Get event by ID
db.get_event_by_id(event_id: str, calendar_id: str) -> Optional[Dict]

# Get event by 25Live reservation ID
db.get_event_by_25live_id(reservation_id: str, calendar_id: str) -> Optional[Dict]

# Get event by iCal UID
db.get_event_by_ical_uid(ical_uid: str) -> List[Dict]

# Mark event as deleted (soft delete)
db.mark_as_deleted(event_id: str, calendar_id: str) -> None

# Update event status
db.update_event_status(event_id: str, calendar_id: str, status: str) -> None
```

#### Bulk Operations

```python
# Get all events for a calendar
db.get_calendar_events(calendar_id: str, active_only: bool = True) -> List[Dict]

# Mark multiple events deleted
db.mark_multiple_deleted(event_ids: List[str], calendar_id: str) -> int

# Get events not seen since timestamp
db.get_stale_events(since: datetime, calendar_id: str = None) -> List[Dict]
```

#### Statistics

```python
# Get database statistics
db.get_stats() -> Dict

# Returns:
{
    'total_events': int,
    'active_events': int,
    'deleted_events': int,
    'events_by_calendar': Dict[str, int],
    'events_by_type': Dict[str, int]
}
```

## 25Live Sync Service

**File:** `src/db_aware_25live_sync.py`

Syncs events from CollegeNET 25Live into the CalPal database.

### Features

- **API Integration**: Connects to 25Live REST API
- **Date Range Batching**: Handles 25Live's 20-week limit
- **Duplicate Prevention**: Uses reservation IDs for deduplication
- **Event Classification**: Identifies classes vs. events
- **Incremental Sync**: Only processes new/changed events

### Usage

```bash
# Run sync
python3 src/db_aware_25live_sync.py

# With debug logging
python3 src/db_aware_25live_sync.py --log-level DEBUG

# Custom date range
python3 src/db_aware_25live_sync.py --start-date 2025-01-01 --end-date 2025-12-31

# Dry run (no database changes)
python3 src/db_aware_25live_sync.py --dry-run
```

### Configuration

```python
# In config.py
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'
TWENTYFIVE_LIVE_CREDENTIALS_FILE = '~/.config/calpal/25live_credentials'

CALENDAR_MAPPINGS = {
    'Classes': 'classes-calendar-id@group.calendar.google.com',
    'Events': 'events-calendar-id@group.calendar.google.com'
}
```

### API

```python
from src.db_aware_25live_sync import DBAware25LiveSync

# Initialize
sync = DBAware25LiveSync()

# Sync all configured calendars
results = sync.sync_all()

# Sync specific calendar type
results = sync.sync_calendar_type('Classes')

# Check for deleted events
deleted = sync.detect_deletions()
```

### Event Data Structure

Events synced from 25Live include:

```python
{
    'event_id': str,              # Google Calendar ID
    'current_calendar': str,      # Target calendar ID
    'summary': str,               # Event title
    'description': str,           # Event description
    'location': str,              # Event location
    'start_time': datetime,       # Start timestamp
    'end_time': datetime,         # End timestamp
    'event_type': '25live_class' | '25live_event',
    'status': 'active',
    'metadata': {
        '25live_reservation_id': str,
        '25live_event_id': str,
        'calendar_type': str
    }
}
```

## Calendar Scanner

**File:** `src/calendar_scanner.py`

Scans Google Calendars to detect changes and deletions.

### Features

- **Multi-Calendar Scanning**: Scans all configured calendars
- **Change Detection**: Identifies new, updated, and deleted events
- **Last-Seen Tracking**: Updates `last_seen_at` for active events
- **Deletion Detection**: Marks events deleted if not found
- **Attendee Event Handling**: Tracks RSVP status

### Usage

```bash
# Scan all calendars
python3 src/calendar_scanner.py

# Scan specific calendar
python3 src/calendar_scanner.py --calendar user@example.edu

# With verbose output
python3 src/calendar_scanner.py --log-level DEBUG

# Dry run
python3 src/calendar_scanner.py --dry-run
```

### API

```python
from src.calendar_scanner import CalendarScanner

# Initialize
scanner = CalendarScanner()

# Scan all calendars
results = scanner.scan_all_calendars()

# Scan specific calendar
results = scanner.scan_calendar('user@example.edu')

# Detect deletions
deletions = scanner.detect_deletions('user@example.edu')
```

### Scan Results

```python
{
    'calendar_id': str,
    'events_scanned': int,
    'events_new': int,
    'events_updated': int,
    'events_deleted': int,
    'scan_time': float,  # seconds
    'errors': List[str]
}
```

## Work Event Organizer

**File:** `src/work_event_organizer.py`

Organizes events in the work calendar by moving them to appropriate subcalendars.

### Features

- **Booking Detection**: Identifies appointment/booking events
- **Meeting Detection**: Identifies meeting invitations
- **Event Moving**: Moves events to correct subcalendars
- **Mirror Creation**: Creates mirror copies in work calendar
- **Duplicate Prevention**: Tracks moved events

### Usage

```bash
# Organize work events
python3 src/work_event_organizer.py

# Dry run (show what would be moved)
python3 src/work_event_organizer.py --dry-run

# Verbose output
python3 src/work_event_organizer.py --log-level DEBUG
```

### Configuration

```python
# Booking patterns
BOOKING_PATTERNS = [
    'meet with',
    'booked by',
    'appointment'
]

# Target subcalendars
SUBCALENDARS = {
    'Appointments': 'appointments-id@group.calendar.google.com',
    'Meetings': 'meetings-id@group.calendar.google.com'
}
```

### API

```python
from src.work_event_organizer import WorkEventOrganizer

# Initialize
organizer = WorkEventOrganizer()

# Organize all events
results = organizer.organize_work_events()

# Move bookings only
results = organizer.move_booking_events()

# Move meeting invitations
results = organizer.move_meeting_invitations()
```

## Personal/Family Mirror

**File:** `src/personal_family_mirror.py`

Mirrors personal and family calendar events to work calendar subcalendars.

### Features

- **Selective Mirroring**: Only mirrors future events
- **Privacy Protection**: Can anonymize event details
- **Two-Way Sync**: Updates mirrors when source changes
- **Deletion Handling**: Removes mirrors when source deleted
- **Do-Not-Mirror Flag**: Respects user deletions

### Usage

```bash
# Mirror personal/family events
python3 src/personal_family_mirror.py

# Mirror personal only
python3 src/personal_family_mirror.py --personal-only

# Mirror family only
python3 src/personal_family_mirror.py --family-only

# Dry run
python3 src/personal_family_mirror.py --dry-run
```

### Configuration

```python
# Source calendars
PERSONAL_CALENDAR_ID = 'personal@gmail.com'
FAMILY_CALENDAR_ID = 'family@group.calendar.google.com'

# Mirror subcalendars
SUBCALENDARS = {
    'Personal Mirror': 'personal-mirror@group.calendar.google.com',
    'Family Mirror': 'family-mirror@group.calendar.google.com'
}

# Privacy settings
ANONYMIZE_MIRRORS = False  # Set True to hide details
```

### API

```python
from src.personal_family_mirror import PersonalFamilyMirror

# Initialize
mirror = PersonalFamilyMirror()

# Mirror personal calendar
results = mirror.mirror_personal_calendar()

# Mirror family calendar
results = mirror.mirror_family_calendar()

# Mirror both
results = mirror.mirror_all()

# Clean up deleted sources
mirror.cleanup_orphaned_mirrors()
```

## Subcalendar Sync

**File:** `src/subcalendar_work_sync.py`

Ensures events in subcalendars are also mirrored to the main work calendar.

### Features

- **Multi-Source Aggregation**: Combines events from multiple subcalendars
- **Work Calendar Mirror**: Creates copies in main work calendar
- **Sync State Tracking**: Tracks which events are synced
- **Update Propagation**: Updates work calendar when subcalendar changes

### Usage

```bash
# Sync subcalendars to work
python3 src/subcalendar_work_sync.py

# Sync specific subcalendar
python3 src/subcalendar_work_sync.py --calendar appointments-id@group.calendar.google.com

# Verbose output
python3 src/subcalendar_work_sync.py --log-level DEBUG
```

### API

```python
from src.subcalendar_work_sync import SubcalendarWorkSync

# Initialize
sync = SubcalendarWorkSync()

# Sync all subcalendars
results = sync.sync_all_subcalendars()

# Sync specific subcalendar
results = sync.sync_subcalendar('appointments-id@group.calendar.google.com')
```

## ICS Generator

**File:** `src/db_aware_wife_ics_generator.py`

Generates ICS calendar files from database events with custom filtering and formatting.

### Features

- **Database-Driven**: Reads events from PostgreSQL
- **Event Filtering**: Excludes personal/filtered events
- **Event Transformation**: Customizes summary/location/description
- **Privacy Protection**: Hides sensitive details
- **Metadata Tracking**: Stores generation metadata

### Usage

```bash
# Generate ICS file
python3 src/db_aware_wife_ics_generator.py

# With debug output
python3 src/db_aware_wife_ics_generator.py --log-level DEBUG

# Custom output path
python3 src/db_aware_wife_ics_generator.py --output /path/to/calendar.ics
```

### Configuration

```python
# ICS output file
ICS_FILE_PATH = 'private/calendar.ics'

# Transformation rules
ICS_RULES = {
    '25live_class': {
        'summary': 'In class',
        'location': None,  # Hide
        'description': None  # Hide
    },
    'booking': {
        'summary': 'In a meeting',
        'location': True,  # Show
        'description': None  # Hide
    }
}

# Calendars to exclude
EXCLUDED_CALENDARS = [
    'personal@gmail.com',
    'family@group.calendar.google.com'
]
```

### API

```python
from src.db_aware_wife_ics_generator import DBWifeICSGenerator

# Initialize
generator = DBWifeICSGenerator()

# Generate ICS file
generator.generate_ics()

# Get events for ICS
events = generator.get_events_for_ics()

# Transform event
transformed = generator.transform_event(event)
```

### ICS Output Format

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CalPal//Calendar Sync//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Work Schedule
X-WR-TIMEZONE:America/Los_Angeles

BEGIN:VEVENT
UID:abc123@google.com
DTSTART:20251004T090000Z
DTEND:20251004T100000Z
SUMMARY:In class
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT

END:VCALENDAR
```

## Flask Web Server

**File:** `src/calpal_flask_server.py`

Web server for serving ICS files via HTTP with token authentication.

### Features

- **Secure Endpoints**: Token-based authentication
- **ICS Serving**: Delivers calendar files via HTTP
- **Auto-Refresh**: Serves latest generated ICS
- **CORS Support**: Allows cross-origin requests
- **Health Checks**: Provides status endpoint

### Usage

```bash
# Start server
python3 src/calpal_flask_server.py

# Custom port
python3 src/calpal_flask_server.py --port 8080

# Debug mode
python3 src/calpal_flask_server.py --debug

# Custom host
python3 src/calpal_flask_server.py --host 0.0.0.0 --port 5001
```

### Configuration

```python
# Server settings
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5001

# Security
SECURE_ENDPOINT_PATH = 'your-random-path'
ACCESS_TOKEN = 'your-access-token'

# ICS file
ICS_FILE_PATH = 'private/calendar.ics'
```

### Endpoints

**GET /health**
```bash
curl http://localhost:5001/health

# Response:
{"status": "ok", "ics_file_exists": true, "last_modified": "2025-10-04T10:30:00"}
```

**GET /{SECURE_ENDPOINT_PATH}/calendar.ics?token={ACCESS_TOKEN}**
```bash
curl http://localhost:5001/your-random-path/calendar.ics?token=your-access-token

# Response: ICS calendar data
```

### API

```python
from src.calpal_flask_server import app

# Run server
app.run(host='0.0.0.0', port=5001)
```

## Service Dependencies

### Dependency Graph

```
Unified Service
    ├─> Database Manager (required)
    ├─> 25Live Sync
    │   ├─> Database Manager
    │   └─> Google Calendar API
    ├─> Calendar Scanner
    │   ├─> Database Manager
    │   └─> Google Calendar API
    ├─> Work Organizer
    │   ├─> Database Manager
    │   └─> Google Calendar API
    ├─> Personal/Family Mirror
    │   ├─> Database Manager
    │   └─> Google Calendar API
    ├─> Subcalendar Sync
    │   ├─> Database Manager
    │   └─> Google Calendar API
    ├─> ICS Generator
    │   └─> Database Manager
    └─> Flask Server
        └─> ICS file
```

### Startup Order

When running as separate services:

1. **PostgreSQL Database** (via Docker)
2. **Database Manager** (verify connection)
3. **25Live Sync** (optional)
4. **Calendar Scanner** (initial scan)
5. **Work Organizer**
6. **Personal/Family Mirror**
7. **Subcalendar Sync**
8. **ICS Generator**
9. **Flask Server**

### Service Isolation

Services can run independently:

```bash
# Just ICS generation (no 25Live, no scanning)
python3 src/db_aware_wife_ics_generator.py

# Just calendar scanning (no 25Live)
python3 src/calendar_scanner.py

# Just web server (assumes ICS exists)
python3 src/calpal_flask_server.py
```

## Troubleshooting

### Common Issues

**Service won't start**
```bash
# Check database connection
python3 -c "from src.db_manager import DatabaseManager; db = DatabaseManager(); print(db.test_connection())"

# Check configuration
python3 -c "import config; print('Config loaded')"

# Check dependencies
pip install -r requirements.txt
```

**Service exits immediately**
```bash
# Check logs
tail -f logs/calpal.log
tail -f logs/errors.log

# Run with debug logging
python3 src/unified_db_calpal_service.py --log-level DEBUG
```

**Database errors**
```bash
# Verify database is running
docker compose ps
docker compose logs calpal_db

# Test connection
docker exec -it calpal_db psql -U calpal -d calpal_db -c "SELECT 1;"

# Check schema
docker exec -it calpal_db psql -U calpal -d calpal_db -c "\dt"
```

**Google API errors**
```bash
# Verify credentials
python3 << EOF
from google.oauth2.service_account import Credentials
creds = Credentials.from_service_account_file(
    '~/.config/calpal/service-account-key.json'
)
print(f"Service account: {creds.service_account_email}")
EOF

# Check calendar access
# Make sure service account has been granted access to calendars
```

**25Live API errors**
```bash
# Verify credentials
cat ~/.config/calpal/25live_credentials

# Test API connection
python3 << EOF
import requests
from requests.auth import HTTPBasicAuth
with open('~/.config/calpal/25live_credentials') as f:
    username = f.readline().strip()
    password = f.readline().strip()
url = 'https://25live.collegenet.com/your-institution/api/v1/spaces'
r = requests.get(url, auth=HTTPBasicAuth(username, password))
print(f"Status: {r.status_code}")
EOF
```

### Performance Issues

**Slow sync times**
```python
# Reduce batch sizes in config.py
GOOGLE_BATCH_SIZE = 50  # Instead of 100
SCAN_MAX_RESULTS = 1000  # Instead of 2500

# Increase intervals
SERVICE_INTERVALS = {
    '25live_sync': 60 * 60,   # Every hour
    'calendar_scan': 30 * 60,  # Every 30 min
}
```

**High memory usage**
```python
# Reduce connection pool size
DB_POOL_SIZE = 3  # Instead of 5
DB_MAX_OVERFLOW = 5  # Instead of 10

# Enable garbage collection
import gc
gc.collect()
```

**High CPU usage**
```python
# Add delays between operations
import time
time.sleep(0.1)  # 100ms delay

# Reduce concurrent operations
SCAN_PARALLEL_REQUESTS = 1  # Sequential instead of parallel
```

## Next Steps

- See [DATABASE.md](DATABASE.md) for database operations
- See [CONFIGURATION.md](CONFIGURATION.md) for configuration options
- See [SECURITY.md](SECURITY.md) for security best practices
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines
