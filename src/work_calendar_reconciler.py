#!/usr/bin/env python3
"""
Work Calendar Reconciliation Service

Ensures the root work calendar stays in sync with the database:
- One and only one Google Calendar event per active database entry
- All deleted database entries are removed from Google Calendar
- Duplicates are detected and removed
- Proper rate limit handling to avoid false deletions

This service runs periodically to reconcile any discrepancies between
the database and Google Calendar, especially on the root work calendar.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.db_manager import DatabaseManager


class WorkCalendarReconciler:
    """Reconcile work calendar with database state."""

    def __init__(self):
        self.logger = logging.getLogger('work-calendar-reconciler')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Work calendar to reconcile
        self.work_calendar_id = WORK_CALENDAR_ID

        # Rate limiting configuration
        self.api_call_delay = 0.1  # 100ms between calls
        self.max_retries = 3
        self.base_backoff = 2  # seconds

        # Statistics
        self.stats = {
            'active_events_checked': 0,
            'duplicates_found': 0,
            'duplicates_removed': 0,
            'deleted_events_removed': 0,
            'events_missing_from_google': 0,
            'errors': 0,
            'rate_limit_hits': 0
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

    def _api_call_with_retry(self, api_func, *args, **kwargs) -> Optional[Any]:
        """
        Execute API call with exponential backoff retry on rate limits.

        Returns None on permanent failure, otherwise returns result.
        """
        for attempt in range(self.max_retries):
            try:
                # Add delay between calls to avoid rate limits
                time.sleep(self.api_call_delay)

                # Execute the API call (returns HttpRequest, need to .execute())
                request = api_func(*args, **kwargs)
                result = request.execute()
                return result

            except HttpError as e:
                if e.resp.status == 429 or 'rateLimitExceeded' in str(e):
                    # Rate limit hit - exponential backoff
                    self.stats['rate_limit_hits'] += 1
                    backoff_time = self.base_backoff * (2 ** attempt)
                    self.logger.warning(f"⏳ Rate limit hit, backing off for {backoff_time}s (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(backoff_time)
                    continue

                elif e.resp.status in [404, 410]:
                    # Event doesn't exist - this is expected for deletions
                    return None

                elif e.resp.status >= 500:
                    # Server error - retry
                    backoff_time = self.base_backoff * (2 ** attempt)
                    self.logger.warning(f"⏳ Server error {e.resp.status}, retrying in {backoff_time}s")
                    time.sleep(backoff_time)
                    continue

                else:
                    # Other HTTP error - log and fail
                    self.logger.error(f"❌ HTTP error {e.resp.status}: {e}")
                    raise

            except Exception as e:
                self.logger.error(f"❌ Unexpected error in API call: {e}")
                raise

        # Max retries exceeded
        self.logger.error(f"❌ Max retries ({self.max_retries}) exceeded for API call")
        return None

    def get_active_events_from_db(self) -> List[Dict]:
        """Get all active events for work calendar from database."""
        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT event_id, summary, start_time, end_time,
                               ical_uid, metadata
                        FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        AND status = 'active'
                        ORDER BY start_time
                    """),
                    {'calendar_id': self.work_calendar_id}
                ).mappings().all()

                return [dict(row) for row in results]

        except Exception as e:
            self.logger.error(f"Error fetching active events from DB: {e}")
            return []

    def get_deleted_events_from_db(self) -> List[Dict]:
        """Get all deleted events for work calendar from database."""
        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT event_id, summary, deleted_at, last_action
                        FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NOT NULL
                        AND status = 'deleted'
                        AND last_action NOT IN ('removed_from_google', 'already_removed')
                        ORDER BY deleted_at
                        LIMIT 500
                    """),
                    {'calendar_id': self.work_calendar_id}
                ).mappings().all()

                return [dict(row) for row in results]

        except Exception as e:
            self.logger.error(f"Error fetching deleted events from DB: {e}")
            return []

    def fetch_all_google_events(self) -> Dict[str, List[Dict]]:
        """
        Fetch all events from Google Calendar and index them.

        Returns dict with:
        - 'by_id': Dict[event_id -> event]
        - 'by_summary_time': Dict[(summary, start_time) -> List[event]]
        """
        self.logger.info("  Fetching all events from Google Calendar...")

        try:
            all_events = []
            page_token = None

            # Fetch events from August 2024 to 12 months forward
            time_min = datetime(2024, 8, 1).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            while True:
                result = self._api_call_with_retry(
                    self.calendar_service.events().list,
                    calendarId=self.work_calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=2500,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                )

                if result:
                    events = result.get('items', [])
                    all_events.extend(events)
                    page_token = result.get('nextPageToken')

                    if not page_token:
                        break
                else:
                    break

            self.logger.info(f"  Found {len(all_events)} events on Google Calendar")

            # Build indexes
            by_id = {}
            by_summary_time = defaultdict(list)

            for event in all_events:
                event_id = event.get('id')
                summary = event.get('summary', '')

                # Get start time
                start = event.get('start', {})
                if 'dateTime' in start:
                    start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                elif 'date' in start:
                    start_time = datetime.strptime(start['date'], '%Y-%m-%d')
                else:
                    continue

                # Index by ID
                if event_id:
                    by_id[event_id] = event

                # Index by summary + start time (rounded to minute for matching)
                key = (summary, start_time.replace(second=0, microsecond=0))
                by_summary_time[key].append(event)

            return {
                'by_id': by_id,
                'by_summary_time': by_summary_time
            }

        except Exception as e:
            self.logger.error(f"Error fetching Google Calendar events: {e}")
            return {'by_id': {}, 'by_summary_time': {}}

    def find_events_in_index(self, google_index: Dict, event_id: str,
                            summary: str, start_time: datetime) -> List[str]:
        """
        Find all instances of this event in the Google Calendar index.

        Returns list of Google Calendar event IDs.
        """
        event_ids = []
        by_id = google_index['by_id']
        by_summary_time = google_index['by_summary_time']

        # Check by event_id first
        if event_id in by_id:
            event_ids.append(event_id)

        # Check by summary + time for duplicates
        key = (summary, start_time.replace(second=0, microsecond=0))
        matching_events = by_summary_time.get(key, [])

        for event in matching_events:
            eid = event.get('id')
            if eid and eid not in event_ids:
                event_ids.append(eid)

        return event_ids

    def reconcile_active_events(self) -> Dict[str, int]:
        """
        Ensure each active database event exists exactly once on Google Calendar.

        Returns statistics about the reconciliation.
        """
        self.logger.info("🔍 Reconciling active events...")

        # Fetch all events from Google Calendar once
        google_index = self.fetch_all_google_events()

        active_events = self.get_active_events_from_db()
        self.logger.info(f"  Found {len(active_events)} active events in database")

        local_stats = {
            'checked': 0,
            'duplicates_found': 0,
            'duplicates_removed': 0,
            'missing': 0
        }

        for db_event in active_events:
            try:
                event_id = db_event['event_id']
                summary = db_event['summary']
                start_time = db_event['start_time']

                # Find all instances in Google Calendar index
                google_event_ids = self.find_events_in_index(google_index, event_id, summary, start_time)

                local_stats['checked'] += 1

                if len(google_event_ids) == 0:
                    # Event missing from Google Calendar
                    self.logger.warning(f"  ⚠️  Missing from Google: {summary} (ID: {event_id})")
                    local_stats['missing'] += 1

                elif len(google_event_ids) == 1:
                    # Perfect - exactly one instance
                    self.logger.debug(f"  ✅ OK: {summary}")

                else:
                    # Duplicates found!
                    self.logger.warning(f"  🔴 Found {len(google_event_ids)} duplicates of '{summary}'")
                    local_stats['duplicates_found'] += 1

                    # Keep the first one (the one that matches db event_id if possible)
                    keep_id = event_id if event_id in google_event_ids else google_event_ids[0]
                    delete_ids = [eid for eid in google_event_ids if eid != keep_id]

                    self.logger.info(f"    Keeping: {keep_id}")
                    self.logger.info(f"    Deleting: {', '.join(delete_ids)}")

                    # Delete duplicates
                    for dup_id in delete_ids:
                        try:
                            result = self._api_call_with_retry(
                                self.calendar_service.events().delete,
                                calendarId=self.work_calendar_id,
                                eventId=dup_id
                            )
                            if result is not None:  # None means 404/410 (already gone)
                                self.logger.info(f"    ✅ Deleted duplicate: {dup_id}")
                                local_stats['duplicates_removed'] += 1
                        except Exception as e:
                            self.logger.error(f"    ❌ Failed to delete duplicate {dup_id}: {e}")
                            self.stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"  Error processing event {db_event.get('event_id', 'unknown')}: {e}")
                self.stats['errors'] += 1

        # Update global stats
        self.stats['active_events_checked'] = local_stats['checked']
        self.stats['duplicates_found'] = local_stats['duplicates_found']
        self.stats['duplicates_removed'] = local_stats['duplicates_removed']
        self.stats['events_missing_from_google'] = local_stats['missing']

        return local_stats

    def fix_data_inconsistencies(self) -> Dict[str, int]:
        """
        Fix database inconsistencies where deleted_at is set but status is still active.

        Returns statistics.
        """
        self.logger.info("🔧 Fixing data inconsistencies...")

        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                # Find events with inconsistent state
                result = session.execute(
                    text("""
                        UPDATE calendar_events
                        SET status = 'deleted'
                        WHERE deleted_at IS NOT NULL
                        AND status != 'deleted'
                        AND current_calendar = :work_calendar
                        RETURNING event_id, summary
                    """),
                    {'work_calendar': self.work_calendar_id}
                )

                fixed = result.rowcount
                session.commit()

                if fixed > 0:
                    self.logger.info(f"  Fixed {fixed} events with inconsistent status")

                return {'fixed': fixed}

        except Exception as e:
            self.logger.error(f"Error fixing data inconsistencies: {e}")
            return {'errors': 1}

    def reconcile_orphaned_mirrors(self) -> Dict[str, int]:
        """
        Find and remove mirrors whose source events have been deleted.

        Returns statistics.
        """
        self.logger.info("🔗 Checking for orphaned mirrors...")

        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                # Find all active mirrors on work calendar (any event_type with source_event_id)
                # This catches properly typed mirrors AND misclassified ones (event_type='other')
                mirrors = session.execute(
                    text("""
                        SELECT
                            m.event_id,
                            m.summary,
                            m.event_type,
                            m.metadata->>'source_event_id' as source_id,
                            m.source_calendar as source_cal
                        FROM calendar_events m
                        WHERE m.current_calendar = :work_calendar
                        AND m.deleted_at IS NULL
                        AND m.status = 'active'
                        AND m.metadata->>'source_event_id' IS NOT NULL
                    """),
                    {'work_calendar': self.work_calendar_id}
                ).mappings().all()

                local_stats = {
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
                        # Source is deleted, remove mirror immediately
                        self.logger.warning(
                            f"  🔴 Orphaned mirror: '{mirror['summary']}' "
                            f"(source deleted)"
                        )
                        local_stats['orphaned'] += 1

                        # Delete from Google Calendar immediately
                        try:
                            delete_result = self._api_call_with_retry(
                                self.calendar_service.events().delete,
                                calendarId=self.work_calendar_id,
                                eventId=mirror['event_id']
                            )

                            if delete_result is None:
                                # Already gone (404/410)
                                action = 'already_removed'
                            else:
                                # Successfully deleted
                                action = 'orphaned_mirror_removed'
                                self.logger.info(f"    ✅ Removed from Google Calendar")

                        except Exception as e:
                            self.logger.error(f"    ❌ Failed to remove from Google: {e}")
                            action = 'orphaned_mirror_cleanup_failed'

                        # Mark mirror as deleted in database
                        session.execute(
                            text("""
                                UPDATE calendar_events
                                SET deleted_at = NOW(),
                                    status = 'deleted',
                                    last_action = :action,
                                    last_action_at = NOW()
                                WHERE event_id = :event_id
                                AND current_calendar = :calendar_id
                                AND deleted_at IS NULL
                            """),
                            {
                                'event_id': mirror['event_id'],
                                'calendar_id': self.work_calendar_id,
                                'action': action
                            }
                        )
                        local_stats['marked_deleted'] += 1

                session.commit()

                self.logger.info(
                    f"  Found {local_stats['orphaned']} orphaned mirrors, "
                    f"marked {local_stats['marked_deleted']} for deletion"
                )

                return local_stats

        except Exception as e:
            self.logger.error(f"Error checking for orphaned mirrors: {e}")
            import traceback
            traceback.print_exc()
            return {'errors': 1}

    def reconcile_deleted_events(self) -> Dict[str, int]:
        """
        Ensure all deleted database events are removed from Google Calendar.

        Returns statistics about the reconciliation.
        """
        self.logger.info("🗑️  Reconciling deleted events...")

        deleted_events = self.get_deleted_events_from_db()
        self.logger.info(f"  Found {len(deleted_events)} deleted events in database")

        local_stats = {
            'removed': 0,
            'already_gone': 0,
            'errors': 0
        }

        for db_event in deleted_events:
            try:
                event_id = db_event['event_id']
                summary = db_event['summary']

                # Try to delete from Google Calendar
                result = self._api_call_with_retry(
                    self.calendar_service.events().delete,
                    calendarId=self.work_calendar_id,
                    eventId=event_id
                )

                if result is None:
                    # Event already gone (404/410)
                    self.logger.debug(f"  ✅ Already removed: {summary}")
                    local_stats['already_gone'] += 1

                    # Mark as already_removed in database
                    self._mark_event_removed(event_id, 'already_removed')

                else:
                    # Successfully deleted
                    self.logger.info(f"  ✅ Removed: {summary}")
                    local_stats['removed'] += 1

                    # Mark as removed_from_google in database
                    self._mark_event_removed(event_id, 'removed_from_google')

            except Exception as e:
                self.logger.error(f"  ❌ Error removing {db_event.get('summary', 'unknown')}: {e}")
                local_stats['errors'] += 1

        # Update global stats
        self.stats['deleted_events_removed'] = local_stats['removed'] + local_stats['already_gone']

        return local_stats

    def _mark_event_removed(self, event_id: str, action: str):
        """Mark event as removed in database."""
        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                session.execute(
                    text("""
                        UPDATE calendar_events
                        SET last_action = :action,
                            last_action_at = NOW()
                        WHERE event_id = :event_id
                        AND current_calendar = :calendar_id
                    """),
                    {
                        'event_id': event_id,
                        'calendar_id': self.work_calendar_id,
                        'action': action
                    }
                )
                session.commit()

        except Exception as e:
            self.logger.error(f"Error marking event as removed: {e}")

    def reconcile_subcalendar_mirrors(self) -> Dict[str, int]:
        """
        Ensure all subcalendar events have valid mirrors on work calendar.

        Checks for:
        - Missing mirrors
        - Incorrect mirror times
        - Orphaned mirrors (source deleted)

        Returns statistics about the reconciliation.
        """
        self.logger.info("🔄 Reconciling subcalendar mirrors...")

        try:
            from sqlalchemy import text

            # Get all subcalendar events that should have mirrors on work
            with self.db.get_session() as session:
                subcal_events = session.execute(
                    text("""
                        SELECT event_id, summary, start_time, end_time,
                               current_calendar, event_type
                        FROM calendar_events
                        WHERE current_calendar != :work_calendar
                        AND deleted_at IS NULL
                        AND status = 'active'
                        AND event_type IN ('manual', '25live_event', '25live_class',
                                          'booking', 'meeting_invitation')
                        AND current_calendar LIKE '%@group.calendar.google.com'
                        ORDER BY start_time
                    """),
                    {'work_calendar': self.work_calendar_id}
                ).mappings().all()

                # Get all active mirrors on work calendar from subcalendars
                work_mirrors = session.execute(
                    text("""
                        SELECT event_id, summary, start_time, end_time,
                               source_calendar, metadata
                        FROM calendar_events
                        WHERE current_calendar = :work_calendar
                        AND deleted_at IS NULL
                        AND status = 'active'
                        AND event_type = 'subcalendar_work_mirror'
                        ORDER BY start_time
                    """),
                    {'work_calendar': self.work_calendar_id}
                ).mappings().all()

                # Build index of work mirrors by source
                mirrors_by_source = {}
                for mirror in work_mirrors:
                    source_cal = mirror['source_calendar']
                    source_event_id = mirror['metadata'].get('source_event_id')
                    if source_event_id:
                        key = (source_cal, source_event_id)
                        if key not in mirrors_by_source:
                            mirrors_by_source[key] = []
                        mirrors_by_source[key].append(mirror)

                local_stats = {
                    'checked': len(subcal_events),
                    'missing_mirrors': 0,
                    'incorrect_time_mirrors': 0,
                    'fixed': 0,
                    'errors': 0
                }

                self.logger.info(f"  Checking {len(subcal_events)} subcalendar events...")

                for subcal_event in subcal_events:
                    try:
                        source_cal = subcal_event['current_calendar']
                        source_id = subcal_event['event_id']
                        summary = subcal_event['summary']
                        start_time = subcal_event['start_time']

                        key = (source_cal, source_id)
                        mirrors = mirrors_by_source.get(key, [])

                        if not mirrors:
                            # Missing mirror!
                            self.logger.warning(f"  ⚠️  Missing mirror for '{summary}' from subcalendar")
                            local_stats['missing_mirrors'] += 1
                            # TODO: Could auto-create the mirror here

                        elif len(mirrors) == 1:
                            # Check if time is correct
                            mirror = mirrors[0]
                            mirror_start = mirror['start_time']
                            mirror_id = mirror['event_id']

                            # Allow 1 minute tolerance
                            time_diff = abs((mirror_start - start_time).total_seconds())
                            if time_diff > 60:
                                self.logger.warning(
                                    f"  ⚠️  Time mismatch for '{summary}': "
                                    f"DB source={start_time}, DB mirror={mirror_start}"
                                )

                                # Check actual Google Calendar times
                                try:
                                    # Get source event from Google
                                    source_gcal = self._api_call_with_retry(
                                        self.calendar_service.events().get,
                                        calendarId=source_cal,
                                        eventId=source_id
                                    )

                                    # Get mirror event from Google
                                    mirror_gcal = self._api_call_with_retry(
                                        self.calendar_service.events().get,
                                        calendarId=self.work_calendar_id,
                                        eventId=mirror_id
                                    )

                                    if source_gcal and mirror_gcal:
                                        source_gcal_start = source_gcal.get('start', {}).get('dateTime')
                                        mirror_gcal_start = mirror_gcal.get('start', {}).get('dateTime')

                                        if source_gcal_start and mirror_gcal_start:
                                            self.logger.info(
                                                f"    Google Calendar: source={source_gcal_start}, "
                                                f"mirror={mirror_gcal_start}"
                                            )

                                            # If Google Calendar times don't match, fix the mirror
                                            if source_gcal_start != mirror_gcal_start:
                                                self.logger.warning(
                                                    f"    🔧 Fixing mirror time mismatch for '{summary}'"
                                                )

                                                # Update mirror event on Google Calendar
                                                mirror_gcal['start'] = source_gcal.get('start')
                                                mirror_gcal['end'] = source_gcal.get('end')

                                                update_result = self._api_call_with_retry(
                                                    self.calendar_service.events().update,
                                                    calendarId=self.work_calendar_id,
                                                    eventId=mirror_id,
                                                    body=mirror_gcal
                                                )

                                                if update_result:
                                                    self.logger.info(f"    ✅ Fixed mirror time")
                                                    local_stats['fixed'] += 1
                                                else:
                                                    self.logger.error(f"    ❌ Failed to fix mirror time")

                                except Exception as e:
                                    self.logger.error(f"    Error checking/fixing times: {e}")

                                local_stats['incorrect_time_mirrors'] += 1

                        else:
                            # Multiple mirrors - handled by active reconciliation
                            pass

                    except Exception as e:
                        self.logger.error(f"  Error checking subcalendar event: {e}")
                        local_stats['errors'] += 1

                self.logger.info(
                    f"  Found {local_stats['missing_mirrors']} missing mirrors, "
                    f"{local_stats['incorrect_time_mirrors']} time mismatches, "
                    f"{local_stats['fixed']} fixed"
                )

                return local_stats

        except Exception as e:
            self.logger.error(f"Error reconciling subcalendar mirrors: {e}")
            import traceback
            traceback.print_exc()
            return {'errors': 1}

    def run_reconciliation(self) -> Dict[str, Any]:
        """
        Run full reconciliation of work calendar.

        Returns summary statistics.
        """
        self.logger.info("🚀 Starting work calendar reconciliation...")
        self.logger.info(f"📅 Calendar: {self.work_calendar_id}")

        start_time = time.time()

        # Phase 0: Fix data inconsistencies
        consistency_stats = self.fix_data_inconsistencies()

        # Phase 1: Reconcile active events (remove duplicates)
        active_stats = self.reconcile_active_events()

        # Phase 2: Check for orphaned mirrors (source deleted)
        orphan_stats = self.reconcile_orphaned_mirrors()

        # Phase 3: Reconcile deleted events (ensure removal)
        deleted_stats = self.reconcile_deleted_events()

        # Phase 4: Reconcile subcalendar mirrors (detect missing/incorrect mirrors)
        mirror_stats = self.reconcile_subcalendar_mirrors()

        elapsed_time = time.time() - start_time

        # Log summary
        self.logger.info("=" * 60)
        self.logger.info("📊 RECONCILIATION SUMMARY")
        self.logger.info(f"Data inconsistencies fixed: {consistency_stats.get('fixed', 0)}")
        self.logger.info(f"Active events checked: {self.stats['active_events_checked']}")
        self.logger.info(f"Duplicates found: {self.stats['duplicates_found']}")
        self.logger.info(f"Duplicates removed: {self.stats['duplicates_removed']}")
        self.logger.info(f"Events missing from Google: {self.stats['events_missing_from_google']}")
        self.logger.info(f"Orphaned mirrors found: {orphan_stats.get('orphaned', 0)}")
        self.logger.info(f"Orphaned mirrors marked deleted: {orphan_stats.get('marked_deleted', 0)}")
        self.logger.info(f"Deleted events removed: {self.stats['deleted_events_removed']}")
        self.logger.info(f"Subcalendar mirrors checked: {mirror_stats.get('checked', 0)}")
        self.logger.info(f"Missing mirrors: {mirror_stats.get('missing_mirrors', 0)}")
        self.logger.info(f"Time mismatch mirrors: {mirror_stats.get('incorrect_time_mirrors', 0)}")
        self.logger.info(f"Mirrors auto-fixed: {mirror_stats.get('fixed', 0)}")
        self.logger.info(f"Rate limit hits: {self.stats['rate_limit_hits']}")
        self.logger.info(f"Errors: {self.stats['errors']}")
        self.logger.info(f"Time elapsed: {elapsed_time:.2f}s")
        self.logger.info("=" * 60)

        return {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'calendar_id': self.work_calendar_id,
            'stats': self.stats,
            'elapsed_time': elapsed_time
        }


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Reconcile work calendar with database')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🔧 WORK CALENDAR RECONCILIATION SERVICE")
    print("=" * 60)
    print("Ensuring work calendar matches database state:")
    print("  ✓ One event per active database entry")
    print("  ✓ Duplicates removed")
    print("  ✓ Deleted events removed from Google")
    print()

    try:
        reconciler = WorkCalendarReconciler()
        results = reconciler.run_reconciliation()

        print("\n✅ Reconciliation complete!")

        if results['stats']['duplicates_removed'] > 0:
            print(f"   Removed {results['stats']['duplicates_removed']} duplicate events")
        if results['stats']['deleted_events_removed'] > 0:
            print(f"   Removed {results['stats']['deleted_events_removed']} deleted events")
        if results['stats']['events_missing_from_google'] > 0:
            print(f"   ⚠️  {results['stats']['events_missing_from_google']} events missing from Google")

    except Exception as e:
        print(f"\n❌ Reconciliation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
