#!/usr/bin/env python3
"""
Personal and Family Calendar Mirror Service

Mirrors events from Personal and Family calendars to work subcalendars:
- travis.e.ross@gmail.com → Personal Events (full details) → Work (Busy only)
- Ross Family → Family Events (full details) → Work (Busy only)

Rules:
- Full event details shown on Personal Events and Family Events subcalendars
- Only "Busy" (no details) mirrored to Work root calendar
- If user deletes from subcalendar: remove from Work, mark in DB as do_not_mirror
- Recurring all-day events: once deleted, never re-mirror
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
from src.db_manager import DatabaseManager


class PersonalFamilyMirror:
    """Mirror personal and family calendar events."""

    def __init__(self):
        self.logger = logging.getLogger('personal-family-mirror')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Load calendar IDs
        self.load_calendars()

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
        self.personal_source = PERSONAL_CALENDAR_ID  # travis.e.ross@gmail.com
        self.family_source = '63cbe19d6ecd1869e68c4b46a96a705e6d0f9d3e31af6b2c251cb6ed81f26ad0@group.calendar.google.com'
        self.work_calendar = WORK_CALENDAR_ID

        # Load subcalendars
        subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
        with open(subcalendars_file, 'r') as f:
            subcalendars = json.load(f)

        self.personal_events = subcalendars['Personal Events']
        self.family_events = subcalendars['Family Events']

        self.logger.info("✅ Loaded calendar IDs")

    def check_do_not_mirror(self, ical_uid: str, event_type: str) -> bool:
        """Check if event should not be mirrored (user deleted it before)."""
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT do_not_mirror FROM calendar_events
                        WHERE ical_uid = :ical_uid
                        AND event_type = :event_type
                        AND do_not_mirror = TRUE
                        LIMIT 1
                    """),
                    {"ical_uid": ical_uid, "event_type": event_type}
                ).scalar()

                return result is not None
        except Exception as e:
            self.logger.error(f"Error checking do_not_mirror: {e}")
            return False

    def mark_do_not_mirror(self, ical_uid: str, event_type: str):
        """Mark event as do not mirror."""
        try:
            with self.db.get_session() as session:
                session.execute(
                    text("""
                        UPDATE calendar_events
                        SET do_not_mirror = TRUE
                        WHERE ical_uid = :ical_uid
                        AND event_type = :event_type
                    """),
                    {"ical_uid": ical_uid, "event_type": event_type}
                )
                self.logger.info(f"Marked {ical_uid} as do_not_mirror")
        except Exception as e:
            self.logger.error(f"Error marking do_not_mirror: {e}")

    def get_source_events(self, calendar_id: str, event_type: str) -> List[Dict]:
        """Get events from database that need mirroring."""
        try:
            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE source_calendar = :calendar_id
                        AND event_type = :event_type
                        AND deleted_at IS NULL
                        AND COALESCE(do_not_mirror, FALSE) = FALSE
                        ORDER BY start_time
                    """),
                    {"calendar_id": calendar_id, "event_type": event_type}
                ).mappings().all()

                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error fetching source events: {e}")
            import traceback
            traceback.print_exc()
            return []

    def create_mirror_event(self, source_event: Dict, target_calendar: str,
                           show_as_busy: bool = False) -> Optional[str]:
        """Create a mirror event on target calendar."""
        try:
            # Determine title
            if show_as_busy:
                summary = "Busy"
                description = ""
                location = ""
            else:
                summary = source_event.get('summary', 'Untitled')
                description = source_event.get('description', '')
                location = source_event.get('location', '')

            # Handle times
            start_time = source_event['start_time']
            end_time = source_event['end_time']

            # Check if all-day event
            is_all_day = source_event.get('is_all_day', False)

            if is_all_day:
                event_body = {
                    'summary': summary,
                    'description': description,
                    'start': {
                        'date': start_time.strftime('%Y-%m-%d'),
                        'timeZone': 'America/Los_Angeles'
                    },
                    'end': {
                        'date': end_time.strftime('%Y-%m-%d'),
                        'timeZone': 'America/Los_Angeles'
                    }
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
                    }
                }

            # Add metadata to track mirror relationship
            event_body['extendedProperties'] = {
                'private': {
                    'mirror_source': source_event['source_calendar'],
                    'mirror_type': 'personal_family',
                    'source_ical_uid': source_event.get('ical_uid', ''),
                    'source_event_id': source_event['event_id']
                }
            }

            # Create event
            created_event = self.calendar_service.events().insert(
                calendarId=target_calendar,
                body=event_body
            ).execute()

            return created_event['id']

        except HttpError as e:
            self.logger.error(f"Failed to create mirror event: {e}")
            return None

    def find_mirror_on_google_calendar(self, source_event_id: str, target_calendar: str,
                                       summary: str, start_time: datetime) -> Optional[str]:
        """
        Search Google Calendar for existing mirror of this source event.
        Returns event_id if found, None otherwise.
        """
        try:
            from datetime import timedelta

            # Search by time and summary
            events_result = self.calendar_service.events().list(
                calendarId=target_calendar,
                timeMin=start_time.isoformat(),
                timeMax=(start_time + timedelta(minutes=1)).isoformat(),
                q=summary if summary != 'Busy' else '',  # Don't search for "Busy"
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

    def check_mirror_exists(self, source_event_id: str, target_calendar: str) -> Optional[str]:
        """Check if mirror already exists on target calendar."""
        try:
            with self.db.get_session() as session:
                from sqlalchemy import text
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

    def mirror_calendar(self, source_calendar: str, subcalendar: str,
                       event_type: str, calendar_name: str) -> Dict[str, int]:
        """Mirror events from source to subcalendar and work."""
        stats = {
            'events_found': 0,
            'subcalendar_created': 0,
            'work_created': 0,
            'already_mirrored': 0,
            'do_not_mirror': 0,
            'errors': 0
        }

        self.logger.info(f"🔄 Mirroring {calendar_name}...")

        # Get events from database
        source_events = self.get_source_events(source_calendar, event_type)
        stats['events_found'] = len(source_events)

        self.logger.info(f"  Found {len(source_events)} events to process")

        for event in source_events:
            try:
                ical_uid = event.get('ical_uid')
                event_id = event['event_id']

                # Check if marked as do_not_mirror
                if self.check_do_not_mirror(ical_uid, event_type):
                    stats['do_not_mirror'] += 1
                    continue

                # Use advisory lock for subcalendar mirror
                lock_key = f"mirror:{event_id}:{subcalendar}"

                with self.db.advisory_lock(lock_key):
                    # Check if mirror exists on Google Calendar (idempotent)
                    existing_on_google = self.find_mirror_on_google_calendar(
                        event_id,
                        subcalendar,
                        event['summary'],
                        event['start_time']
                    )

                    if existing_on_google:
                        # Mirror already exists, ensure it's in database
                        subcal_mirror_id = existing_on_google
                        mirror_data = {
                            'event_id': subcal_mirror_id,
                            'ical_uid': ical_uid,
                            'summary': event['summary'],
                            'description': event.get('description', ''),
                            'location': event.get('location', ''),
                            'start_time': event['start_time'],
                            'end_time': event['end_time'],
                            'source_calendar': source_calendar,
                            'current_calendar': subcalendar,
                            'event_type': f"{event_type}_mirror",
                            'status': 'active',
                            'is_all_day': event.get('is_all_day', False),
                            'metadata': {
                                'mirror_source': source_calendar,
                                'source_event_id': event_id,
                                'is_mirror': True,
                                'original_summary': event['summary']
                            }
                        }
                        self.db.upsert_mirror_event(mirror_data)
                        stats['already_mirrored'] += 1
                    else:
                        # Create new mirror
                        subcal_mirror_id = self.create_mirror_event(
                            event, subcalendar, show_as_busy=False
                        )

                        if subcal_mirror_id:
                            mirror_data = {
                                'event_id': subcal_mirror_id,
                                'ical_uid': ical_uid,
                                'summary': event['summary'],
                                'description': event.get('description', ''),
                                'location': event.get('location', ''),
                                'start_time': event['start_time'],
                                'end_time': event['end_time'],
                                'source_calendar': source_calendar,
                                'current_calendar': subcalendar,
                                'event_type': f"{event_type}_mirror",
                                'status': 'active',
                                'is_all_day': event.get('is_all_day', False),
                                'metadata': {
                                    'mirror_source': source_calendar,
                                    'source_event_id': event_id,
                                    'is_mirror': True,
                                    'original_summary': event['summary']
                                }
                            }
                            self.db.upsert_mirror_event(mirror_data)
                            stats['subcalendar_created'] += 1
                        else:
                            stats['errors'] += 1

                # Use advisory lock for work mirror
                work_lock_key = f"mirror:{event_id}:{self.work_calendar}"

                with self.db.advisory_lock(work_lock_key):
                    # Check if mirror exists on Google Calendar (idempotent)
                    existing_work_on_google = self.find_mirror_on_google_calendar(
                        event_id,
                        self.work_calendar,
                        'Busy',
                        event['start_time']
                    )

                    if existing_work_on_google:
                        # Mirror already exists, ensure it's in database
                        work_data = {
                            'event_id': existing_work_on_google,
                            'ical_uid': ical_uid,
                            'summary': 'Busy',
                            'description': '',
                            'location': '',
                            'start_time': event['start_time'],
                            'end_time': event['end_time'],
                            'source_calendar': source_calendar,
                            'current_calendar': self.work_calendar,
                            'event_type': f"{event_type}_work_mirror",
                            'status': 'active',
                            'is_all_day': event.get('is_all_day', False),
                            'metadata': {
                                'mirror_source': source_calendar,
                                'source_event_id': event_id,
                                'is_busy_mirror': True,
                                'subcalendar_mirror': subcal_mirror_id
                            }
                        }
                        self.db.upsert_mirror_event(work_data)
                        stats['already_mirrored'] += 1
                    else:
                        # Create new work mirror
                        work_mirror_id = self.create_mirror_event(
                            event, self.work_calendar, show_as_busy=True
                        )

                        if work_mirror_id:
                            work_data = {
                                'event_id': work_mirror_id,
                                'ical_uid': ical_uid,
                                'summary': 'Busy',
                                'description': '',
                                'location': '',
                                'start_time': event['start_time'],
                                'end_time': event['end_time'],
                                'source_calendar': source_calendar,
                                'current_calendar': self.work_calendar,
                                'event_type': f"{event_type}_work_mirror",
                                'status': 'active',
                                'is_all_day': event.get('is_all_day', False),
                                'metadata': {
                                    'mirror_source': source_calendar,
                                    'source_event_id': event_id,
                                    'is_busy_mirror': True,
                                    'subcalendar_mirror': subcal_mirror_id
                                }
                            }
                            self.db.upsert_mirror_event(work_data)
                            stats['work_created'] += 1
                        else:
                            stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing event {event.get('summary', 'Unknown')}: {e}")
                stats['errors'] += 1

        return stats

    def run_mirror_sync(self) -> Dict[str, Any]:
        """Run complete mirror synchronization."""
        self.logger.info("🚀 Starting Personal/Family mirror sync...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'mirrors': {}
        }

        # Mirror Personal calendar
        personal_stats = self.mirror_calendar(
            source_calendar=self.personal_source,
            subcalendar=self.personal_events,
            event_type='personal',
            calendar_name='Personal Calendar'
        )
        results['mirrors']['Personal'] = personal_stats

        # Mirror Family calendar
        family_stats = self.mirror_calendar(
            source_calendar=self.family_source,
            subcalendar=self.family_events,
            event_type='family',
            calendar_name='Ross Family'
        )
        results['mirrors']['Family'] = family_stats

        # Summary
        self.logger.info("=" * 60)
        self.logger.info("📊 MIRROR SYNC SUMMARY")
        for name, stats in results['mirrors'].items():
            self.logger.info(f"\n{name}:")
            self.logger.info(f"  Events found: {stats['events_found']}")
            self.logger.info(f"  Subcalendar created: {stats['subcalendar_created']}")
            self.logger.info(f"  Work created: {stats['work_created']}")
            self.logger.info(f"  Already mirrored: {stats['already_mirrored']}")
            self.logger.info(f"  Do not mirror: {stats['do_not_mirror']}")
            self.logger.info(f"  Errors: {stats['errors']}")

        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Mirror Personal and Family calendars')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🔄 PERSONAL/FAMILY CALENDAR MIRROR")
    print("=" * 50)
    print()

    mirror = PersonalFamilyMirror()
    results = mirror.run_mirror_sync()

    print("\n✅ Mirror sync complete!")


if __name__ == '__main__':
    main()
