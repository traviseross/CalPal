#!/usr/bin/env python3
"""
Work Event Organizer Service

Organizes work calendar events into appropriate subcalendars:
- Booking events: MOVE from Work → Appointments
- Meeting invitations: MIRROR from Work → Meetings (full details)

Rules:
- Booking events are moved (they disappear from Work list but stay visible)
- Meeting invitations cannot be moved (not the organizer), so we create mirrors
- Database tracks all moves and mirrors to prevent duplicates
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


class WorkEventOrganizer:
    """Organize work calendar events into subcalendars."""

    def __init__(self):
        self.logger = logging.getLogger('work-event-organizer')

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
        self.work_calendar = WORK_CALENDAR_ID

        # Load subcalendars
        subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
        with open(subcalendars_file, 'r') as f:
            subcalendars = json.load(f)

        self.appointments = subcalendars['Appointments']
        self.meetings = subcalendars['Meetings']

        self.logger.info("✅ Loaded calendar IDs")

    def get_booking_events(self) -> List[Dict]:
        """Get booking events from database that need to be moved."""
        try:
            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE event_type = 'booking'
                        AND current_calendar = :work_calendar
                        AND deleted_at IS NULL
                        ORDER BY start_time
                    """),
                    {"work_calendar": self.work_calendar}
                ).mappings().all()

                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error fetching booking events: {e}")
            return []

    def get_meeting_invitations(self) -> List[Dict]:
        """Get meeting invitation events that need mirroring."""
        try:
            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE event_type = 'meeting_invitation'
                        AND current_calendar = :work_calendar
                        AND is_attendee_event = TRUE
                        AND deleted_at IS NULL
                        ORDER BY start_time
                    """),
                    {"work_calendar": self.work_calendar}
                ).mappings().all()

                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error fetching meeting invitations: {e}")
            return []

    def check_event_on_calendar(self, event_id: str, calendar_id: str) -> bool:
        """Check if event already exists on target calendar."""
        existing = self.db.get_event_by_id(event_id, calendar_id)
        return existing is not None

    def check_mirror_exists(self, source_event_id: str, target_calendar: str) -> Optional[str]:
        """Check if mirror of this event already exists."""
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
            self.logger.error(f"Error checking mirror: {e}")
            return None

    def move_event(self, event_id: str, source_calendar: str, target_calendar: str) -> bool:
        """Move event from source to target calendar."""
        try:
            # Use Google Calendar move API
            moved_event = self.calendar_service.events().move(
                calendarId=source_calendar,
                eventId=event_id,
                destination=target_calendar
            ).execute()

            self.logger.info(f"✅ Moved event {event_id}")
            return True

        except HttpError as e:
            if 'Resource has been deleted' in str(e):
                self.logger.warning(f"Event {event_id} already deleted")
            else:
                self.logger.error(f"Failed to move event {event_id}: {e}")
            return False

    def create_meeting_mirror(self, source_event: Dict) -> Optional[str]:
        """Create a mirror of meeting invitation on Meetings calendar."""
        try:
            # Get full details from source event
            start_time = source_event['start_time']
            end_time = source_event['end_time']

            # Create event body with full details
            event_body = {
                'summary': source_event.get('summary', 'Untitled Meeting'),
                'description': source_event.get('description', ''),
                'location': source_event.get('location', ''),
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'America/Los_Angeles'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'America/Los_Angeles'
                },
                'extendedProperties': {
                    'private': {
                        'mirror_source': 'meeting_invitation',
                        'source_event_id': source_event['event_id'],
                        'source_ical_uid': source_event.get('ical_uid', ''),
                        'original_organizer': source_event.get('organizer_email', '')
                    }
                }
            }

            # Create mirror event
            created_event = self.calendar_service.events().insert(
                calendarId=self.meetings,
                body=event_body
            ).execute()

            mirror_id = created_event['id']
            self.logger.info(f"✅ Created meeting mirror: {source_event.get('summary', 'Untitled')}")
            return mirror_id

        except HttpError as e:
            self.logger.error(f"Failed to create meeting mirror: {e}")
            return None

    def organize_booking_events(self) -> Dict[str, int]:
        """Move booking events from Work to Appointments."""
        stats = {
            'events_found': 0,
            'events_moved': 0,
            'already_on_appointments': 0,
            'errors': 0
        }

        self.logger.info("🔄 Organizing booking events...")

        # Get booking events from database
        booking_events = self.get_booking_events()
        stats['events_found'] = len(booking_events)

        self.logger.info(f"  Found {len(booking_events)} booking events to process")

        for event in booking_events:
            try:
                event_id = event['event_id']

                # Check if already on Appointments
                if self.check_event_on_calendar(event_id, self.appointments):
                    stats['already_on_appointments'] += 1
                    continue

                # Move event
                if self.move_event(event_id, self.work_calendar, self.appointments):
                    # Update database
                    with self.db.get_session() as session:
                        session.execute(
                            text("""
                                UPDATE calendar_events
                                SET current_calendar = :appointments,
                                    last_action = 'moved_to_appointments',
                                    last_action_at = NOW(),
                                    updated_at = NOW()
                                WHERE event_id = :event_id
                                AND current_calendar = :work_calendar
                            """),
                            {
                                "appointments": self.appointments,
                                "event_id": event_id,
                                "work_calendar": self.work_calendar
                            }
                        )
                    stats['events_moved'] += 1
                else:
                    stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing booking event: {e}")
                stats['errors'] += 1

        return stats

    def organize_meeting_invitations(self) -> Dict[str, int]:
        """Mirror meeting invitations to Meetings calendar."""
        stats = {
            'events_found': 0,
            'mirrors_created': 0,
            'already_mirrored': 0,
            'errors': 0
        }

        self.logger.info("🔄 Organizing meeting invitations...")

        # Get meeting invitations from database
        meetings = self.get_meeting_invitations()
        stats['events_found'] = len(meetings)

        self.logger.info(f"  Found {len(meetings)} meeting invitations to process")

        for event in meetings:
            try:
                event_id = event['event_id']

                # Check if already mirrored
                if self.check_mirror_exists(event_id, self.meetings):
                    stats['already_mirrored'] += 1
                    continue

                # Create mirror
                mirror_id = self.create_meeting_mirror(event)

                if mirror_id:
                    # Record mirror in database
                    mirror_data = {
                        'event_id': mirror_id,
                        'ical_uid': event.get('ical_uid'),
                        'summary': event.get('summary', 'Untitled'),
                        'description': event.get('description', ''),
                        'location': event.get('location', ''),
                        'start_time': event['start_time'],
                        'end_time': event['end_time'],
                        'source_calendar': self.work_calendar,
                        'current_calendar': self.meetings,
                        'event_type': 'meeting_mirror',
                        'is_attendee_event': True,
                        'organizer_email': event.get('organizer_email'),
                        'status': 'active',
                        'metadata': {
                            'mirror_source': self.work_calendar,
                            'source_event_id': event_id,
                            'is_mirror': True,
                            'original_summary': event.get('summary', '')
                        }
                    }
                    self.db.record_event(mirror_data)
                    stats['mirrors_created'] += 1
                else:
                    stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing meeting invitation: {e}")
                stats['errors'] += 1

        return stats

    def run_organization(self) -> Dict[str, Any]:
        """Run complete work event organization."""
        self.logger.info("🚀 Starting work event organization...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'booking_events': {},
            'meeting_invitations': {}
        }

        # Organize booking events
        booking_stats = self.organize_booking_events()
        results['booking_events'] = booking_stats

        # Organize meeting invitations
        meeting_stats = self.organize_meeting_invitations()
        results['meeting_invitations'] = meeting_stats

        # Summary
        self.logger.info("=" * 60)
        self.logger.info("📊 WORK EVENT ORGANIZATION SUMMARY")

        self.logger.info(f"\nBooking Events → Appointments:")
        self.logger.info(f"  Found: {booking_stats['events_found']}")
        self.logger.info(f"  Moved: {booking_stats['events_moved']}")
        self.logger.info(f"  Already on Appointments: {booking_stats['already_on_appointments']}")
        self.logger.info(f"  Errors: {booking_stats['errors']}")

        self.logger.info(f"\nMeeting Invitations → Meetings:")
        self.logger.info(f"  Found: {meeting_stats['events_found']}")
        self.logger.info(f"  Mirrors created: {meeting_stats['mirrors_created']}")
        self.logger.info(f"  Already mirrored: {meeting_stats['already_mirrored']}")
        self.logger.info(f"  Errors: {meeting_stats['errors']}")

        self.logger.info("=" * 60)

        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Organize work calendar events')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("📋 WORK EVENT ORGANIZER")
    print("=" * 50)
    print("Organizing booking events and meeting invitations")
    print()

    organizer = WorkEventOrganizer()
    results = organizer.run_organization()

    print("\n✅ Organization complete!")


if __name__ == '__main__':
    main()
