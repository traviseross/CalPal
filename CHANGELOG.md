# Changelog

All notable changes to CalPal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2025-10-07

### 🎉 Public Release - Complete Repository Restructure

This major release restructures CalPal for public distribution with a proper Python package structure, comprehensive documentation, and complete removal of sensitive data.

### Added
- **New Package Structure** - Organized into proper Python package `calpal/`
  - `calpal.core` - Core database and infrastructure (DatabaseManager)
  - `calpal.sync` - Synchronization services (25Live, Calendar Scanner, Unified Sync)
  - `calpal.organizers` - Event organization logic (Event Organizer, Mirror Manager, Reconciler)
  - `calpal.generators` - ICS generation and web server
- **Configuration Templates** - Ready-to-use examples for new users
  - `config.example.py` - Main configuration template
  - `.env.example` - Environment variables template
  - `config/calendars.example.json` - Calendar ID mappings template
  - `config/25live_queries.example.json` - 25Live query configuration template
- **Comprehensive Documentation** in `docs/`
  - `getting-started.md` - Complete setup guide with prerequisites and installation
  - `architecture.md` - System design, components, and data flow diagrams
  - `api-reference.md` - Developer API documentation for all modules
  - `configuration.md` - Complete configuration reference
  - `security.md` - Security best practices and compliance guidelines
- **Enhanced .gitignore** - Comprehensive protection against committing sensitive data
  - Organized into sections: sensitive data, Python environment, build artifacts
  - Inline documentation explaining what each section protects
  - Security reminders and best practices
- **Tools Directory** - Utility scripts for maintenance
  - `tools/manage_blacklist.py` - Event blacklist management utility

### Changed
- **BREAKING: Import Structure** - All imports now use `calpal.` package prefix
  - Old: `from src.db_manager import DatabaseManager`
  - New: `from calpal.core.db_manager import DatabaseManager`
- **File Organization** - Renamed and reorganized for clarity
  - `db_aware_25live_sync.py` → `calpal/sync/twentyfive_live_sync.py`
  - `calendar_scanner.py` → `calpal/sync/calendar_scanner.py`
  - `unified_db_calpal_service.py` → `calpal/sync/unified_sync_service.py`
  - `unified_calendar_sync.py` → `calpal/sync/calendar_writer.py`
  - `work_event_organizer.py` → `calpal/organizers/event_organizer.py`
  - `personal_family_mirror.py` → `calpal/organizers/mirror_manager.py`
  - `work_calendar_reconciler.py` → `calpal/organizers/reconciler.py`
  - `subcalendar_work_sync.py` → `calpal/organizers/subcalendar_sync.py`
  - `db_aware_wife_ics_generator.py` → `calpal/generators/ics_generator.py`
  - `calpal_flask_server.py` → `calpal/generators/ics_server.py`
- **README.md** - Complete rewrite for public audience
  - Professional project description and features
  - Clear architecture diagrams
  - Updated directory structure
  - Installation instructions using new package structure
  - Links to new documentation
- **requirements.txt** - Enhanced with installation instructions and update guidelines

### Removed
- **Sensitive Data Sanitization** - Complete removal of private information
  - All personal email addresses removed
  - Real calendar IDs replaced with placeholders
  - Institution-specific references genericized
  - Hardcoded credentials removed
- **Obsolete Files** - Cleaned up 51+ deprecated files
  - Old troubleshooting scripts
  - Temporary test files
  - Archived debugging utilities
  - Generated reports and results
  - Legacy sync scripts
- **Old Documentation** - Replaced with clean, professional docs
  - Removed docs with embedded sensitive data

### Security
- **Complete Data Sanitization** - All sensitive information removed from codebase
  - Email addresses: genericized to `example.com`, `institution.edu`
  - Calendar IDs: replaced with `your-calendar-id@group.calendar.google.com`
  - API tokens: moved to environment variables
  - Database credentials: externalized to `.env`
- **Configuration Security** - All credentials now externalized
  - Service account keys: `~/.config/calpal/service-account-key.json` (never committed)
  - 25Live credentials: `~/.config/calpal/25live_credentials` (never committed)
  - Database passwords: `.env` file (never committed)
- **Enhanced .gitignore** - Multiple layers of protection
  - Blocks all credential files
  - Prevents committing personal data directories
  - Protects generated files with calendar data
  - Includes security checklist in comments

### Migration Guide

**For existing users:**

1. **Back up your current installation**
   ```bash
   cp -r CalPal CalPal.backup
   ```

2. **Update imports in any custom scripts**
   ```python
   # Old imports
   from src.db_manager import DatabaseManager
   from src.calendar_scanner import CalendarScanner

   # New imports
   from calpal.core.db_manager import DatabaseManager
   from calpal.sync.calendar_scanner import CalendarScanner
   ```

3. **Run services with new paths**
   ```bash
   # Old
   python3 src/unified_db_calpal_service.py

   # New
   python3 -m calpal.sync.unified_sync_service
   ```

4. **Update systemd service files** (if using)
   ```ini
   # Change ExecStart to:
   ExecStart=/path/to/venv/bin/python3 -m calpal.sync.unified_sync_service
   ```

**For new users:**
- Follow the complete setup guide in `docs/getting-started.md`
- All configuration is now template-based - no hardcoded values

## [1.x.x] - Previous Versions

### Added
- **Phase 2: Single Writer Pattern** - Architectural upgrade to prevent race conditions
  - New `unified_calendar_sync.py` service: single source of truth for Google Calendar writes
  - Database is now authoritative source, Google Calendar is presentation layer
  - Orphaned mirror detection and automatic cleanup
  - Batch processing with `--batch-size` and `--deletions-only` flags
  - **Systemd Services**: Replaced cron jobs with proper systemd timers
    - `calpal-scanner.timer`: Runs scanner hourly to detect manual deletions
    - `calpal-sync.timer`: Runs unified sync every 30 minutes (deletions-only)
  - Created `cleanup_all_deletions.sh` for overnight batch cleanup

### Changed
- **25Live Sync** - Converted to DB-only mode (no direct Google Calendar writes)
  - **CRITICAL FIX**: Now checks BOTH `25live_reservation_id` AND `25live_event_id` for deletions
  - Prevents infinite re-creation bug (e.g., CCC President's Meeting recreated 418 times)
  - Events marked as `pending_creation` in database
  - unified_calendar_sync handles Google Calendar creation

- **Calendar Scanner** - Converted to read-only mode
  - Removed `_remove_deleted_events()` method
  - Deletion now handled exclusively by unified_calendar_sync
  - Prevents race conditions between multiple services

- **ICS Generator** - Converted to database-only source (Phase 2 complete)
  - No longer queries Google Calendar directly
  - Reads all events from PostgreSQL database
  - **Anonymization**: Student appointments show as "Student appointment"
  - **Location Enhancement**: Classes show location (e.g., "Class in Ross Center ROS 105")
  - Excludes Personal and Family calendars
  - Respects database `deleted_at` field
  - Auto-restarts Flask server after generation

### Added (from previous work)
- **Deletion Detection & Removal** - Calendar Scanner now automatically detects and removes deleted events
  - Detects events deleted from Google Calendar and marks them in database
  - Removes events marked as deleted from Google Calendar (e.g., blacklisted events)
  - Bidirectional sync ensures database and Google Calendar stay consistent
  - Graceful handling of already-deleted events (404/410 errors)
  - Batch processing up to 500 deletions per scan

- **Recently Deleted Event Protection** - Prevents infinite deletion/re-creation loops
  - New `check_recently_deleted()` method in DatabaseManager
  - Scanner skips events deleted within last hour (configurable window)
  - Prevents race condition between reconciler deletion and scanner re-creation

- **Two-Layer Rate Limiting** - Comprehensive Google Calendar API rate limit handling
  - **Proactive throttling**: 100ms delay between API calls (10 QPS, well under Google's limit)
  - **Reactive backoff**: Exponential backoff (2s, 4s, 8s, 16s...) with automatic retry on rate limit hits
  - Eliminates 200+ rate limit errors per scan

- **Flask Auto-Refresh** - ICS Generator now restarts Flask server after generating new files
  - Ensures Flask always serves the latest ICS file
  - Prevents stale file caching issues

- **Event Blacklist Manager** - Interactive tool to manage unwanted 25Live events
  - Support for exact match and regex pattern blacklisting
  - Shows matching events in database
  - Automatically marks matching events as deleted
  - Integration with Calendar Scanner for removal

### Changed
- **Calendar Scanner** - Major improvements to event classification and rate limiting
  - Now recognizes subcalendar mirrors via `mirror_type='subcalendar_to_work'` in extendedProperties
  - Always updates events on each scan (not just when times/summary change)
  - Checks for `event_type` changes and auto-corrects misclassifications
  - Skips recently deleted events to prevent re-creation loops
  - Added `_detect_deletions()` method to compare calendar vs database
  - Added `_remove_deleted_events()` method with rate limiting
  - New database event states: `scanner_detected_deletion`, `removed_from_google`, `already_removed`

- **Database Manager** - Enhanced event tracking and duplicate prevention
  - `record_event()` now updates `event_type` field (fixes misclassifications)
  - New `check_recently_deleted()` method with configurable time window
  - Better handling of event lifecycle transitions

- **Work Calendar Reconciler** - Improved orphaned event detection
  - Now handles orphaned mirrors of ANY event_type (not just 'subcalendar_work_mirror')
  - Queries ALL events with `source_event_id` for comprehensive cleanup
  - Prevents orphaned events from escaping detection due to misclassification

- **Flask Server** - Disabled ICS file caching for always-fresh content
  - Added no-cache headers: `Cache-Control: no-cache, no-store, must-revalidate`
  - Disabled etag caching
  - Ensures clients always receive latest calendar data

### Fixed
- **CRITICAL: Infinite Duplicate Loop** - Fixed 4 critical leaks causing deletion/re-creation loop
  - **Leak #1**: Scanner now correctly identifies subcalendar mirrors (was misclassifying as 'other')
  - **Leak #2**: Scanner no longer re-creates recently deleted events (1-hour cooldown)
  - **Leak #3**: Reconciler now cleans up orphaned events of any type (not just typed correctly)
  - **Leak #4**: Scanner auto-corrects event_type misclassifications on subsequent scans
  - Result: 149 mistyped events will auto-correct, 7 persistent problem events will be removed

- **Google Calendar API Rate Limiting** - Eliminated 200+ rate limit errors per scan
  - Added proactive 100ms delay between API calls (prevents rate limits)
  - Added reactive exponential backoff with retry (handles edge cases)
  - Scanner now completes deletion phase without errors

- **Event Misclassification** - Events now correctly classified and auto-corrected
  - Subcalendar mirrors properly detected via extendedProperties metadata
  - Existing misclassifications fixed on next scan
  - Prevents orphaned events from escaping cleanup

- **ICS File Staleness** - Flask no longer caches ICS files, always serves fresh content
- **Blacklisted Events Not Removed** - Calendar Scanner now removes blacklisted events from Google Calendar
- **Deletion Detection Missing** - System now detects when events are manually deleted from calendars

### Documentation
- Updated SERVICES.md with comprehensive deletion detection documentation
- Added deletion flow diagrams and state transition examples
- Documented Flask cache control and auto-restart behavior
- Updated README.md to highlight deletion detection feature
- Added database event state documentation

### Planned Features
- Migration tracking system in database
- Web UI for configuration and monitoring
- Email notifications for sync failures
- Advanced event filtering rules
- Multi-user support with separate credentials
- Prometheus metrics export
- Grafana dashboards

## [1.0.0] - 2025-10-04

### Major Release - Database-Backed Architecture

This is the first public release of CalPal with a completely redesigned architecture using PostgreSQL as the single source of truth for event tracking.

### Added

#### Core Features
- **Database-backed event tracking** - PostgreSQL database stores all calendar events with complete lifecycle management
- **Unified service coordinator** - Single service manages all components with configurable intervals
- **Intelligent duplicate prevention** - Uses 25Live reservation IDs and event signatures
- **Bidirectional sync** - Detects changes in both 25Live and Google Calendar
- **Soft delete system** - Maintains audit trail of deleted events
- **Mirror event system** - Creates and maintains mirror copies across calendars

#### Services
- **25Live Sync Service** (`db_aware_25live_sync.py`) - Syncs events from 25Live API to database
- **Calendar Scanner** (`calendar_scanner.py`) - Scans Google Calendars for changes and deletions
- **Work Event Organizer** (`work_event_organizer.py`) - Automatically organizes events into subcalendars
- **Personal/Family Mirror** (`personal_family_mirror.py`) - Mirrors personal/family events to work calendar
- **Subcalendar Sync** (`subcalendar_work_sync.py`) - Syncs subcalendars back to work calendar
- **ICS Generator** (`db_aware_wife_ics_generator.py`) - Generates filtered ICS files from database
- **Flask Web Server** (`calpal_flask_server.py`) - Serves ICS files via HTTP with token auth

#### Database
- Complete database schema with event tracking table
- Indexes for performance optimization
- Views for common queries (active_events, deleted_events)
- Automatic timestamp updates via triggers
- Migration system for schema changes
- Comprehensive metadata storage in JSONB

#### Documentation
- Complete README with architecture diagrams
- Installation guide with step-by-step instructions
- Configuration guide with all options documented
- Services documentation with API reference
- Database documentation with schema details, queries, and best practices
- Security guide with comprehensive security best practices
- Contributing guidelines for open source collaboration
- 25Live Classes sync documentation

#### Configuration
- Centralized config.py for all settings
- Environment variable support
- Docker Compose setup for database
- Example configuration templates
- Secure credential management outside repository

#### Security
- Token-based authentication for web endpoints
- Credential isolation (no secrets in git)
- File permission enforcement
- Database password security
- Secure random token generation
- Comprehensive security documentation

### Changed
- **Architecture**: Complete rewrite from JSON file tracking to PostgreSQL database
- **Event tracking**: Now tracks full event lifecycle instead of just sync state
- **Services**: Modular services instead of monolithic scripts
- **Configuration**: Unified configuration instead of scattered settings

### Deprecated
- JSON-based event tracking files (classes_mirrored_events.json, etc.)
- Legacy sync scripts (twentyfive_live_sync.py without database)
- Legacy ICS generator (wife_calendar_ics_service.py without database)

### Removed
- File-based event tracking (replaced by database)
- Manual duplicate cleanup scripts (now automatic)
- Hardcoded calendar configurations (now in config.py)

### Fixed
- **Duplicate events**: Database constraints prevent duplicate events
- **Deletion detection**: Properly detects and handles deleted events
- **Mirror orphans**: Cleans up mirrors when source events deleted
- **Sync race conditions**: Database transactions ensure consistency
- **API rate limiting**: Better handling of Google Calendar API limits
- **Timezone handling**: Consistent timezone storage and processing

### Security
- All credentials moved outside repository
- Secure file permissions enforced
- Token-based web authentication
- Database password security
- No sensitive data in logs

## [0.9.0] - 2025-09-24 [Pre-release]

### Added
- Initial database schema design
- Database manager with connection pooling
- Event upsert functionality
- Soft delete implementation
- Basic mirror tracking

### Changed
- Transitioned from JSON file storage to database
- Updated sync logic to use database

## [0.5.0] - 2025-09-23 [Beta]

### Added
- Basic 25Live integration
- Google Calendar sync
- ICS file generation
- Flask server for ICS hosting
- JSON-based event tracking

### Changed
- Improved duplicate detection logic
- Better error handling

### Fixed
- Classes sync restoration issues
- Duplicate event creation

## [0.1.0] - 2025-09-21 [Alpha]

### Added
- Initial proof of concept
- Basic 25Live API integration
- Simple Google Calendar sync
- Manual event tracking

---

## Version History Overview

| Version | Date | Type | Description |
|---------|------|------|-------------|
| 1.0.0 | 2025-10-04 | Major | Database architecture, full documentation |
| 0.9.0 | 2025-09-24 | Pre-release | Database implementation |
| 0.5.0 | 2025-09-23 | Beta | JSON-based tracking |
| 0.1.0 | 2025-09-21 | Alpha | Initial prototype |

## Migration Guides

### Upgrading from 0.5.0 to 1.0.0

**Breaking Changes:**
- JSON tracking files no longer used
- Database now required
- Configuration structure changed

**Migration Steps:**

1. **Set up database**:
```bash
docker compose up -d
```

2. **Update configuration**:
```bash
cp config.example.py config.py
# Add DATABASE_URL to config.py
```

3. **Migrate existing events** (optional):
```bash
# If you have existing JSON tracking files
python3 scripts/migrate_json_to_db.py
```

4. **Update service calls**:
```bash
# Old:
python3 src/twentyfive_live_sync.py

# New:
python3 src/db_aware_25live_sync.py
```

5. **Update systemd service** (if using):
```bash
# Update ExecStart to use unified_db_calpal_service.py
sudo systemctl daemon-reload
sudo systemctl restart calpal
```

### Upgrading from 0.9.0 to 1.0.0

**Changes:**
- Schema updates (new indexes, constraints)
- Service coordination improvements
- Documentation updates

**Migration Steps:**

1. **Apply database migrations**:
```bash
docker exec -i calpal_db psql -U calpal -d calpal_db < db/migrations/002_add_mirror_fields.sql
```

2. **Update configuration**:
```bash
# Review config.py for new options
# Update service intervals if needed
```

3. **Restart services**:
```bash
systemctl restart calpal
```

## Known Issues

### Version 1.0.0

**Minor Issues:**
- Calendar scanner may take longer on first run with large calendars (expected)
- 25Live API occasionally returns incomplete data (retry logic handles this)
- ICS generation may include past events beyond configured window (filter in ICS reader)

**Workarounds:**
- Adjust SCAN_MAX_RESULTS in config for large calendars
- Increase 25Live sync interval if API issues persist
- Configure ICS reader to filter by date

### Reporting Issues

Please report issues on [GitHub Issues](https://github.com/yourusername/CalPal/issues) with:
- CalPal version
- Operating system
- Python version
- Database version
- Error messages/logs
- Steps to reproduce

## Roadmap

### Version 1.1.0 (Q4 2025)
- [ ] Web UI for configuration
- [ ] Email notifications
- [ ] Advanced filtering rules
- [ ] Performance optimizations
- [ ] Migration tracking table

### Version 1.2.0 (Q1 2026)
- [ ] Multi-user support
- [ ] Role-based access control
- [ ] API endpoints for external integrations
- [ ] Prometheus metrics
- [ ] Grafana dashboards

### Version 2.0.0 (Future)
- [ ] Support for additional calendar systems (Outlook, iCal)
- [ ] Machine learning for event classification
- [ ] Mobile app
- [ ] Cloud-hosted SaaS option

## Deprecation Notices

### Deprecated in 1.0.0
The following will be removed in version 2.0.0:

- **Legacy JSON tracking files**: Use database instead
- **Legacy sync scripts**: Use db_aware_* versions
- **run_wife_calendar_service.py**: Use unified_db_calpal_service.py

### How to Migrate

**From JSON tracking**:
```bash
# Backup JSON files
cp *.json backups/

# Run migration (if needed)
python3 scripts/migrate_json_to_db.py

# Verify in database
docker exec -it calpal_db psql -U calpal -d calpal_db -c "SELECT COUNT(*) FROM calendar_events;"
```

**From legacy scripts**:
```bash
# Old script:
python3 src/twentyfive_live_sync.py

# New script:
python3 src/db_aware_25live_sync.py

# Or use unified service:
python3 src/unified_db_calpal_service.py
```

## Contributors

Thank you to all contributors who have helped make CalPal better!

### Version 1.0.0 Contributors
- Travis Ross (@traviseross) - Architecture design, core development, documentation

Want to contribute? See [CONTRIBUTING.md](docs/CONTRIBUTING.md)!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Note:** This changelog follows the [Keep a Changelog](https://keepachangelog.com/) format. Each version documents:
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Features that will be removed
- **Removed**: Features that have been removed
- **Fixed**: Bug fixes
- **Security**: Security improvements
