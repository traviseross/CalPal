#!/usr/bin/env python3
"""
Google Calendar Scanner Service

Scans Google Calendars and records all events into the database:
- Ross Family calendar
- travis.e.ross@gmail.com personal calendar
- All work subcalendars (Classes, GFU Events, Meetings, Appointments)
- tross@georgefox.edu work calendar

Date Range: August 1, 2024 to 12 months forward from today

This implements the "Sources → Database" pattern where all calendar
events are ingested into the database first, before any organization.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.db_manager import DatabaseManager


class CalendarScanner:
    """Scan Google Calendars and record events into database."""

    def __init__(self):
        self.logger = logging.getLogger('calendar-scanner')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Define calendars to scan
        self.calendars_to_scan = self._load_calendar_list()

        # Date range: August 1, 2024 to 12 months forward
        self.start_date = datetime(2024, 8, 1)
        self.end_date = datetime.now() + timedelta(days=365)

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
        """Load list of all calendars to scan."""
        calendars = {}

        # Personal calendars
        calendars['Personal'] = PERSONAL_CALENDAR_ID  # travis.e.ross@gmail.com
        calendars['Ross Family'] = '63cbe19d6ecd1869e68c4b46a96a705e6d0f9d3e31af6b2c251cb6ed81f26ad0@group.calendar.google.com'

        # Work calendar
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

        self.logger.info(f"📅 Will scan {len(calendars)} calendars:")
        for name, cal_id in calendars.items():
            self.logger.info(f"  - {name}: {cal_id[:20]}...")

        return calendars

    def fetch_calendar_events(self, calendar_id: str, calendar_name: str) -> List[Dict]:
        """Fetch all events from a specific calendar."""
        try:
            time_min = self.start_date.isoformat() + 'Z'
            time_max = self.end_date.isoformat() + 'Z'

            self.logger.info(f"🔍 Scanning {calendar_name}...")

            events = []
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
                events.extend(batch_events)

                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break

            self.logger.info(f"  Found {len(events)} events in {calendar_name}")
            return events

        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning(f"  Calendar not found: {calendar_name}")
            else:
                self.logger.error(f"  Failed to fetch events from {calendar_name}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"  Error scanning {calendar_name}: {e}")
            return []

    def _classify_event_type(self, event: Dict, calendar_name: str) -> str:
        """Classify what type of event this is."""
        # Check extended properties for 25Live events
        extended_props = event.get('extendedProperties', {}).get('private', {})
        source = extended_props.get('source', '')

        if source == '25live':
            calendar_type = extended_props.get('calendar_type', '')
            if calendar_type == 'Classes':
                return '25live_class'
            else:
                return '25live_event'
        elif source == 'classes_mirror':
            return 'classes_mirror'
        elif source == 'gfu_events_mirror':
            return 'gfu_events_mirror'

        # Check for booking events
        summary = event.get('summary', '')
        description = event.get('description', '')
        creator_email = event.get('creator', {}).get('email', '')

        if (summary.startswith('Meet with Travis Ross') and
            creator_email == 'tross@georgefox.edu' and
            'Booked by' in description):
            return 'booking'

        # Check if it's an attendee event (meeting invitation)
        attendees = event.get('attendees', [])
        organizer_email = event.get('organizer', {}).get('email', '')

        for attendee in attendees:
            if 'tross@georgefox.edu' in attendee.get('email', ''):
                if organizer_email != 'tross@georgefox.edu':
                    return 'meeting_invitation'
                break

        # Check calendar source
        if calendar_name == 'Ross Family':
            return 'family'
        elif calendar_name == 'Personal':
            return 'personal'
        elif calendar_name in ['Classes', 'GFU Events', 'Meetings', 'Appointments']:
            return 'manual'  # Manually created on subcalendar

        return 'other'

    def event_to_db_format(self, event: Dict, calendar_id: str, calendar_name: str) -> Optional[Dict]:
        """Convert Google Calendar event to database format."""
        try:
            event_id = event.get('id')
            if not event_id:
                return None

            # Extract times
            start = event.get('start', {})
            end = event.get('end', {})

            # Handle both datetime and date (all-day events)
            if 'dateTime' in start:
                start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
            elif 'date' in start:
                # All-day event
                start_time = datetime.strptime(start['date'], '%Y-%m-%d')
                end_time = datetime.strptime(end['date'], '%Y-%m-%d')
            else:
                return None

            # Classify event type
            event_type = self._classify_event_type(event, calendar_name)

            # Check if user is an attendee (not organizer)
            is_attendee_event = False
            attendees = event.get('attendees', [])
            organizer_email = event.get('organizer', {}).get('email', '')
            creator_email = event.get('creator', {}).get('email', '')

            for attendee in attendees:
                if 'tross@georgefox.edu' in attendee.get('email', ''):
                    if organizer_email != 'tross@georgefox.edu' and organizer_email != calendar_id:
                        is_attendee_event = True
                    break

            # Extract extended properties
            ext_props = event.get('extendedProperties', {})
            private = ext_props.get('private', {})

            # Build metadata preserving source_event_id at top level
            metadata = {
                'calendar_name': calendar_name,
                'original_start': start,
                'original_end': end,
            }

            # Preserve source_event_id at top level for unique constraint
            if 'source_event_id' in private:
                metadata['source_event_id'] = private['source_event_id']

            # Preserve 25live_reservation_id at top level
            if '25live_reservation_id' in private:
                metadata['25live_reservation_id'] = private['25live_reservation_id']

            # Store full extended properties for reference
            if ext_props:
                metadata['google_event_data'] = ext_props

            # Build database event
            db_event = {
                'event_id': event_id,
                'ical_uid': event.get('iCalUID'),
                'summary': event.get('summary', 'Untitled'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'start_time': start_time,
                'end_time': end_time,
                'source_calendar': calendar_id,
                'current_calendar': calendar_id,
                'event_type': event_type,
                'is_attendee_event': is_attendee_event,
                'organizer_email': organizer_email,
                'creator_email': creator_email,
                'status': 'active',
                'last_action': 'scanned',
                'metadata': metadata
            }

            return db_event

        except Exception as e:
            self.logger.error(f"Error converting event to DB format: {e}")
            return None

    def scan_calendar(self, calendar_name: str, calendar_id: str) -> Dict[str, int]:
        """Scan a single calendar and record all events in database."""
        stats = {
            'events_found': 0,
            'events_recorded': 0,
            'events_updated': 0,
            'events_skipped': 0,
            'errors': 0
        }

        # Fetch all events
        events = self.fetch_calendar_events(calendar_id, calendar_name)
        stats['events_found'] = len(events)

        if not events:
            return stats

        # Process each event
        for event in events:
            try:
                db_event = self.event_to_db_format(event, calendar_id, calendar_name)

                if not db_event:
                    stats['errors'] += 1
                    continue

                # Check if event already exists in database
                existing = self.db.get_event_by_id(db_event['event_id'], calendar_id)

                if existing:
                    # Event exists - update last_seen_at
                    stats['events_updated'] += 1
                else:
                    # New event - record it
                    if self.db.record_event(db_event):
                        stats['events_recorded'] += 1
                    else:
                        stats['errors'] += 1

            except Exception as e:
                self.logger.error(f"Error processing event {event.get('id', 'unknown')}: {e}")
                stats['errors'] += 1

        return stats

    def scan_all_calendars(self) -> Dict[str, Any]:
        """Scan all configured calendars and record events."""
        self.logger.info("🚀 Starting calendar scanner...")
        self.logger.info(f"📅 Date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'date_range': {
                'start': self.start_date.strftime('%Y-%m-%d'),
                'end': self.end_date.strftime('%Y-%m-%d')
            },
            'calendars': {},
            'totals': {
                'events_found': 0,
                'events_recorded': 0,
                'events_updated': 0,
                'errors': 0
            }
        }

        # Scan each calendar
        for calendar_name, calendar_id in self.calendars_to_scan.items():
            try:
                stats = self.scan_calendar(calendar_name, calendar_id)
                results['calendars'][calendar_name] = stats

                # Update totals
                results['totals']['events_found'] += stats['events_found']
                results['totals']['events_recorded'] += stats['events_recorded']
                results['totals']['events_updated'] += stats['events_updated']
                results['totals']['errors'] += stats['errors']

            except Exception as e:
                self.logger.error(f"Failed to scan {calendar_name}: {e}")
                results['calendars'][calendar_name] = {'error': str(e)}

        # Save results
        results_file = os.path.join(PROJECT_ROOT, 'calendar_scan_results.json')
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Log summary
        self.logger.info("=" * 60)
        self.logger.info("📊 CALENDAR SCAN SUMMARY")
        self.logger.info(f"Total events found: {results['totals']['events_found']}")
        self.logger.info(f"New events recorded: {results['totals']['events_recorded']}")
        self.logger.info(f"Existing events updated: {results['totals']['events_updated']}")
        self.logger.info(f"Errors: {results['totals']['errors']}")
        self.logger.info("=" * 60)

        for calendar_name, stats in results['calendars'].items():
            if 'error' in stats:
                self.logger.error(f"  ❌ {calendar_name}: {stats['error']}")
            else:
                self.logger.info(f"  ✅ {calendar_name}: {stats['events_found']} found, {stats['events_recorded']} new")

        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Scan Google Calendars into database')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("📅 GOOGLE CALENDAR SCANNER")
    print("=" * 50)
    print("Scanning all calendars into database")
    print("Date range: August 1, 2024 to 12 months forward")
    print()

    scanner = CalendarScanner()
    results = scanner.scan_all_calendars()

    print("\n✅ Calendar scan complete!")
    print(f"Results saved to: calendar_scan_results.json")


if __name__ == '__main__':
    main()
