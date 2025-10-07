# Legacy `src/` Directory Removed

**As of CalPal v2.0.0**, the `src/` directory has been completely removed for security reasons.

## Migration to `calpal/` Package

All code has been reorganized into the `calpal/` package structure:

### Old Location → New Location

- `src/db_manager.py` → `calpal/core/db_manager.py`
- `src/db_aware_25live_sync.py` → `calpal/sync/twentyfive_live_sync.py`
- `src/calendar_scanner.py` → `calpal/sync/calendar_scanner.py`
- `src/unified_db_calpal_service.py` → `calpal/sync/unified_sync_service.py`
- `src/unified_calendar_sync.py` → `calpal/sync/calendar_writer.py`
- `src/work_event_organizer.py` → `calpal/organizers/event_organizer.py`
- `src/personal_family_mirror.py` → `calpal/organizers/mirror_manager.py`
- `src/work_calendar_reconciler.py` → `calpal/organizers/reconciler.py`
- `src/subcalendar_work_sync.py` → `calpal/organizers/subcalendar_sync.py`
- `src/db_aware_wife_ics_generator.py` → `calpal/generators/ics_generator.py`
- `src/calpal_flask_server.py` → `calpal/generators/ics_server.py`
- `src/manage_event_blacklist.py` → `tools/manage_blacklist.py`

### Update Your Imports

**Old imports:**
```python
from src.db_manager import DatabaseManager
from src.calendar_scanner import CalendarScanner
```

**New imports:**
```python
from calpal.core.db_manager import DatabaseManager
from calpal.sync.calendar_scanner import CalendarScanner
```

### Run Services with New Paths

**Old:**
```bash
python3 src/unified_db_calpal_service.py
```

**New:**
```bash
python3 -m calpal.sync.unified_sync_service
```

## Why Was This Removed?

The `src/` directory contained:
- Hardcoded sensitive data (calendar IDs, service account emails)
- Unsanitized personal information
- Legacy code structure

For security and maintainability, all code has been moved to the proper `calpal/` package structure with complete data sanitization.

## Documentation

See the full migration guide in `CHANGELOG.md` or visit the documentation:
- [Getting Started](../docs/getting-started.md)
- [Architecture Guide](../docs/architecture.md)
- [API Reference](../docs/api-reference.md)
