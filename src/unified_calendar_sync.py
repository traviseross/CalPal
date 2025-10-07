#!/usr/bin/env python3
"""
Unified Calendar Sync Service

ARCHITECTURE PRINCIPLE: Single Writer Pattern
- Database is the authoritative source of truth for "what should exist"
- Google Calendar is a presentation/view layer
- This service makes Google Calendar match database state
- NO OTHER SERVICE should write to Google Calendar

Responsibilities:
1. Create events on Google Calendar when deleted_at IS NULL and not on calendar
2. Delete events from Google Calendar when deleted_at IS NOT NULL
3. Update events on Google Calendar when data changed
4. Handle cascading deletions: if source event deleted, delete all mirrors
5. Respect user deletion intent (deleted_at timestamp)

This replaces the scattered calendar writes in:
- db_aware_25live_sync.py (will become DB-only)
- calendar_scanner.py (will become read-only + DB write)
- work_calendar_reconciler.py (logic moves here)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.db_manager import DatabaseManager


class UnifiedCalendarSync:
    """
    Single service responsible for syncing database state to Google Calendar.

    Philosophy: Database tells us "what should exist", we make Google Calendar match.
    """

    def __init__(self, dry_run: bool = True, deletions_only: bool = False,
                 batch_size: int = None, calendar_filter: str = None):
        self.logger = logging.getLogger('unified-calendar-sync')
        self.dry_run = dry_run
        self.deletions_only = deletions_only
        self.batch_size = batch_size
        self.calendar_filter = calendar_filter

        if self.dry_run:
            self.logger.warning("🧪 DRY RUN MODE - No changes will be made to Google Calendar")
        else:
            self.logger.info("🔴 LIVE MODE - Changes will be applied to Google Calendar")

        if self.deletions_only:
            self.logger.info("🗑️  DELETIONS ONLY MODE - Will only remove events, not create them")

        if self.batch_size:
            self.logger.info(f"📦 BATCH SIZE: {self.batch_size} operations per run")

        if self.calendar_filter:
            self.logger.info(f"📅 CALENDAR FILTER: Only syncing '{self.calendar_filter}'")

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Load calendars to sync
        self.calendars_to_sync = self._load_calendar_list()

        # Statistics
        self.stats = {
            'events_created': 0,
            'events_deleted': 0,
            'events_updated': 0,
            'mirrors_deleted': 0,
            'errors': 0
        }

    def _initialize_calendar_service(self):
        """Initialize Google Calendar API service."""
        try:
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("✅ Google Calendar API service initialized")
            return service
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Calendar API: {e}")
            raise

    def _load_calendar_list(self) -> Dict[str, str]:
        """Load list of all calendars to sync."""
        calendars = {}

        # Work calendar (main sync target)
        calendars['Work'] = WORK_CALENDAR_ID  # tross@georgefox.edu

        # Work subcalendars
        try:
            subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
            with open(subcalendars_file, 'r') as f:
                subcalendars = json.load(f)
                calendars.update(subcalendars)
            self.logger.info(f"✅ Loaded {len(subcalendars)} work subcalendars")
        except Exception as e:
            self.logger.error(f"❌ Failed to load work subcalendars: {e}")

        self.logger.info(f"📅 Will sync {len(calendars)} calendars")
        return calendars

    def _get_active_db_events(self, calendar_id: str) -> Dict[str, Dict]:
        """
        Get all events that SHOULD exist on this calendar according to database.

        Returns: {event_id: event_data}
        """
        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT
                            event_id,
                            summary,
                            description,
                            location,
                            start_time,
                            end_time,
                            event_type,
                            metadata
                        FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        AND status = 'active'
                    """),
                    {'calendar_id': calendar_id}
                ).mappings().all()

                events = {}
                for row in result:
                    events[row['event_id']] = dict(row)

                return events

        except Exception as e:
            self.logger.error(f"Error getting active DB events: {e}")
            return {}

    def _get_calendar_events(self, calendar_id: str, calendar_name: str) -> Dict[str, Dict]:
        """
        Get all events currently on Google Calendar.

        Returns: {event_id: event_data}
        """
        try:
            # Query last 3 months to 12 months forward
            time_min = (datetime.now() - timedelta(days=90)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            events = {}
            page_token = None

            while True:
                events_result = self.calendar_service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=2500,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()

                batch_events = events_result.get('items', [])

                for event in batch_events:
                    event_id = event.get('id')
                    if event_id:
                        events[event_id] = event

                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break

            self.logger.debug(f"  Found {len(events)} events on {calendar_name}")
            return events

        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"  Calendar not found: {calendar_name}")
            else:
                self.logger.error(f"  Failed to fetch events from {calendar_name}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"  Error fetching events from {calendar_name}: {e}")
            return {}

    def _get_events_to_delete(self, calendar_id: str) -> List[Dict]:
        """
        Get events that should be DELETED from Google Calendar.
        These are events marked deleted_at != NULL in database.
        """
        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT
                            event_id,
                            current_calendar,
                            summary,
                            deleted_at,
                            last_action
                        FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NOT NULL
                        AND status = 'deleted'
                        AND last_action NOT IN ('removed_from_google', 'already_removed')
                        ORDER BY deleted_at
                        LIMIT 500
                    """),
                    {'calendar_id': calendar_id}
                ).mappings().all()

                return [dict(row) for row in result]

        except Exception as e:
            self.logger.error(f"Error getting events to delete: {e}")
            return []

    def _build_google_event(self, db_event: Dict) -> Dict:
        """Convert database event format to Google Calendar event format."""
        try:
            start_time = db_event['start_time']
            end_time = db_event['end_time']

            # Handle all-day events vs timed events
            if isinstance(start_time, datetime):
                if start_time.hour == 0 and start_time.minute == 0 and start_time.second == 0:
                    # Likely all-day event
                    google_event = {
                        'summary': db_event['summary'],
                        'description': db_event.get('description', ''),
                        'location': db_event.get('location', ''),
                        'start': {'date': start_time.strftime('%Y-%m-%d')},
                        'end': {'date': end_time.strftime('%Y-%m-%d')},
                    }
                else:
                    # Timed event
                    google_event = {
                        'summary': db_event['summary'],
                        'description': db_event.get('description', ''),
                        'location': db_event.get('location', ''),
                        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'America/Los_Angeles'},
                        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'America/Los_Angeles'},
                    }

            # Add extended properties from metadata
            metadata = db_event.get('metadata', {})
            if metadata:
                extended_props = metadata.get('google_event_data', {})
                if extended_props:
                    google_event['extendedProperties'] = extended_props

            return google_event

        except Exception as e:
            self.logger.error(f"Error building Google event: {e}")
            return None

    def sync_calendar(self, calendar_name: str, calendar_id: str) -> Dict[str, int]:
        """
        Sync a single calendar: make Google Calendar match database state.

        Returns: Statistics dict
        """
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"📅 Syncing calendar: {calendar_name}")
        self.logger.info(f"{'='*60}")

        local_stats = {
            'events_to_create': 0,
            'events_to_delete': 0,
            'events_to_update': 0,
            'created': 0,
            'deleted': 0,
            'updated': 0,
            'errors': 0
        }

        # Step 1: Get database state (what SHOULD exist)
        self.logger.info("📊 Getting database state...")
        db_events = self._get_active_db_events(calendar_id)
        self.logger.info(f"  Database says {len(db_events)} events should exist")

        # Step 2: Get Google Calendar state (what DOES exist)
        self.logger.info("☁️  Getting Google Calendar state...")
        gcal_events = self._get_calendar_events(calendar_id, calendar_name)
        self.logger.info(f"  Google Calendar has {len(gcal_events)} events")

        # Step 3: Compute differences
        db_event_ids = set(db_events.keys())
        gcal_event_ids = set(gcal_events.keys())

        to_create = db_event_ids - gcal_event_ids  # In DB, not on calendar
        to_delete = gcal_event_ids - db_event_ids  # On calendar, not in DB (stale)

        local_stats['events_to_create'] = len(to_create)
        local_stats['events_to_delete'] = len(to_delete)

        self.logger.info(f"\n📋 Sync Plan:")
        self.logger.info(f"  Events to CREATE: {len(to_create)}")
        self.logger.info(f"  Events to DELETE: {len(to_delete)}")

        # Step 4: Handle deletions (events marked deleted_at in DB)
        self.logger.info(f"\n🗑️  Checking for explicitly deleted events...")
        explicitly_deleted = self._get_events_to_delete(calendar_id)
        self.logger.info(f"  Found {len(explicitly_deleted)} events marked for deletion")

        if explicitly_deleted:
            for event in explicitly_deleted[:5]:  # Show first 5
                self.logger.info(f"    - {event['summary']} (deleted {event['deleted_at']})")
            if len(explicitly_deleted) > 5:
                self.logger.info(f"    ... and {len(explicitly_deleted) - 5} more")

        # Step 5: Apply changes (or log if dry run)
        if self.dry_run:
            self._log_proposed_changes(calendar_name, to_create, to_delete, db_events, gcal_events, explicitly_deleted)
        else:
            self._apply_changes(calendar_name, calendar_id, to_create, to_delete, db_events, explicitly_deleted, local_stats)

        return local_stats

    def _log_proposed_changes(self, calendar_name: str, to_create: Set[str],
                             to_delete: Set[str], db_events: Dict, gcal_events: Dict,
                             explicitly_deleted: List[Dict]):
        """Log what would change in dry run mode."""

        self.logger.info(f"\n🧪 DRY RUN - Proposed changes for {calendar_name}:")

        if to_create:
            self.logger.info(f"\n➕ Would CREATE {len(to_create)} events:")
            for event_id in list(to_create)[:10]:  # Show first 10
                event = db_events[event_id]
                self.logger.info(f"    - {event['summary']} ({event['start_time']})")
            if len(to_create) > 10:
                self.logger.info(f"    ... and {len(to_create) - 10} more")

        if to_delete:
            self.logger.info(f"\n❌ Would DELETE {len(to_delete)} stale events:")
            for event_id in list(to_delete)[:10]:  # Show first 10
                event = gcal_events[event_id]
                self.logger.info(f"    - {event.get('summary', 'Untitled')}")
            if len(to_delete) > 10:
                self.logger.info(f"    ... and {len(to_delete) - 10} more")

        if explicitly_deleted:
            self.logger.info(f"\n🗑️  Would DELETE {len(explicitly_deleted)} explicitly deleted events:")
            for event in explicitly_deleted[:10]:
                self.logger.info(f"    - {event['summary']}")
            if len(explicitly_deleted) > 10:
                self.logger.info(f"    ... and {len(explicitly_deleted) - 10} more")

        if not to_create and not to_delete and not explicitly_deleted:
            self.logger.info("  ✅ Calendar is in sync - no changes needed")

    def _apply_changes(self, calendar_name: str, calendar_id: str,
                      to_create: Set[str], to_delete: Set[str],
                      db_events: Dict, explicitly_deleted: List[Dict],
                      local_stats: Dict):
        """Apply changes to Google Calendar (LIVE MODE)."""
        from sqlalchemy import text

        self.logger.info(f"\n🔴 LIVE MODE - Applying changes to {calendar_name}...")

        # Track operations for batch limiting
        operations_count = 0
        batch_limit_reached = False

        # Delete stale events (on calendar but not in DB)
        if to_delete and not batch_limit_reached:
            events_to_process = list(to_delete)[:self.batch_size] if self.batch_size else list(to_delete)
            self.logger.info(f"\n❌ Deleting {len(events_to_process)} stale events...")

            for event_id in events_to_process:
                if self.batch_size and operations_count >= self.batch_size:
                    self.logger.info(f"  ⏸️  Batch limit ({self.batch_size}) reached, stopping")
                    batch_limit_reached = True
                    break

                try:
                    time.sleep(0.1)  # Rate limiting

                    self.calendar_service.events().delete(
                        calendarId=calendar_id,
                        eventId=event_id
                    ).execute()

                    local_stats['deleted'] += 1
                    operations_count += 1
                    self.logger.debug(f"  ✅ Deleted stale event {event_id}")

                except HttpError as e:
                    if e.resp.status in [404, 410]:
                        # Already gone
                        local_stats['deleted'] += 1
                        operations_count += 1
                    else:
                        self.logger.error(f"  ❌ Failed to delete {event_id}: {e}")
                        local_stats['errors'] += 1

        # Delete explicitly deleted events (marked deleted_at in DB)
        if explicitly_deleted and not batch_limit_reached:
            events_to_process = explicitly_deleted[:self.batch_size - operations_count] if self.batch_size else explicitly_deleted
            self.logger.info(f"\n🗑️  Deleting {len(events_to_process)} explicitly deleted events...")

            with self.db.get_session() as session:
                for event in events_to_process:
                    if self.batch_size and operations_count >= self.batch_size:
                        self.logger.info(f"  ⏸️  Batch limit ({self.batch_size}) reached, stopping")
                        batch_limit_reached = True
                        break

                    try:
                        time.sleep(0.1)  # Rate limiting

                        self.calendar_service.events().delete(
                            calendarId=event['current_calendar'],
                            eventId=event['event_id']
                        ).execute()

                        # Mark as removed in database
                        session.execute(
                            text("""
                                UPDATE calendar_events
                                SET last_action = 'removed_from_google',
                                    last_action_at = NOW()
                                WHERE event_id = :event_id
                                AND current_calendar = :calendar_id
                            """),
                            {
                                'event_id': event['event_id'],
                                'calendar_id': event['current_calendar']
                            }
                        )

                        local_stats['deleted'] += 1
                        operations_count += 1
                        self.logger.debug(f"  ✅ Deleted {event['summary']}")

                    except HttpError as e:
                        if e.resp.status in [404, 410]:
                            # Already gone
                            session.execute(
                                text("""
                                    UPDATE calendar_events
                                    SET last_action = 'already_removed',
                                        last_action_at = NOW()
                                    WHERE event_id = :event_id
                                    AND current_calendar = :calendar_id
                                """),
                                {
                                    'event_id': event['event_id'],
                                    'calendar_id': event['current_calendar']
                                }
                            )
                            local_stats['deleted'] += 1
                            operations_count += 1
                        else:
                            self.logger.error(f"  ❌ Failed to delete {event['summary']}: {e}")
                            local_stats['errors'] += 1
                    except Exception as e:
                        self.logger.error(f"  ❌ Error deleting {event['summary']}: {e}")
                        local_stats['errors'] += 1

                session.commit()

        # Create missing events (in DB but not on calendar)
        if to_create and not self.deletions_only and not batch_limit_reached:
            events_to_process = list(to_create)[:self.batch_size - operations_count] if self.batch_size else list(to_create)
            self.logger.info(f"\n➕ Creating {len(events_to_process)} missing events...")

            with self.db.get_session() as session:
                for event_id in events_to_process:
                    if self.batch_size and operations_count >= self.batch_size:
                        self.logger.info(f"  ⏸️  Batch limit ({self.batch_size}) reached, stopping")
                        break

                    try:
                        time.sleep(0.1)  # Rate limiting

                        db_event = db_events[event_id]
                        google_event = self._build_google_event(db_event)

                        if not google_event:
                            local_stats['errors'] += 1
                            continue

                        # Create on Google Calendar
                        created_event = self.calendar_service.events().insert(
                            calendarId=calendar_id,
                            body=google_event
                        ).execute()

                        # Update database with last_action
                        session.execute(
                            text("""
                                UPDATE calendar_events
                                SET last_action = 'synced_to_google',
                                    last_action_at = NOW()
                                WHERE event_id = :event_id
                                AND current_calendar = :calendar_id
                            """),
                            {
                                'event_id': event_id,
                                'calendar_id': calendar_id
                            }
                        )

                        local_stats['created'] += 1
                        operations_count += 1
                        self.logger.debug(f"  ✅ Created {db_event['summary']}")

                    except Exception as e:
                        self.logger.error(f"  ❌ Failed to create event {event_id}: {e}")
                        local_stats['errors'] += 1

                session.commit()
        elif to_create and self.deletions_only:
            self.logger.info(f"\n⏭️  Skipping creation of {len(to_create)} events (deletions-only mode)")

        self.logger.info(f"\n✅ Sync complete for {calendar_name}")
        self.logger.info(f"  Created: {local_stats['created']}")
        self.logger.info(f"  Deleted: {local_stats['deleted']}")
        self.logger.info(f"  Errors: {local_stats['errors']}")

    def handle_orphaned_mirrors(self) -> Dict[str, int]:
        """
        Find mirrors whose source events are deleted and mark them for deletion.

        This replaces work_calendar_reconciler.reconcile_orphaned_mirrors()
        """
        self.logger.info(f"\n{'='*60}")
        self.logger.info("🔗 Checking for orphaned mirrors...")
        self.logger.info(f"{'='*60}")

        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                # Find all active mirror events (any event with source_event_id)
                mirrors = session.execute(
                    text("""
                        SELECT
                            m.event_id,
                            m.summary,
                            m.event_type,
                            m.current_calendar,
                            m.metadata->>'source_event_id' as source_id,
                            m.source_calendar as source_cal
                        FROM calendar_events m
                        WHERE m.deleted_at IS NULL
                        AND m.status = 'active'
                        AND m.metadata->>'source_event_id' IS NOT NULL
                    """)
                ).mappings().all()

                orphan_stats = {
                    'checked': len(mirrors),
                    'orphaned': 0,
                    'marked_deleted': 0
                }

                self.logger.info(f"  Checking {len(mirrors)} mirror events...")

                for mirror in mirrors:
                    source_id = mirror['source_id']
                    source_cal = mirror['source_cal']

                    if not source_id or not source_cal:
                        continue

                    # Check if source event is deleted
                    source_deleted = session.execute(
                        text("""
                            SELECT deleted_at
                            FROM calendar_events
                            WHERE event_id = :source_id
                            AND current_calendar = :source_cal
                            LIMIT 1
                        """),
                        {'source_id': source_id, 'source_cal': source_cal}
                    ).scalar()

                    if source_deleted is not None:
                        # Source is deleted, mark mirror for deletion
                        self.logger.warning(
                            f"  🔴 Orphaned mirror: '{mirror['summary']}' "
                            f"(source deleted on {source_deleted})"
                        )
                        orphan_stats['orphaned'] += 1

                        if not self.dry_run:
                            # Mark mirror as deleted in database
                            # Sync service will remove it from Google Calendar
                            session.execute(
                                text("""
                                    UPDATE calendar_events
                                    SET deleted_at = NOW(),
                                        status = 'deleted',
                                        last_action = 'source_deleted_orphan',
                                        last_action_at = NOW()
                                    WHERE event_id = :event_id
                                    AND current_calendar = :calendar_id
                                    AND deleted_at IS NULL
                                """),
                                {
                                    'event_id': mirror['event_id'],
                                    'calendar_id': mirror['current_calendar']
                                }
                            )
                            orphan_stats['marked_deleted'] += 1
                        else:
                            self.logger.info(f"    🧪 DRY RUN - Would mark for deletion")

                if not self.dry_run:
                    session.commit()

                self.logger.info(
                    f"\n  Found {orphan_stats['orphaned']} orphaned mirrors"
                )
                if not self.dry_run:
                    self.logger.info(f"  Marked {orphan_stats['marked_deleted']} for deletion")

                return orphan_stats

        except Exception as e:
            self.logger.error(f"Error checking for orphaned mirrors: {e}")
            import traceback
            traceback.print_exc()
            return {'errors': 1}

    def sync_all_calendars(self) -> Dict[str, Any]:
        """
        Sync all calendars: make Google Calendar match database state.

        Returns: Full results with statistics
        """
        self.logger.info("=" * 60)
        self.logger.info("🚀 UNIFIED CALENDAR SYNC")
        if self.dry_run:
            self.logger.info("🧪 DRY RUN MODE - No changes will be made")
        else:
            self.logger.info("🔴 LIVE MODE - Changes will be applied")
        self.logger.info("=" * 60)

        results = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': self.dry_run,
            'calendars': {},
            'orphaned_mirrors': {},
            'totals': {
                'events_created': 0,
                'events_deleted': 0,
                'events_updated': 0,
                'errors': 0
            }
        }

        # Step 1: Handle orphaned mirrors first
        orphan_stats = self.handle_orphaned_mirrors()
        results['orphaned_mirrors'] = orphan_stats

        # Step 2: Sync each calendar
        for calendar_name, calendar_id in self.calendars_to_sync.items():
            # Skip if calendar filter is set and doesn't match
            if self.calendar_filter and calendar_name != self.calendar_filter:
                self.logger.debug(f"  Skipping {calendar_name} (filtered)")
                continue

            try:
                stats = self.sync_calendar(calendar_name, calendar_id)
                results['calendars'][calendar_name] = stats

                # Update totals
                results['totals']['events_created'] += stats.get('created', 0)
                results['totals']['events_deleted'] += stats.get('deleted', 0)
                results['totals']['events_updated'] += stats.get('updated', 0)
                results['totals']['errors'] += stats.get('errors', 0)

            except Exception as e:
                self.logger.error(f"Failed to sync {calendar_name}: {e}")
                results['calendars'][calendar_name] = {'error': str(e)}

        # Save results
        results_file = os.path.join(PROJECT_ROOT, 'unified_sync_results.json')
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Log summary
        self.logger.info("\n" + "=" * 60)
        self.logger.info("📊 SYNC SUMMARY")
        self.logger.info("=" * 60)
        if self.dry_run:
            self.logger.info("🧪 DRY RUN - No changes were made")
        self.logger.info(f"Events created: {results['totals']['events_created']}")
        self.logger.info(f"Events deleted: {results['totals']['events_deleted']}")
        self.logger.info(f"Events updated: {results['totals']['events_updated']}")
        self.logger.info(f"Errors: {results['totals']['errors']}")
        self.logger.info(f"Orphaned mirrors found: {orphan_stats.get('orphaned', 0)}")
        if not self.dry_run and orphan_stats.get('marked_deleted', 0) > 0:
            self.logger.info(f"Orphaned mirrors marked for deletion: {orphan_stats.get('marked_deleted', 0)}")
        self.logger.info("=" * 60)

        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Unified Calendar Sync Service')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--live', action='store_true',
                       help='Run in LIVE mode (apply changes). Default is DRY RUN.')
    parser.add_argument('--deletions-only', action='store_true',
                       help='Only delete events, skip creation (useful for cleanup)')
    parser.add_argument('--batch-size', type=int,
                       help='Limit number of operations per run (prevents rate limits)')
    parser.add_argument('--calendar',
                       help='Only sync specific calendar (e.g., "Work", "Classes")')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    dry_run = not args.live

    print("\n" + "=" * 60)
    print("🚀 UNIFIED CALENDAR SYNC SERVICE")
    print("=" * 60)
    if dry_run:
        print("🧪 DRY RUN MODE - No changes will be made")
        print("   Use --live to apply changes")
    else:
        print("🔴 LIVE MODE - Changes will be applied to Google Calendar")
    if args.deletions_only:
        print("🗑️  DELETIONS ONLY - Will not create events")
    if args.batch_size:
        print(f"📦 BATCH SIZE: {args.batch_size} operations")
    if args.calendar:
        print(f"📅 CALENDAR FILTER: {args.calendar}")
    print("=" * 60)
    print()

    sync = UnifiedCalendarSync(
        dry_run=dry_run,
        deletions_only=args.deletions_only,
        batch_size=args.batch_size,
        calendar_filter=args.calendar
    )
    results = sync.sync_all_calendars()

    print("\n✅ Sync complete!")
    print(f"Results saved to: unified_sync_results.json")

    if dry_run:
        print("\n💡 To apply these changes, run with --live flag")
    elif args.batch_size and (results['totals']['events_created'] > 0 or results['totals']['events_deleted'] > 0):
        print("\n💡 Run again to continue sync (batch processing)")


if __name__ == '__main__':
    main()
