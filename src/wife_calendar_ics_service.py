#!/usr/bin/env python3
"""
Calendar ICS Service

Creates an ICS file from work calendar with filtering and title rules.
Applies specific filtering and title rules without modifying source calendar.

Rules:
- "Class (mirrored from Classes calendar)" -> "In class"
- "Personal calendar busy time (safe to delete)" -> Skip entirely
- "Travis is unavailable" -> Skip entirely
- Everything else -> "Busy" with location, original title in description
"""

import json
import logging
import argparse
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import hashlib

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ICS generation
from icalendar import Calendar, Event as ICalEvent
import pytz

try:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import *
except ImportError:
    print("ERROR: config.py not found. Please copy config.example.py to config.py and customize it.")
    exit(1)

class WifeCalendarICSService:
    """Generate ICS file from work calendar."""

    def __init__(self):
        self.logger = logging.getLogger('calendar-ics')

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Source calendars from config
        self.work_calendar = WORK_CALENDAR_ID
        self.personal_calendar = PERSONAL_CALENDAR_ID

        # Output configuration
        self.ics_output_path = ICS_FILE_PATH

    def _initialize_calendar_service(self):
        """Initialize Google Calendar API service."""
        try:
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/calendar.readonly']
            )
            service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("✅ Google Calendar API service initialized")
            return service
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Calendar API: {e}")
            raise


    def fetch_calendar_events(self, days_back: int = 7, days_forward: int = 365):
        """Fetch events from both work and personal calendars."""
        try:
            self.logger.info(f"Fetching events from work calendar: {self.work_calendar}")
            self.logger.info(f"Fetching events from personal calendar: {self.personal_calendar}...")

            # Step 1: Calculate time range - always use exactly 12 months forward
            time_min = (datetime.now() - timedelta(days=days_back)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            self.logger.info(f"Fetching events from {time_min} to {time_max} (12 months forward)")

            # Step 2: Fetch events from both calendars

            all_events = []

            # Fetch from work calendar
            work_events = self._fetch_events_from_calendar(self.work_calendar, time_min, time_max, "work")
            all_events.extend(work_events)

            # Fetch from personal calendar
            personal_events = self._fetch_events_from_calendar(self.personal_calendar, time_min, time_max, "personal")
            all_events.extend(personal_events)

            # Remove duplicates by event ID
            seen_ids = set()
            unique_events = []
            for event in all_events:
                event_id = event.get('id')
                if event_id and event_id not in seen_ids:
                    seen_ids.add(event_id)
                    unique_events.append(event)
                elif not event_id:
                    # Keep events without IDs
                    unique_events.append(event)

            self.logger.info(f"Retrieved {len(unique_events)} total unique events from both calendars")
            return unique_events

        except Exception as e:
            self.logger.error(f"Failed to fetch events: {e}")
            return []

    def _fetch_events_from_calendar(self, calendar_id: str, time_min: str, time_max: str, calendar_type: str) -> List[Dict]:
        """Fetch events from a specific calendar."""
        try:
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

                self.logger.info(f"Retrieved {len(batch_events)} events from {calendar_type} calendar, continuing...")

            self.logger.info(f"Retrieved {len(events)} total events from {calendar_type} calendar ({calendar_id})")
            return events

        except Exception as e:
            self.logger.error(f"Failed to fetch events from {calendar_type} calendar ({calendar_id}): {e}")
            return []

    def process_event_for_wife(self, event: Dict) -> Optional[Dict]:
        """Process events to preserve full details without filtering."""
        # Keep all event details exactly as they are
        return {
            'summary': event.get('summary', ''),
            'description': event.get('description', ''),
            'location': event.get('location', ''),
            'start': event.get('start'),
            'end': event.get('end'),
            'original_event': event
        }


    def generate_ics_file(self, processed_events: List[Dict]) -> str:
        """Generate ICS file content from processed events."""
        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//Travis Ross//Wife Calendar//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', 'Travis Work Status')
        cal.add('x-wr-caldesc', 'Travis work calendar status for scheduling')

        # Add events
        for event_data in processed_events:
            event = ICalEvent()

            # Basic event properties
            event.add('summary', event_data['summary'])

            # Only add description if it has content
            if event_data['description']:
                event.add('description', event_data['description'])

            # Only add location if it has content
            if event_data['location']:
                event.add('location', event_data['location'])

            # Handle start/end times
            start_data = event_data['start']
            end_data = event_data['end']

            # Parse datetime
            if 'dateTime' in start_data:
                # Timed event
                start_dt = datetime.fromisoformat(start_data['dateTime'].replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_data['dateTime'].replace('Z', '+00:00'))
                event.add('dtstart', start_dt)
                event.add('dtend', end_dt)
            else:
                # All-day event
                start_date = datetime.strptime(start_data['date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(end_data['date'], '%Y-%m-%d').date()
                event.add('dtstart', start_date)
                event.add('dtend', end_date)

            # Generate unique ID
            original_event = event_data['original_event']
            event_id = original_event.get('id', '')
            event.add('uid', f"{event_id}@wife-calendar.traviseross.com")

            # Add timestamps
            now = datetime.now(pytz.UTC)
            event.add('dtstamp', now)

            created = original_event.get('created')
            if created:
                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                event.add('created', created_dt)

            updated = original_event.get('updated')
            if updated:
                updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                event.add('last-modified', updated_dt)

            # Add to calendar
            cal.add_component(event)

        return cal.to_ical().decode('utf-8')

    def save_ics_file(self, ics_content: str):
        """Save ICS content to file."""
        try:
            with open(self.ics_output_path, 'w', encoding='utf-8') as f:
                f.write(ics_content)

            self.logger.info(f"✅ ICS file saved to: {self.ics_output_path}")

            # Also save metadata about the generation
            metadata = {
                'generated_at': datetime.now().isoformat(),
                'public_url': 'https://calpal.traviseross.com/zj9ETjqLo2EFWwwUtMORWgnI94ji_4Obbsanw5ld8EM/travis_schedule.ics',
                'work_calendar': self.work_calendar,
                'personal_calendar': self.personal_calendar,
                'events_count': ics_content.count('BEGIN:VEVENT')
            }

            metadata_path = self.ics_output_path.replace('.ics', '_metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            return metadata

        except Exception as e:
            self.logger.error(f"Failed to save ICS file: {e}")
            raise

    def run_generation(self, days_back: int = 7, days_forward: int = 365):
        """Run the complete ICS generation process."""
        self.logger.info("🔄 Starting wife calendar ICS generation...")

        # Fetch events from both calendars
        all_events = self.fetch_calendar_events(days_back, days_forward)

        if not all_events:
            self.logger.warning("No events found in calendars")
            return

        # Process events to preserve full details
        processed_events = []
        for event in all_events:
            processed = self.process_event_for_wife(event)
            if processed:
                processed_events.append(processed)

        self.logger.info(f"Processed {len(processed_events)} events with full details preserved")

        # Generate ICS content
        ics_content = self.generate_ics_file(processed_events)

        # Save to file
        metadata = self.save_ics_file(ics_content)

        # Summary
        print(f"\n📅 CALENDAR ICS GENERATION COMPLETE")
        print(f"=" * 50)
        print(f"Work calendar: {self.work_calendar}")
        print(f"Personal calendar: {self.personal_calendar}")
        print(f"Total events found: {len(all_events)}")
        print(f"Events included: {len(processed_events)}")
        print(f"Date range: 12 months forward")
        print(f"ICS file: {self.ics_output_path}")
        print(f"Public URL: {metadata['public_url']}")

        return metadata


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Generate wife calendar ICS file')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Days to look back for events (default: 7)')
    parser.add_argument('--days-forward', type=int, default=365,
                       help='Days to look forward for events (default: 365)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Set logging level')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run the service
    service = WifeCalendarICSService()
    service.run_generation(args.days_back, args.days_forward)

if __name__ == '__main__':
    main()