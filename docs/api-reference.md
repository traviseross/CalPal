# API Reference

Developer reference for CalPal modules and classes.

## Core Module (`calpal.core`)

### DatabaseManager

Primary database interface for all CalPal components.

```python
from calpal.core.db_manager import DatabaseManager

db = DatabaseManager()
```

#### Methods

**`get_connection()`**
```python
conn = db.get_connection()
# Returns: psycopg2 connection object
```

**`add_event(event_data, calendar_id, action='created')`**
```python
db.add_event(
    event_data={
        'id': 'event123',
        'summary': 'Meeting',
        'start': datetime(2025, 10, 7, 10, 0),
        'end': datetime(2025, 10, 7, 11, 0),
        'ical_uid': 'unique-id@domain.com'
    },
    calendar_id='work@example.edu',
    action='created'
)
# Returns: bool (success)
```

**`get_events(calendar_id=None, start_date=None, end_date=None, include_deleted=False)`**
```python
events = db.get_events(
    calendar_id='work@example.edu',
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 10, 31),
    include_deleted=False
)
# Returns: list of event dictionaries
```

**`mark_event_deleted(event_id, calendar_id)`**
```python
db.mark_event_deleted('event123', 'work@example.edu')
# Returns: bool (success)
```

**`add_to_blacklist(ical_uid, calendar_id, reason=None)`**
```python
db.add_to_blacklist(
    ical_uid='unique-id@domain.com',
    calendar_id='work@example.edu',
    reason='Manually deleted by user'
)
# Returns: bool (success)
```

**`is_blacklisted(ical_uid, calendar_id)`**
```python
is_blocked = db.is_blacklisted('unique-id@domain.com', 'work@example.edu')
# Returns: bool
```

## Sync Module (`calpal.sync`)

### TwentyFiveLiveSync

Synchronize events from 25Live to database.

```python
from calpal.sync.twentyfive_live_sync import DBAware25LiveSync

sync = DBAware25LiveSync()
```

#### Methods

**`sync_classes(start_date, end_date)`**
```python
sync.sync_classes(
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 10, 31)
)
# Returns: dict with sync statistics
```

**`sync_events(start_date, end_date)`**
```python
stats = sync.sync_events(
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 10, 31)
)
# Returns: {'added': 10, 'updated': 5, 'skipped': 2}
```

### CalendarScanner

Scan Google Calendars for changes and deletions.

```python
from calpal.sync.calendar_scanner import CalendarScanner

scanner = CalendarScanner()
```

#### Methods

**`scan_calendar(calendar_id, start_date=None, end_date=None)`**
```python
results = scanner.scan_calendar(
    calendar_id='work@example.edu',
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 10, 31)
)
# Returns: dict with scan results
```

**`detect_deletions(calendar_id)`**
```python
deleted = scanner.detect_deletions('work@example.edu')
# Returns: list of deleted event IDs
```

**`cleanup_deleted_events(calendar_id)`**
```python
scanner.cleanup_deleted_events('work@example.edu')
# Returns: int (number of events cleaned up)
```

## Organizers Module (`calpal.organizers`)

### EventOrganizer

Route events to appropriate subcalendars.

```python
from calpal.organizers.event_organizer import WorkEventOrganizer

organizer = WorkEventOrganizer()
```

#### Methods

**`organize_events()`**
```python
stats = organizer.organize_events()
# Returns: {'organized': 15, 'skipped': 3}
```

**`determine_target_calendar(event)`**
```python
target = organizer.determine_target_calendar(event)
# Returns: str (calendar name like 'Classes', 'Meetings')
```

### MirrorManager

Mirror events between calendars.

```python
from calpal.organizers.mirror_manager import PersonalFamilyMirror

mirror = PersonalFamilyMirror()
```

#### Methods

**`sync_mirrors()`**
```python
stats = mirror.sync_mirrors()
# Returns: {'created': 5, 'updated': 2, 'deleted': 1}
```

**`create_mirror(source_event, target_calendar)`**
```python
mirror_event = mirror.create_mirror(
    source_event=event,
    target_calendar='work@example.edu'
)
# Returns: dict (mirror event data)
```

### Reconciler

Reconcile database with Google Calendar state.

```python
from calpal.organizers.reconciler import WorkCalendarReconciler

reconciler = WorkCalendarReconciler()
```

#### Methods

**`reconcile(calendar_id)`**
```python
results = reconciler.reconcile('work@example.edu')
# Returns: {'fixed': 3, 'conflicts': 1}
```

## Generators Module (`calpal.generators`)

### ICSGenerator

Generate ICS files from database.

```python
from calpal.generators.ics_generator import DBWifeICSGenerator

generator = DBWifeICSGenerator()
```

#### Methods

**`generate_ics(output_path=None)`**
```python
ics_path = generator.generate_ics(output_path='private/schedule.ics')
# Returns: str (path to generated ICS file)
```

**`should_include_event(event)`**
```python
include = generator.should_include_event(event)
# Returns: bool
# Override this method to customize filtering
```

**`transform_event(event)`**
```python
transformed = generator.transform_event(event)
# Returns: dict (transformed event)
# Override this method to customize event formatting
```

### ICSServer

Flask web server for ICS hosting.

```python
from calpal.generators.ics_server import app

app.run(host='0.0.0.0', port=5001)
```

## Utility Functions

### Event Signature Generation

```python
from calpal.core.db_manager import generate_event_signature

signature = generate_event_signature(event)
# Returns: str (unique signature for deduplication)
```

### Date Utilities

```python
from calpal.sync.calendar_scanner import get_date_range

start, end = get_date_range(lookback_days=30, lookahead_days=365)
# Returns: tuple of datetime objects
```

## Data Models

### Event Dictionary

Standard event format used throughout CalPal:

```python
event = {
    'id': 'google_event_id',
    'ical_uid': 'unique-id@domain.com',
    'summary': 'Event Title',
    'description': 'Event Description',
    'start': datetime(2025, 10, 7, 10, 0),
    'end': datetime(2025, 10, 7, 11, 0),
    'location': 'Room 123',
    'event_type': 'meeting',  # 'class', 'meeting', 'appointment', etc.
    'current_calendar': 'work@example.edu',
    'metadata': {
        'source': '25live',
        'reservation_id': '12345',
        'source_event_id': 'original_event_id'  # For mirrors
    }
}
```

### Database Event Record

Fields in `calendar_events` table:

```python
{
    'event_id': str,           # Primary key
    'current_calendar': str,   # Calendar ID
    'ical_uid': str,           # iCalendar UID
    'summary': str,
    'description': str,
    'start_time': datetime,
    'end_time': datetime,
    'location': str,
    'event_type': str,
    'metadata': dict,          # JSONB field
    'created_at': datetime,
    'updated_at': datetime,
    'deleted_at': datetime,    # NULL if not deleted
    'last_action': str         # 'created', 'moved', 'deleted', etc.
}
```

## Extending CalPal

### Creating a Custom Sync Source

```python
from calpal.core.db_manager import DatabaseManager

class CustomSync:
    def __init__(self):
        self.db = DatabaseManager()
        self.logger = logging.getLogger('custom-sync')

    def sync_events(self, start_date, end_date):
        # 1. Fetch events from your source
        events = self.fetch_from_source(start_date, end_date)

        # 2. Transform to CalPal format
        for event in events:
            event_data = self.transform_event(event)

            # 3. Check if blacklisted
            if self.db.is_blacklisted(event_data['ical_uid'], calendar_id):
                continue

            # 4. Add to database
            self.db.add_event(event_data, calendar_id, action='synced')

        return {'synced': len(events)}
```

### Custom Event Filter

```python
from calpal.generators.ics_generator import DBWifeICSGenerator

class CustomICSGenerator(DBWifeICSGenerator):
    def should_include_event(self, event):
        # Custom filtering logic
        if event['event_type'] == 'private':
            return False
        if 'confidential' in event['summary'].lower():
            return False
        return True

    def transform_event(self, event):
        # Custom transformation
        if event['event_type'] == 'meeting':
            event['summary'] = f"Meeting: {event['summary']}"
        return event
```

## Error Handling

### Exception Classes

```python
from calpal.core.exceptions import (
    DatabaseError,
    GoogleCalendarError,
    TwentyFiveLiveError
)

try:
    db.add_event(event_data, calendar_id)
except DatabaseError as e:
    logger.error(f"Database error: {e}")
except GoogleCalendarError as e:
    logger.error(f"Google Calendar API error: {e}")
```

### Retry Patterns

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def sync_with_retry():
    sync.sync_events(start_date, end_date)
```

## Testing

### Mocking Database

```python
from unittest.mock import MagicMock

db = MagicMock(spec=DatabaseManager)
db.add_event.return_value = True
db.get_events.return_value = [mock_event]
```

### Test Utilities

```python
from calpal.test.utils import create_mock_event, create_mock_db

event = create_mock_event(summary='Test Event')
db = create_mock_db()
```

## Further Reading

- [Architecture Guide](architecture.md) - System design details
- [Configuration Reference](configuration.md) - All configuration options
- [Getting Started](getting-started.md) - Setup and usage
