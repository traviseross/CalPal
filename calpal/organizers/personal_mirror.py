#!/usr/bin/env python3
"""
Personal Calendar Mirror - travis.e.ross@gmail.com → tross@georgefox.edu

Mirrors personal events to work calendar with red color (#CC0000 → colorId 11).
Simpler than old mirror system - just copies events with color.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from calpal.core.db_manager import DatabaseManager


class PersonalMirror:
    """Mirror events from travis.e.ross@gmail.com to tross@georgefox.edu with red color."""

    def __init__(self):
        self.logger = logging.getLogger('personal-mirror')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Calendar IDs
        self.personal_calendar = PERSONAL_CALENDAR_ID  # travis.e.ross@gmail.com
        self.work_calendar = WORK_CALENDAR_ID  # tross@georgefox.edu

        # Color for personal events: Red (colorId 11 - Tomato, closest to #CC0000)
        self.personal_color = '11'

    def _initialize_calendar_service(self):
        """Initialize Google Calendar API service."""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("✅ Google Calendar API service initialized")
            return service
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Calendar API: {e}")
            raise

    def get_personal_events(self, days_back: int = 7, days_forward: int = 365) -> List[Dict]:
        """Get events from personal calendar."""
        time_min = (datetime.now() - timedelta(days=days_back)).isoformat() + 'Z'
        time_max = (datetime.now() + timedelta(days=days_forward)).isoformat() + 'Z'

        try:
            self.logger.debug(f"Fetching events from {self.personal_calendar}")

            events_result = self.calendar_service.events().list(
                calendarId=self.personal_calendar,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                maxResults=2500
            ).execute()

            events = events_result.get('items', [])
            self.logger.info(f"  Found {len(events)} events on personal calendar")
            return events

        except HttpError as e:
            self.logger.error(f"Error fetching personal events: {e}")
            return []

    def check_mirror_exists(self, source_event_id: str) -> Optional[str]:
        """Check if mirror already exists on work calendar."""
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT event_id
                        FROM calendar_events
                        WHERE metadata->>'source_event_id' = :source_id
                        AND current_calendar = :work_cal
                        AND deleted_at IS NULL
                        LIMIT 1
                    """),
                    {
                        'source_id': source_event_id,
                        'work_cal': self.work_calendar
                    }
                ).scalar()

                return result

        except Exception as e:
            self.logger.error(f"Error checking for mirror: {e}")
            return None

    def create_mirror(self, source_event: Dict) -> Optional[str]:
        """Create mirror of personal event on work calendar with red color."""
        try:
            # Build event body
            mirror_event = {
                'summary': source_event.get('summary', 'Untitled'),
                'description': source_event.get('description', ''),
                'location': source_event.get('location', ''),
                'colorId': self.personal_color,  # Red
                'extendedProperties': {
                    'private': {
                        'source': 'personal_mirror',
                        'source_event_id': source_event['id'],
                        'source_calendar': self.personal_calendar,
                        'event_type': 'personal_work_mirror'
                    }
                }
            }

            # Copy start/end times
            if 'dateTime' in source_event['start']:
                mirror_event['start'] = source_event['start']
                mirror_event['end'] = source_event['end']
            else:
                # All-day event
                mirror_event['start'] = source_event['start']
                mirror_event['end'] = source_event['end']

            # Copy recurrence if present
            if 'recurrence' in source_event:
                mirror_event['recurrence'] = source_event['recurrence']

            time.sleep(0.1)  # Rate limiting

            created_event = self.calendar_service.events().insert(
                calendarId=self.work_calendar,
                body=mirror_event
            ).execute()

            self.logger.debug(f"  Created mirror: {created_event['id']}")
            return created_event['id']

        except HttpError as e:
            self.logger.error(f"Error creating mirror: {e}")
            return None

    def record_mirror_in_db(self, source_event: Dict, mirror_event_id: str):
        """Record mirror event in database."""
        try:
            # Parse times
            start_data = source_event['start']
            end_data = source_event['end']

            if 'dateTime' in start_data:
                start_time = datetime.fromisoformat(start_data['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end_data['dateTime'].replace('Z', '+00:00'))
                is_all_day = False
            else:
                start_time = datetime.fromisoformat(start_data['date'])
                end_time = datetime.fromisoformat(end_data['date'])
                is_all_day = True

            event_data = {
                'event_id': mirror_event_id,
                'ical_uid': source_event.get('iCalUID'),
                'summary': source_event.get('summary', 'Untitled'),
                'description': source_event.get('description', ''),
                'location': source_event.get('location', ''),
                'start_time': start_time,
                'end_time': end_time,
                'is_all_day': is_all_day,
                'source_calendar': self.personal_calendar,
                'current_calendar': self.work_calendar,
                'event_type': 'personal_work_mirror',
                'status': 'active',
                'last_action': 'created',
                'metadata': {
                    'source_event_id': source_event['id'],
                    'color_id': self.personal_color,
                    'mirror_type': 'personal'
                }
            }

            if self.db.record_event(event_data):
                self.logger.debug(f"  Recorded in database")
            else:
                self.logger.warning(f"  Failed to record in database")

        except Exception as e:
            self.logger.error(f"Error recording in database: {e}")

    def sync_personal_events(self) -> Dict:
        """Sync personal events to work calendar."""
        self.logger.info("🔄 Syncing personal calendar → work calendar")
        self.logger.info(f"   Personal: {self.personal_calendar}")
        self.logger.info(f"   Work: {self.work_calendar}")
        self.logger.info(f"   Color: {self.personal_color} (Red)")

        stats = {
            'total_personal_events': 0,
            'mirrors_created': 0,
            'already_mirrored': 0,
            'errors': 0
        }

        # Get personal events
        personal_events = self.get_personal_events()
        stats['total_personal_events'] = len(personal_events)

        for event in personal_events:
            try:
                event_id = event['id']
                summary = event.get('summary', 'Untitled')

                # Check if mirror already exists
                existing_mirror = self.check_mirror_exists(event_id)
                if existing_mirror:
                    stats['already_mirrored'] += 1
                    continue

                # Create mirror
                self.logger.info(f"  Mirroring: {summary[:50]}")
                mirror_id = self.create_mirror(event)

                if mirror_id:
                    # Record in database
                    self.record_mirror_in_db(event, mirror_id)
                    stats['mirrors_created'] += 1
                else:
                    stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
                stats['errors'] += 1

        self.logger.info(f"✅ Personal mirror sync complete:")
        self.logger.info(f"  Personal events: {stats['total_personal_events']}")
        self.logger.info(f"  Mirrors created: {stats['mirrors_created']}")
        self.logger.info(f"  Already mirrored: {stats['already_mirrored']}")
        self.logger.info(f"  Errors: {stats['errors']}")

        return stats


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Mirror personal calendar to work calendar')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("PERSONAL CALENDAR MIRROR")
    print("=" * 60)
    print("travis.e.ross@gmail.com → tross@georgefox.edu (Red)")
    print("=" * 60)
    print()

    mirror = PersonalMirror()
    stats = mirror.sync_personal_events()

    print("\n✅ Sync complete!")


if __name__ == '__main__':
    main()
