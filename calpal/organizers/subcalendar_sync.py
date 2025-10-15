#!/usr/bin/env python3
"""
Subcalendar → Work Bidirectional Sync Service

Ensures all events on subcalendars also appear as mirrors on Work calendar:
- Classes → Work (mirror with full details)
- GFU Events → Work (mirror with full details)
- Appointments → Work (mirror with full details)
- Meetings → Work (mirror with full details)

Rules:
- Check database before creating any mirror
- Track all mirrors with metadata linking to source
- Skip events that are already mirrors FROM Work
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import text

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from calpal.core.db_manager import DatabaseManager


class SubcalendarWorkSync:
    """Sync subcalendar events to Work calendar."""

    def __init__(self):
        self.logger = logging.getLogger('subcalendar-work-sync')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Load calendar IDs
        self.load_calendars()

        # Load event blacklist
        self.load_event_blacklist()

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

    def load_calendars(self):
        """Load all calendar IDs."""
        self.work_calendar = WORK_CALENDAR_ID

        # Load subcalendars
        subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
        with open(subcalendars_file, 'r') as f:
            subcalendars = json.load(f)

        # Subcalendars to sync to Work
        self.subcalendars = {
            'Classes': subcalendars['Classes'],
            'GFU Events': subcalendars['GFU Events'],
            'Appointments': subcalendars['Appointments'],
            'Meetings': subcalendars['Meetings']
        }

        self.logger.info("✅ Loaded calendar IDs")

    def load_event_blacklist(self):
        """Load event blacklist from event_blacklist.json."""
        try:
            import re
            blacklist_file = os.path.join(DATA_DIR, 'event_blacklist.json')
            with open(blacklist_file, 'r') as f:
                blacklist_data = json.load(f)

            self.blacklisted_events = set(blacklist_data.get('blacklisted_events', []))
            self.blacklist_patterns = [
                re.compile(pattern)
                for pattern in blacklist_data.get('blacklist_patterns', [])
            ]

            self.logger.info(f"✅ Loaded event blacklist ({len(self.blacklisted_events)} exact matches, {len(self.blacklist_patterns)} patterns)")
        except FileNotFoundError:
            self.logger.warning("⚠️  No event blacklist file found, allowing all events")
            self.blacklisted_events = set()
            self.blacklist_patterns = []
        except Exception as e:
            self.logger.error(f"❌ Failed to load event blacklist: {e}")
            self.blacklisted_events = set()
            self.blacklist_patterns = []

    def is_event_blacklisted(self, summary: str) -> bool:
        """Check if event summary is blacklisted."""
        # Check exact matches
        if summary in self.blacklisted_events:
            return True

        # Check regex patterns
        for pattern in self.blacklist_patterns:
            if pattern.search(summary):
                return True

        return False

    def _get_color_for_source(self, source_calendar_id: str) -> str:
        """
        Get Google Calendar colorId for source calendar.

        Color IDs:
        - 9: Blue (Classes)
        - 10: Green (GFU Events)
        - 5: Yellow (Appointments)
        - 11: Red (Meetings)
        """
        # Match against known subcalendars
        if source_calendar_id == self.subcalendars.get('Classes'):
            return '9'  # Blue
        elif source_calendar_id == self.subcalendars.get('GFU Events'):
            return '10'  # Green
        elif source_calendar_id == self.subcalendars.get('Appointments'):
            return '5'  # Yellow
        elif source_calendar_id == self.subcalendars.get('Meetings'):
            return '11'  # Red
        else:
            return '1'  # Default: Lavender

    def get_subcalendar_events(self, calendar_id: str) -> List[Dict]:
        """Get all events from a subcalendar that should be mirrored."""
        try:
            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        AND status = 'active'
                        ORDER BY start_time
                    """),
                    {"calendar_id": calendar_id}
                ).mappings().all()

                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error fetching subcalendar events: {e}")
            return []

    def is_mirror_from_work(self, event: Dict) -> bool:
        """Check if this event is already a mirror FROM Work (don't re-mirror)."""
        metadata = event.get('metadata', {})

        # Check if this is a mirror from Work calendar
        mirror_source = metadata.get('mirror_source', '')
        if mirror_source == self.work_calendar:
            return True

        # Check event_type patterns
        event_type = event.get('event_type', '')
        if 'work_mirror' in event_type or event_type == 'meeting_mirror':
            return True

        return False

    def event_exists_on_work_by_icaluid(self, ical_uid: str) -> bool:
        """Check if an event with this ical_uid already exists on Work calendar (not created by service account).

        This is used to prevent mirroring events from Appointments back to Work when they
        originated on Work (e.g., booking events that were moved to Appointments).
        """
        if not ical_uid:
            return False

        try:
            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT event_id FROM calendar_events
                        WHERE current_calendar = :work_cal
                        AND ical_uid = :ical_uid
                        AND deleted_at IS NULL
                        AND (creator_email != 'mycalpal@calendar-472406.iam.gserviceaccount.com'
                             OR creator_email IS NULL)
                        LIMIT 1
                    """),
                    {"work_cal": self.work_calendar, "ical_uid": ical_uid}
                ).scalar()

                return result is not None
        except Exception as e:
            self.logger.error(f"Error checking event on work by ical_uid: {e}")
            return False

    def check_mirror_exists(self, source_event_id: str, target_calendar: str) -> Optional[str]:
        """Check if mirror already exists on target calendar."""
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT event_id FROM calendar_events
                        WHERE metadata->>'source_event_id' = :source_id
                        AND current_calendar = :target_cal
                        AND deleted_at IS NULL
                        LIMIT 1
                    """),
                    {"source_id": source_event_id, "target_cal": target_calendar}
                ).scalar()

                return result
        except Exception as e:
            self.logger.error(f"Error checking mirror exists: {e}")
            return None

    def create_work_mirror(self, source_event: Dict) -> Optional[str]:
        """Create mirror of subcalendar event on Work calendar."""
        try:
            # Get event details
            summary = source_event.get('summary', 'Untitled')
            description = source_event.get('description', '')
            location = source_event.get('location', '')
            start_time = source_event['start_time']
            end_time = source_event['end_time']
            is_all_day = source_event.get('is_all_day', False)

            # Determine color based on source calendar
            source_calendar_id = source_event['current_calendar']
            color_id = self._get_color_for_source(source_calendar_id)

            # Build event body
            if is_all_day:
                event_body = {
                    'summary': summary,
                    'description': description,
                    'location': location,
                    'start': {
                        'date': start_time.strftime('%Y-%m-%d'),
                        'timeZone': 'America/Los_Angeles'
                    },
                    'end': {
                        'date': end_time.strftime('%Y-%m-%d'),
                        'timeZone': 'America/Los_Angeles'
                    },
                    'colorId': color_id
                }
            else:
                event_body = {
                    'summary': summary,
                    'description': description,
                    'location': location,
                    'start': {
                        'dateTime': start_time.isoformat(),
                        'timeZone': 'America/Los_Angeles'
                    },
                    'end': {
                        'dateTime': end_time.isoformat(),
                        'timeZone': 'America/Los_Angeles'
                    },
                    'colorId': color_id
                }

            # Add metadata
            event_body['extendedProperties'] = {
                'private': {
                    'mirror_source': source_event['current_calendar'],
                    'mirror_type': 'subcalendar_to_work',
                    'source_event_id': source_event['event_id'],
                    'source_ical_uid': source_event.get('ical_uid', '')
                }
            }

            # Create mirror
            created_event = self.calendar_service.events().insert(
                calendarId=self.work_calendar,
                body=event_body
            ).execute()

            return created_event['id']

        except HttpError as e:
            self.logger.error(f"Failed to create work mirror: {e}")
            return None

    def find_mirror_on_google_calendar(self, source_event_id: str, summary: str,
                                       start_time: datetime) -> Optional[str]:
        """
        Search Google Calendar for existing mirror of this source event.
        Returns event_id if found, None otherwise.
        """
        try:
            from datetime import timedelta

            # Search by time and summary
            events_result = self.calendar_service.events().list(
                calendarId=self.work_calendar,
                timeMin=start_time.isoformat(),
                timeMax=(start_time + timedelta(minutes=1)).isoformat(),
                q=summary,
                singleEvents=True
            ).execute()

            events = events_result.get('items', [])

            # Check extended properties for source_event_id match
            for event in events:
                ext_props = event.get('extendedProperties', {})
                private = ext_props.get('private', {})

                if private.get('source_event_id') == source_event_id:
                    return event.get('id')

            return None
        except Exception as e:
            self.logger.error(f"Error searching Google Calendar: {e}")
            return None

    def sync_subcalendar(self, calendar_name: str, calendar_id: str) -> Dict[str, int]:
        """Sync a subcalendar to Work."""
        stats = {
            'events_found': 0,
            'mirrors_created': 0,
            'already_mirrored': 0,
            'skipped_work_mirrors': 0,
            'skipped_already_on_work': 0,
            'skipped_duplicate_time': 0,
            'errors': 0
        }

        self.logger.info(f"🔄 Syncing {calendar_name} → Work...")

        # Get all events from subcalendar
        events = self.get_subcalendar_events(calendar_id)
        stats['events_found'] = len(events)

        self.logger.info(f"  Found {len(events)} events to process")

        # Track seen time blocks to de-duplicate recurring event instances
        seen_time_blocks = set()

        # Process in batches with progress logging
        for i, event in enumerate(events, 1):
            try:
                event_id = event['event_id']
                ical_uid = event.get('ical_uid')
                summary = event.get('summary', 'Untitled')
                start_time = event['start_time']

                # Skip if this is already a mirror FROM Work
                if self.is_mirror_from_work(event):
                    stats['skipped_work_mirrors'] += 1
                    continue

                # Skip if event is blacklisted
                if self.is_event_blacklisted(summary):
                    self.logger.debug(f"Skipping blacklisted event: {summary}")
                    stats['skipped_work_mirrors'] += 1  # Reuse this counter
                    continue

                # Skip if this event already exists on Work (by ical_uid) and wasn't created by service account
                # This prevents mirroring booking events from Appointments back to Work when they originated there
                if self.event_exists_on_work_by_icaluid(ical_uid):
                    stats['skipped_already_on_work'] += 1
                    continue

                # De-duplicate recurring event instances: skip if we've already mirrored this time block
                time_block_key = (summary, start_time, calendar_id)
                if time_block_key in seen_time_blocks:
                    stats['skipped_duplicate_time'] += 1
                    continue

                # CRITICAL: Check database for existing mirror at this time/summary/calendar
                # This prevents creating duplicates across sync runs
                existing_time_mirror = self.db.get_event_by_time_and_summary(
                    summary=summary,
                    start_time=start_time,
                    calendar_id=self.work_calendar
                )
                if existing_time_mirror and existing_time_mirror.get('event_type') == 'subcalendar_work_mirror':
                    stats['skipped_duplicate_time'] += 1
                    seen_time_blocks.add(time_block_key)
                    continue

                # Use advisory lock to prevent concurrent mirror creation
                lock_key = f"mirror:{event_id}:{self.work_calendar}"

                with self.db.advisory_lock(lock_key):
                    # Check if mirror exists on Google Calendar (idempotent)
                    existing_on_google = self.find_mirror_on_google_calendar(
                        event_id,
                        summary,
                        start_time
                    )

                    if existing_on_google:
                        # Mirror already exists, just ensure it's in database
                        mirror_data = {
                            'event_id': existing_on_google,
                            'ical_uid': event.get('ical_uid'),
                            'summary': summary,
                            'description': event.get('description', ''),
                            'location': event.get('location', ''),
                            'start_time': start_time,
                            'end_time': event['end_time'],
                            'source_calendar': calendar_id,
                            'current_calendar': self.work_calendar,
                            'event_type': 'subcalendar_work_mirror',
                            'status': 'active',
                            'is_all_day': event.get('is_all_day', False),
                            'metadata': {
                                'mirror_source': calendar_id,
                                'source_event_id': event_id,
                                'is_mirror': True,
                                'subcalendar_name': calendar_name,
                                'original_summary': summary
                            }
                        }
                        self.db.upsert_mirror_event(mirror_data)
                        stats['already_mirrored'] += 1
                        seen_time_blocks.add(time_block_key)
                    else:
                        # Create new mirror
                        mirror_id = self.create_work_mirror(event)

                        if mirror_id:
                            # Record in database
                            mirror_data = {
                                'event_id': mirror_id,
                                'ical_uid': event.get('ical_uid'),
                                'summary': summary,
                                'description': event.get('description', ''),
                                'location': event.get('location', ''),
                                'start_time': start_time,
                                'end_time': event['end_time'],
                                'source_calendar': calendar_id,
                                'current_calendar': self.work_calendar,
                                'event_type': 'subcalendar_work_mirror',
                                'status': 'active',
                                'is_all_day': event.get('is_all_day', False),
                                'metadata': {
                                    'mirror_source': calendar_id,
                                    'source_event_id': event_id,
                                    'is_mirror': True,
                                    'subcalendar_name': calendar_name,
                                    'original_summary': summary
                                }
                            }
                            self.db.upsert_mirror_event(mirror_data)
                            stats['mirrors_created'] += 1
                            seen_time_blocks.add(time_block_key)
                        else:
                            stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing event {event.get('summary', 'Unknown')}: {e}")
                stats['errors'] += 1

            # Progress logging every 100 events
            if i % 100 == 0:
                self.logger.info(f"  Progress: {i}/{len(events)} events processed...")

        return stats

    def run_sync(self) -> Dict[str, Any]:
        """Run complete subcalendar → Work sync."""
        self.logger.info("🚀 Starting subcalendar → Work sync...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'subcalendars': {}
        }

        # Sync each subcalendar
        for name, calendar_id in self.subcalendars.items():
            stats = self.sync_subcalendar(name, calendar_id)
            results['subcalendars'][name] = stats

        # Summary
        self.logger.info("=" * 60)
        self.logger.info("📊 SUBCALENDAR → WORK SYNC SUMMARY")

        total_found = 0
        total_created = 0
        total_already = 0
        total_skipped_mirrors = 0
        total_skipped_on_work = 0
        total_errors = 0

        for name, stats in results['subcalendars'].items():
            self.logger.info(f"\n{name}:")
            self.logger.info(f"  Events found: {stats['events_found']}")
            self.logger.info(f"  Mirrors created: {stats['mirrors_created']}")
            self.logger.info(f"  Already mirrored: {stats['already_mirrored']}")
            self.logger.info(f"  Skipped (work mirrors): {stats['skipped_work_mirrors']}")
            self.logger.info(f"  Skipped (already on work): {stats['skipped_already_on_work']}")
            self.logger.info(f"  Skipped (duplicate times): {stats.get('skipped_duplicate_time', 0)}")
            self.logger.info(f"  Errors: {stats['errors']}")

            total_found += stats['events_found']
            total_created += stats['mirrors_created']
            total_already += stats['already_mirrored']
            total_skipped_mirrors += stats['skipped_work_mirrors']
            total_skipped_on_work += stats['skipped_already_on_work']
            total_errors += stats['errors']

        self.logger.info(f"\n📊 TOTALS:")
        self.logger.info(f"  Total events: {total_found}")
        self.logger.info(f"  Total mirrors created: {total_created}")
        self.logger.info(f"  Already mirrored: {total_already}")
        self.logger.info(f"  Skipped work mirrors: {total_skipped_mirrors}")
        self.logger.info(f"  Skipped already on work: {total_skipped_on_work}")
        self.logger.info(f"  Total errors: {total_errors}")
        self.logger.info("=" * 60)

        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Sync subcalendars to Work calendar')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🔄 SUBCALENDAR → WORK SYNC")
    print("=" * 50)
    print("Mirroring Classes, GFU Events, Appointments, Meetings → Work")
    print()

    syncer = SubcalendarWorkSync()
    results = syncer.run_sync()

    print("\n✅ Sync complete!")


if __name__ == '__main__':
    main()
