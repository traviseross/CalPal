# CalPal - Simplified Calendar Automation System

**Personal calendar management system for Travis Ross**

Automatically syncs 25Live events and personal calendar to a unified Google Calendar with color-coded visual organization.

---

## Architecture Overview

```
┌─────────────────┐
│   25Live API    │
└────────┬────────┘
         │
         v
┌─────────────────────────────────────────────┐
│         Database (PostgreSQL)               │
│  - Event tracking                           │
│  - Deletion history (prevents re-creation)  │
│  - Metadata storage                         │
└────────┬────────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────────┐
│   Google Calendar: tross@georgefox.edu      │
│                                              │
│  Color-coded events:                        │
│  🟡 Classes (Yellow)                        │
│  🔵 GFU Events (Blue)                       │
│  🟠 Appointments (Orange)                   │
│  🔴 Personal (Red)                          │
└────────┬────────────────────────────────────┘
         │
         v
┌─────────────────────────────────────────────┐
│         ICS Feed (Wife Calendar)            │
│  - Filtered & anonymized event feed         │
│  - Includes work + personal events          │
└─────────────────────────────────────────────┘
```

---

## Current Services

**Running**: `simplified_sync_service.py` (systemd service: `calpal.service`)

### Components

1. **25Live Sync** (every 30 minutes)
   - Fetches classes and GFU events from 25Live
   - Creates directly on `tross@georgefox.edu` with colors
   - Respects deletion history (won't recreate deleted events)
   - Applies event blacklist

2. **Personal Mirror** (every 10 minutes)
   - Mirrors `travis.e.ross@gmail.com` → `tross@georgefox.edu`
   - Adds red color to personal events
   - Tracks mirrors in database

3. **ICS Generator** (every 5 minutes)
   - Generates filtered ICS feed for wife calendar
   - Anonymizes student appointments
   - Includes work + personal events
   - Excludes family calendar

---

## Color Coding

| Event Type | Color | Google Calendar ID |
|------------|-------|-------------------|
| Classes | 🟡 Yellow (Banana) | 5 |
| Appointments | 🟠 Orange (Tangerine) | 6 |
| GFU Events | 🔵 Blue (Blueberry) | 9 |
| Personal | 🔴 Red (Tomato) | 11 |

---

## Key Files

### Active Services
- `calpal/sync/simplified_sync_service.py` - Main service orchestrator
- `calpal/sync/twentyfive_live_sync.py` - 25Live → Work calendar sync
- `calpal/organizers/personal_mirror.py` - Personal → Work calendar mirror
- `calpal/generators/ics_generator.py` - ICS feed generator
- `calpal/sync/calendar_scanner.py` - Reads events from Google Calendar → Database

### Configuration
- `config.py` - Main configuration (calendars, paths, database)
- `.config/systemd/user/calpal.service` - Service definition

### Data Files
- `data/work_subcalendars.json` - Subcalendar IDs (legacy, still referenced)
- `data/event_blacklist.json` - Events to never create
- `private/25live_queries.json` - 25Live API queries

---

## Database Schema

**Table**: `calendar_events`

Key fields:
- `event_id` - Google Calendar event ID
- `ical_uid` - iCalendar UID
- `summary`, `description`, `location` - Event details
- `start_time`, `end_time`, `is_all_day` - Timing
- `source_calendar`, `current_calendar` - Location tracking
- `event_type` - Type classification
- `deleted_at` - Soft delete timestamp (prevents re-creation)
- `status` - active/deleted
- `metadata` - JSON field for extended data

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- PostgreSQL database
- Google Calendar API credentials (service account)
- 25Live API credentials

### Service Management

```bash
# Status
systemctl --user status calpal.service

# Logs
tail -f ~/CalPal/logs/unified_service.log

# Restart
systemctl --user restart calpal.service

# Stop
systemctl --user stop calpal.service

# Start
systemctl --user start calpal.service
```

### Run Components Manually

```bash
# 25Live sync
python3 -m calpal.sync.twentyfive_live_sync

# Personal mirror
python3 -m calpal.organizers.personal_mirror

# ICS generator
python3 -m calpal.generators.ics_generator

# Service (one cycle)
python3 -m calpal.sync.simplified_sync_service --run-once
```

---

## What Changed (v2.0 Simplification)

### Removed (Archived)
- ❌ Subcalendar mirroring system
- ❌ Mirror reconciliation/orphan detection
- ❌ Unified calendar writer
- ❌ Complex event lifecycle management
- ❌ ~2000 lines of mirroring code

### New Approach
- ✅ Single calendar with color coding
- ✅ Direct writes to `tross@georgefox.edu`
- ✅ Database as historical record
- ✅ Simpler, more maintainable
- ✅ User deletes are final (no resurrection)

**See**: `ARCHITECTURE_SIMPLIFICATION.md` for full migration details

---

## Archived Code

Old mirroring system preserved in:
- `archive/old_mirroring_system/` - Original multi-calendar architecture
- `archive/test_scripts/` - Migration and testing tools

---

## Troubleshooting

### Events not syncing from 25Live
1. Check service logs: `tail -f ~/CalPal/logs/unified_service.log`
2. Verify 25Live credentials: `cat ~/.config/calpal/25live_credentials`
3. Test manually: `python3 -m calpal.sync.twentyfive_live_sync`

### Personal events not mirroring
1. Check personal calendar ID in config
2. Verify service account has access to `travis.e.ross@gmail.com`
3. Test manually: `python3 -m calpal.organizers.personal_mirror`

### ICS feed not updating
1. Check ICS file exists: `ls -lh ~/CalPal/private/schedule.ics`
2. Check Flask server: `pgrep -f calpal_flask_server`
3. Test manually: `python3 -m calpal.generators.ics_generator`

### Deleted events keep coming back
- This should no longer happen! The system tracks `deleted_at` in database
- If it does, check logs for "Skipping previously deleted event"

---

## Security Notes

- Service account credentials in `~/.config/calpal/service-account-key.json`
- 25Live credentials in `~/.config/calpal/25live_credentials`
- Database password in environment variable `DATABASE_URL`
- ICS feed secured with random endpoint path
- **Never commit credentials to git**

---

## Development

### Adding a new event source
1. Create a sync module in `calpal/sync/`
2. Add color mapping to event creation
3. Register in `simplified_sync_service.py`
4. Update this README

### Modifying colors
Update `calpal/sync/twentyfive_live_sync.py` or `calpal/organizers/personal_mirror.py`

Google Calendar color IDs:
1=Lavender, 2=Sage, 3=Grape, 4=Flamingo, 5=Banana,
6=Tangerine, 7=Peacock, 8=Graphite, 9=Blueberry, 10=Basil, 11=Tomato

---

## License

Personal project - not licensed for public use.

---

**Last Updated**: October 15, 2025
**Version**: 2.0 (Simplified Architecture)
