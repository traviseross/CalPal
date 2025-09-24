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

        # Source calendar from config
        self.source_calendar = WORK_CALENDAR_ID

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


    def fetch_work_calendar_events(self, days_back: int = 7, days_forward: int = 365):
        """Fetch events from Travis's work calendar."""
        try:
            self.logger.info(f"Determining actual event range from {self.source_calendar}...")

            # Step 1: Find the actual range of events in the calendar
            # Start with a very large future date to find the latest event
            far_future = (datetime.now() + timedelta(days=365*5)).isoformat() + 'Z'

            # Get a small sample to find the latest event
            latest_events = self.calendar_service.events().list(
                calendarId=self.source_calendar,
                timeMin=(datetime.now() - timedelta(days=days_back)).isoformat() + 'Z',
                timeMax=far_future,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events_sample = latest_events.get('items', [])

            if not events_sample:
                self.logger.warning("No events found in calendar")
                return []

            # Find the actual time range from the events
            time_min = (datetime.now() - timedelta(days=days_back)).isoformat() + 'Z'

            # Find the latest event date
            latest_event_time = None
            for event in events_sample:
                event_time_data = event.get('end') or event.get('start')
                if event_time_data:
                    if 'dateTime' in event_time_data:
                        event_time = datetime.fromisoformat(event_time_data['dateTime'].replace('Z', '+00:00'))
                    else:
                        # Convert date-only events to timezone-aware datetime at start of day
                        event_date = datetime.strptime(event_time_data['date'], '%Y-%m-%d')
                        event_time = event_date.replace(tzinfo=pytz.UTC)

                    if latest_event_time is None or event_time > latest_event_time:
                        latest_event_time = event_time

            if latest_event_time:
                # Use the actual latest event time, but ensure we go at least as far as the original days_forward
                min_future_date = datetime.now(pytz.UTC) + timedelta(days=days_forward)
                time_max = max(latest_event_time, min_future_date).astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                self.logger.info(f"Found events extending to {latest_event_time.strftime('%Y-%m-%d')}")
            else:
                time_max = (datetime.now() + timedelta(days=days_forward)).isoformat() + 'Z'
                self.logger.info(f"Using default time range (no events found to determine range)")

            self.logger.info(f"Fetching all events from {time_min} to {time_max}")

            # Step 2: Fetch all events in the determined range
            all_events = []
            page_token = None

            while True:
                events_result = self.calendar_service.events().list(
                    calendarId=self.source_calendar,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=2500,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()

                batch_events = events_result.get('items', [])
                all_events.extend(batch_events)

                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break

                self.logger.info(f"Retrieved {len(batch_events)} events, continuing...")

            self.logger.info(f"Retrieved {len(all_events)} total events from work calendar")
            return all_events

        except Exception as e:
            self.logger.error(f"Failed to fetch events: {e}")
            return []

    def process_event_for_wife(self, event: Dict) -> Optional[Dict]:
        """Process a work calendar event according to wife calendar rules."""
        summary = event.get('summary', '')
        description = event.get('description', '')
        location = event.get('location', '')

        # Rule 0: Skip mirrored events from Ross Family or travis.e.ross@gmail.com
        # Check for indications that this event was mirrored from these specific sources
        if self._is_mirrored_from_excluded_source(event):
            return None  # Skip these mirrored events

        # Rule 1: Class events
        if 'Class (mirrored from Classes calendar)' in description:
            return {
                'summary': 'In class',
                'description': '',  # No details
                'location': '',     # No location
                'start': event.get('start'),
                'end': event.get('end'),
                'original_event': event
            }

        # Rule 2: GFU Events (University events)
        if 'GFU Event (mirrored)' in description:
            return {
                'summary': 'Fox Event',
                'description': '',  # No details
                'location': location,  # Keep original location
                'start': event.get('start'),
                'end': event.get('end'),
                'original_event': event
            }

        # Rule 3: Skip personal busy time and unavailable blocks
        if ('Personal calendar busy time (safe to delete)' in summary or
            'Travis is unavailable' in summary):
            return None  # Skip entirely

        # Rule 4: Everything else becomes "In a meeting"
        return {
            'summary': 'In a meeting',
            'description': '',  # No details
            'location': location,  # Keep original location
            'start': event.get('start'),
            'end': event.get('end'),
            'original_event': event
        }

    def _is_mirrored_from_excluded_source(self, event: Dict) -> bool:
        """Check if event is mirrored from Ross Family or travis.e.ross@gmail.com calendars."""
        summary = event.get('summary', '').lower()
        description = event.get('description', '').lower()

        # Check for creator information - events mirrored from personal calendars
        # often retain the original creator's email
        creator = event.get('creator', {})
        creator_email = creator.get('email', '').lower()

        # Check organizer as well
        organizer = event.get('organizer', {})
        organizer_email = organizer.get('email', '').lower()

        # Patterns to identify excluded mirrored events:
        excluded_patterns = [
            # Direct email matches
            'travis.e.ross@gmail.com',
            # Ross Family calendar patterns (common naming patterns)
            'ross family',
            'rossfamily',
            'family calendar',
            # Busy indicators that are typically from personal calendars
            'busy',
        ]

        # Check if this is a "Busy" event that's likely mirrored from personal calendar
        # We want to exclude "Busy" events that come from personal calendars, but keep
        # legitimate work "Busy" events
        if summary.strip() == 'busy':
            # If it's just "Busy" with no other details and from personal sources, skip it
            if (creator_email in ['travis.e.ross@gmail.com'] or
                organizer_email in ['travis.e.ross@gmail.com'] or
                any(pattern in description for pattern in ['ross family', 'personal'])):
                return True

        # Check for any of the excluded patterns in various fields
        for pattern in excluded_patterns:
            if (pattern in summary or
                pattern in description or
                pattern in creator_email or
                pattern in organizer_email):
                # Additional check: if it's "busy" pattern, make sure it's from personal source
                if pattern == 'busy':
                    # Only exclude if it's clearly from a personal source
                    if (creator_email in ['travis.e.ross@gmail.com'] or
                        'ross family' in description or
                        'personal' in description):
                        return True
                else:
                    return True

        return False

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
                'source_calendar': self.source_calendar,
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

        # Fetch events from work calendar
        work_events = self.fetch_work_calendar_events(days_back, days_forward)

        if not work_events:
            self.logger.warning("No events found in work calendar")
            return

        # Process events according to rules
        processed_events, filtered_stats = self._process_events_with_stats(work_events)

        self.logger.info(f"Processed {len(processed_events)} events, skipped {filtered_stats['total_skipped']} total")
        self.logger.info(f"  - Filtered {filtered_stats['mirrored_count']} mirrored events from personal calendars")
        self.logger.info(f"  - Filtered {filtered_stats['personal_busy_count']} personal busy time blocks")

        # Generate ICS content
        ics_content = self.generate_ics_file(processed_events)

        # Save to file
        metadata = self.save_ics_file(ics_content)

        # Summary
        print(f"\n📅 WIFE CALENDAR ICS GENERATION COMPLETE")
        print(f"=" * 50)
        print(f"Source calendar: {self.source_calendar}")
        print(f"Events processed: {len(work_events)}")
        print(f"Events included: {len(processed_events)}")
        print(f"Events skipped: {filtered_stats['total_skipped']}")
        print(f"  - Mirrored events filtered: {filtered_stats['mirrored_count']}")
        print(f"  - Personal busy time filtered: {filtered_stats['personal_busy_count']}")
        print(f"ICS file: {self.ics_output_path}")
        print(f"Public URL: {metadata['public_url']}")

        return metadata

    def _process_events_with_stats(self, work_events: List[Dict]) -> tuple:
        """Process events and return both results and filtering statistics."""
        processed_events = []
        filtered_mirrored_count = 0
        filtered_personal_busy_count = 0

        for event in work_events:
            # Check why the event is being skipped for better logging
            summary = event.get('summary', '')
            if self._is_mirrored_from_excluded_source(event):
                self.logger.debug(f"Filtered mirrored event: {summary}")
                filtered_mirrored_count += 1
                continue
            elif ('Personal calendar busy time (safe to delete)' in summary or
                  'Travis is unavailable' in summary):
                self.logger.debug(f"Filtered personal busy time: {summary}")
                filtered_personal_busy_count += 1
                continue

            processed = self.process_event_for_wife(event)
            if processed:
                processed_events.append(processed)

        stats = {
            'mirrored_count': filtered_mirrored_count,
            'personal_busy_count': filtered_personal_busy_count,
            'total_skipped': filtered_mirrored_count + filtered_personal_busy_count
        }

        return processed_events, stats

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