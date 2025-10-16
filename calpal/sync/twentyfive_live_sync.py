#!/usr/bin/env python3
"""
Simplified 25Live Sync Service - Direct to Work Calendar

Syncs events from 25Live directly to tross@georgefox.edu with color coding:
- Classes: Yellow (color 5)
- GFU Events: Blue (color 9)

SIMPLIFIED ARCHITECTURE:
- Writes directly to tross@georgefox.edu (no subcalendars)
- Uses color coding for visual differentiation
- Database tracks all events for ICS generation and history
- No mirroring, no reconciliation, no orphans

FIXES:
- Checks BOTH 25live_reservation_id AND 25live_event_id for deletions
- Prevents events from being recreated after manual deletion

Date Range: August 1, 2024 to 12 months forward from today
"""

import json
import logging
import os
import requests
import base64
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from calpal.core.db_manager import DatabaseManager


class DBAware25LiveSync:
    """Database-aware 25Live to Google Calendar sync service."""

    def __init__(self):
        self.logger = logging.getLogger('db-25live-sync')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Initialize 25Live client
        self.session = requests.Session()
        self.authenticated = False

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Load credentials and config
        self.work_calendar = WORK_CALENDAR_ID
        self.load_credentials()
        self.load_query_config()
        self.load_calendar_config()
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

    def load_credentials(self):
        """Load 25Live credentials."""
        try:
            with open(TWENTYFIVE_LIVE_CREDENTIALS_FILE, 'r') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                if len(lines) >= 2:
                    self.username = lines[0]
                    self.password = lines[1]
                    self.logger.info("✅ Loaded 25Live credentials")
                else:
                    raise ValueError("Invalid credentials format")
        except Exception as e:
            self.logger.error(f"❌ Failed to load credentials: {e}")
            raise

    def load_query_config(self):
        """Load query configuration from 25live_queries.json."""
        try:
            queries_file = os.path.join(PRIVATE_DIR, '25live_queries.json')
            with open(queries_file, 'r') as f:
                self.query_config = json.load(f)
                self.logger.info("✅ Loaded 25Live query configuration")
        except Exception as e:
            self.logger.error(f"❌ Failed to load query config: {e}")
            raise

    def load_calendar_config(self):
        """Configure calendar and color settings."""
        # All events go to work calendar with color coding
        self.target_calendar = self.work_calendar

        # Color mappings for event types
        self.color_map = {
            'Classes': '5',  # Banana (Yellow)
            'GFU Events': '9'  # Blueberry (Blue)
        }

        self.logger.info("✅ Calendar configuration loaded")
        self.logger.info(f"  Target calendar: {self.target_calendar}")
        self.logger.info(f"  Classes color: {self.color_map['Classes']} (Yellow)")
        self.logger.info(f"  GFU Events color: {self.color_map['GFU Events']} (Blue)")

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

        # Check pattern matches
        for pattern in self.blacklist_patterns:
            if pattern.search(summary):
                return True

        return False

    def check_deleted_event(self, reservation_id: str, event_id: str, calendar_id: str) -> bool:
        """Check if an event with this reservation_id OR event_id was previously deleted.

        CRITICAL FIX: Some events have event_id but null reservation_id.
        Must check BOTH to prevent infinite re-creation.
        """
        try:
            from sqlalchemy import text
            with self.db.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT COUNT(*) as count
                        FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND deleted_at IS NOT NULL
                        AND (
                            metadata->>'25live_reservation_id' = :reservation_id
                            OR metadata->>'25live_event_id' = :event_id
                        )
                    """),
                    {
                        "reservation_id": reservation_id,
                        "event_id": event_id,
                        "calendar_id": calendar_id
                    }
                ).fetchone()

                return result[0] > 0 if result else False
        except Exception as e:
            self.logger.error(f"Error checking deleted event: {e}")
            return False

    def authenticate_25live(self):
        """Authenticate with 25Live."""
        self.logger.info("🔐 Authenticating with 25Live...")

        challenge_url = f"{TWENTYFIVE_LIVE_BASE_URL}/25live/data/{TWENTYFIVE_LIVE_INSTITUTION}/run/login.json?caller=pro"

        credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        }

        try:
            response = self.session.get(challenge_url, headers=headers, timeout=30)

            if response.status_code == 200:
                self.authenticated = True
                self.logger.info("✅ 25Live authentication successful")
                return True
            else:
                self.logger.error(f"❌ 25Live authentication failed: {response.status_code}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"❌ 25Live authentication error: {e}")
            return False

    def generate_date_ranges(self) -> List[tuple]:
        """Generate date ranges from August 1, 2024 to 12 months forward.

        Respects 25Live's 20-week limit by chunking into smaller ranges.
        """
        start_date = datetime(2024, 8, 1)
        end_date = datetime.now() + timedelta(days=365)  # 12 months forward

        ranges = []
        current = start_date
        max_range_days = 130  # 18.5 weeks = 130 days (safe under 20-week limit)

        while current < end_date:
            range_end = min(current + timedelta(days=max_range_days), end_date)
            ranges.append((
                current.strftime('%Y-%m-%d'),
                range_end.strftime('%Y-%m-%d')
            ))
            current = range_end + timedelta(days=1)

        total_days = (end_date - start_date).days
        self.logger.info(f"📅 Generated {len(ranges)} date ranges covering {total_days} days")
        self.logger.info(f"   From: {start_date.strftime('%Y-%m-%d')}")
        self.logger.info(f"   To: {end_date.strftime('%Y-%m-%d')}")
        return ranges

    def fetch_reservations(self, url_fragment: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch reservations from 25Live for a specific URL fragment and date range."""
        if not self.authenticated:
            raise Exception("Must authenticate with 25Live first")

        calendar_url = f"{TWENTYFIVE_LIVE_BASE_URL}/25live/data/{TWENTYFIVE_LIVE_INSTITUTION}/run/home/calendar/calendardata.json"

        # Parse URL fragment parameters
        url_params = self.parse_url_fragment(url_fragment)

        # Base parameters
        params = {
            'mode': 'pro',
            'start_dt': start_date,
            'end_dt': end_date,
            'comptype': 'calendar',
            'sort': 'evdates_event_name',
            'compsubject': 'event',
            'state': '0 1 3 4 99',
            'caller': 'pro-CalendarService.getData'
        }

        # Add URL-specific parameters
        params.update(url_params)

        try:
            response = self.session.get(calendar_url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                reservations = data.get('reservations', {}).get('reservation', [])
                self.logger.debug(f"Retrieved {len(reservations)} reservations for {start_date} to {end_date}")
                return reservations
            else:
                self.logger.warning(f"Failed to fetch reservations: HTTP {response.status_code}")
                return []

        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return []

    def parse_url_fragment(self, url_fragment: str) -> Dict[str, str]:
        """Parse URL fragment to extract query parameters."""
        if '&' in url_fragment:
            param_string = url_fragment.split('&', 1)[1]
        else:
            param_string = ""

        params = {}
        if param_string:
            for param_pair in param_string.split('&'):
                if '=' in param_pair:
                    key, value = param_pair.split('=', 1)
                    params[key] = value

        return params

    def _safe_extract_text(self, text_data: Any) -> str:
        """Safely extract text from potentially malformed data."""
        if not text_data:
            return ''

        try:
            if isinstance(text_data, str):
                return text_data.strip()

            if isinstance(text_data, dict):
                if text_data.get('nil'):
                    return ''
                value = text_data.get('value', '') or text_data.get('text', '') or str(text_data)
                return self._safe_extract_text(value)

            return str(text_data) if text_data else ''

        except Exception as e:
            self.logger.error(f"Error extracting text: {e}")
            return str(text_data)[:100] if text_data else ''

    def _parse_space_reservation(self, space_res: Any) -> str:
        """Parse space reservation data to extract location."""
        if not space_res:
            return ''

        try:
            if isinstance(space_res, str):
                return space_res

            if isinstance(space_res, list) and space_res:
                room_names = []
                for room in space_res:
                    room_name = self._extract_room_name(room)
                    if room_name:
                        room_names.append(room_name)

                if room_names:
                    if len(room_names) > 3:
                        return f"{room_names[0]} (+ {len(room_names)-1} other locations)"
                    else:
                        return ', '.join(room_names)
                return ''

            if isinstance(space_res, dict):
                return self._extract_room_name(space_res)

            return str(space_res)[:50] if space_res else ''

        except Exception as e:
            self.logger.error(f"Error parsing space reservation: {e}")
            return ''

    def _extract_room_name(self, room_data: Any) -> str:
        """Extract clean room name from room data."""
        if not room_data:
            return ''

        try:
            if isinstance(room_data, dict):
                if room_data.get('nil'):
                    return ''

                building_raw = room_data.get('building_name', '')
                space_name = room_data.get('space_name', '') or room_data.get('formal_name', '')

                building = ''
                if building_raw and not (isinstance(building_raw, dict) and building_raw.get('nil')):
                    building = str(building_raw)

                if space_name and building:
                    if building.split()[0] not in space_name:
                        return f"{building} {space_name}"
                    else:
                        return space_name
                elif space_name:
                    return space_name
                elif building:
                    return building
                return ''

            if isinstance(room_data, str):
                return room_data

            return str(room_data) if room_data else ''

        except Exception as e:
            self.logger.error(f"Error extracting room name: {e}")
            return ''

    def _extract_25live_reservation_id(self, reservation: Dict) -> Optional[str]:
        """Extract 25Live Reservation ID (profile_name) from reservation."""
        profile_name = reservation.get('profile_name')
        if profile_name and (profile_name.startswith('Rsrv_') or any(c.isdigit() for c in str(profile_name))):
            # For recurring classes, include the event start date to make ID unique per instance
            start_dt = reservation.get('event_start_dt', '')
            if start_dt:
                # Extract just the date part (YYYY-MM-DD) from the ISO datetime
                event_date = start_dt.split('T')[0] if 'T' in start_dt else start_dt[:10]
                return f"{profile_name}_{event_date}"
            return str(profile_name)
        return None

    def reservation_to_event_data(self, reservation: Any, calendar_type: str) -> Optional[Dict]:
        """Convert 25Live reservation to event data for database and Google Calendar."""
        # Handle case where reservation might be a string or invalid
        if not isinstance(reservation, dict):
            self.logger.warning(f"Invalid reservation type: {type(reservation)}")
            return None

        # Extract basic info
        event_name = self._safe_extract_text(reservation.get('event_name', ''))
        event_title = self._safe_extract_text(reservation.get('event_title', ''))
        start_dt = reservation.get('event_start_dt', '')
        end_dt = reservation.get('event_end_dt', '')

        # Extract location
        space_res = reservation.get('space_reservation', {})
        location = self._parse_space_reservation(space_res)

        # Create title based on calendar type
        if calendar_type == 'Classes':
            title = event_title if event_title else event_name
        else:
            title = event_name if event_name else event_title

        # Extract 25Live reservation ID for tracking
        reservation_id = self._extract_25live_reservation_id(reservation)

        # Build description
        description_parts = [f"Source: 25Live {calendar_type}"]
        if reservation_id:
            description_parts.append(f"Profile: {reservation_id}")
        if reservation.get('organization_name') and reservation['organization_name'] != '(Private)':
            description_parts.append(f"Organization: {reservation['organization_name']}")
        if reservation.get('event_locator'):
            description_parts.append(f"Event ID: {reservation['event_locator']}")

        description = '\n'.join(description_parts)

        # Determine event type
        if calendar_type == 'Classes':
            event_type = '25live_class'
        else:
            event_type = '25live_event'

        # Parse start/end times to datetime
        try:
            start_time = datetime.fromisoformat(start_dt.replace('Z', '+00:00')) if start_dt else None
            end_time = datetime.fromisoformat(end_dt.replace('Z', '+00:00')) if end_dt else None
        except:
            start_time = None
            end_time = None

        return {
            'summary': title,
            'description': description,
            'location': location,
            'start_time': start_time,
            'end_time': end_time,
            'source_calendar': self.target_calendar,  # All events go to work calendar
            'current_calendar': self.target_calendar,
            'event_type': event_type,
            'status': 'active',
            'is_attendee_event': False,
            'organizer_email': None,
            'creator_email': None,
            'last_action': 'created',
            'metadata': {
                '25live_reservation_id': reservation_id,
                '25live_event_id': str(reservation.get('event_id', '')),
                'calendar_type': calendar_type,
                'color_id': self.color_map.get(calendar_type, '1')  # Store color in metadata
            }
        }

    def check_google_calendar_for_event(self, calendar_id: str, start_time: datetime,
                                        end_time: datetime, summary: str) -> Optional[str]:
        """
        Check if event exists on Google Calendar.
        Returns event_id if found, None otherwise.
        """
        try:
            # Search for events at this time
            events_result = self.calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                q=summary,
                singleEvents=True
            ).execute()

            events = events_result.get('items', [])

            # Look for exact match
            for event in events:
                if event.get('summary') == summary:
                    event_start = event.get('start', {})
                    event_start_time = event_start.get('dateTime') or event_start.get('date')

                    if event_start_time:
                        # Parse the event start time
                        if 'T' in event_start_time:
                            event_dt = datetime.fromisoformat(event_start_time.replace('Z', '+00:00'))
                        else:
                            event_dt = datetime.fromisoformat(event_start_time)

                        # Compare times (allowing small differences)
                        if abs((event_dt.replace(tzinfo=None) - start_time.replace(tzinfo=None)).total_seconds()) < 60:
                            return event.get('id')

            return None
        except Exception as e:
            self.logger.error(f"Error checking Google Calendar: {e}")
            return None

    def create_google_calendar_event(self, event_data: Dict) -> Optional[str]:
        """Create event in Google Calendar with color and return the event_id."""
        # Get color from metadata
        color_id = event_data.get('metadata', {}).get('color_id', '1')

        calendar_event = {
            'summary': event_data['summary'],
            'description': event_data['description'],
            'location': event_data['location'],
            'start': {
                'dateTime': event_data['start_time'].isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': event_data['end_time'].isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'colorId': color_id,  # Add color
            'extendedProperties': {
                'private': {
                    'source': '25live',
                    'event_type': event_data['event_type'],
                    'calendar_type': event_data['metadata']['calendar_type'],
                    'sync_time': datetime.now().isoformat()
                }
            }
        }

        try:
            created_event = self.calendar_service.events().insert(
                calendarId=event_data['current_calendar'],
                body=calendar_event
            ).execute()

            event_id = created_event['id']
            ical_uid = created_event.get('iCalUID')

            self.logger.debug(f"Created event with color {color_id}: {event_data['summary']}")

            # Add small delay to avoid rate limiting
            time.sleep(0.1)

            return event_id, ical_uid

        except HttpError as e:
            if 'rateLimitExceeded' in str(e):
                self.logger.warning(f"Rate limit hit, waiting 2 seconds...")
                time.sleep(2)
                return None, None
            self.logger.error(f"Failed to create Google Calendar event: {e}")
            return None, None

    def sync_calendar_type(self, calendar_type: str) -> Dict[str, Any]:
        """Sync all events for a specific calendar type with database tracking."""
        self.logger.info(f"🔄 Syncing {calendar_type} events to {self.target_calendar}...")
        self.logger.info(f"   Using color: {self.color_map.get(calendar_type, '1')}")

        # Get configuration
        type_config = self.query_config.get(calendar_type, {})
        urls = type_config.get('URLs', [])

        if not urls:
            return {'success': False, 'error': f'No URLs configured for {calendar_type}'}

        # Get date ranges
        date_ranges = self.generate_date_ranges()

        stats = {
            'total_reservations': 0,
            'events_created': 0,
            'duplicates_skipped': 0,
            'errors': 0
        }

        # Process each URL and date range
        for url in urls:
            url_params = self.parse_url_fragment(url)
            self.logger.info(f"  Processing URL with params: {url_params}")

            for start_date, end_date in date_ranges:
                reservations = self.fetch_reservations(url, start_date, end_date)
                stats['total_reservations'] += len(reservations)

                for reservation in reservations:
                    try:
                        # Convert to event data (now goes to work calendar)
                        event_data = self.reservation_to_event_data(reservation, calendar_type)

                        if not event_data:
                            stats['errors'] += 1
                            continue

                        if not event_data.get('start_time') or not event_data.get('end_time'):
                            self.logger.warning(f"Skipping event with invalid times: {event_data.get('summary', 'Unknown')}")
                            stats['errors'] += 1
                            continue

                        # Check if event is blacklisted
                        if self.is_event_blacklisted(event_data.get('summary', '')):
                            self.logger.debug(f"Skipping blacklisted event: {event_data.get('summary')}")
                            stats['duplicates_skipped'] += 1
                            continue

                        # Check if event already exists in database (by 25Live reservation ID)
                        reservation_id = event_data['metadata'].get('25live_reservation_id')
                        event_id = event_data['metadata'].get('25live_event_id')

                        if reservation_id or event_id:
                            # Check database for existing ACTIVE event with this 25Live ID
                            if reservation_id:
                                existing = self.db.get_event_by_25live_id(reservation_id, self.target_calendar)
                                if existing:
                                    stats['duplicates_skipped'] += 1
                                    continue

                            # Check for DELETED events - don't recreate them!
                            deleted_event = self.check_deleted_event(reservation_id, event_id, self.target_calendar)
                            if deleted_event:
                                self.logger.debug(f"Skipping previously deleted event: {event_data.get('summary')}")
                                stats['duplicates_skipped'] += 1
                                continue
                        else:
                            # Fallback: Check by summary + start_time + calendar
                            existing = self.db.get_event_by_time_and_summary(
                                summary=event_data['summary'],
                                start_time=event_data['start_time'],
                                calendar_id=self.target_calendar
                            )
                            if existing:
                                stats['duplicates_skipped'] += 1
                                self.logger.debug(f"Skipping duplicate (by time/summary): {event_data['summary']}")
                                continue

                        # SIMPLIFIED: Create directly on Google Calendar with color
                        event_id, ical_uid = self.create_google_calendar_event(event_data)

                        if event_id:
                            # Record in database with Google Calendar ID
                            event_data['event_id'] = event_id
                            event_data['ical_uid'] = ical_uid
                            event_data['last_action'] = 'created'

                            if self.db.record_event(event_data):
                                stats['events_created'] += 1
                            else:
                                stats['errors'] += 1
                        else:
                            stats['errors'] += 1

                    except Exception as e:
                        self.logger.error(f"Error processing reservation: {e}")
                        stats['errors'] += 1

        self.logger.info(f"✅ {calendar_type} sync complete:")
        self.logger.info(f"  Total reservations: {stats['total_reservations']}")
        self.logger.info(f"  Events created: {stats['events_created']}")
        self.logger.info(f"  Duplicates skipped: {stats['duplicates_skipped']}")
        self.logger.info(f"  Errors: {stats['errors']}")

        return {
            'success': True,
            'calendar_type': calendar_type,
            'stats': stats
        }

    def run_full_sync(self) -> Dict[str, Any]:
        """Run complete synchronization of all calendar types."""
        self.logger.info("🚀 Starting database-aware 25Live synchronization...")
        self.logger.info("📅 Date range: August 1, 2024 to 12 months forward")

        # Authenticate with 25Live
        if not self.authenticate_25live():
            return {'success': False, 'error': 'Failed to authenticate with 25Live'}

        results = {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'date_range': {
                'start': '2024-08-01',
                'end': (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
            },
            'sync_results': {}
        }

        # Sync each calendar type
        for calendar_type in ['Classes', 'GFU Events']:
            try:
                result = self.sync_calendar_type(calendar_type)
                results['sync_results'][calendar_type] = result
            except Exception as e:
                self.logger.error(f"Failed to sync {calendar_type}: {e}")
                results['sync_results'][calendar_type] = {
                    'success': False,
                    'error': str(e)
                }

        # Check overall success
        all_successful = all(
            result.get('success', False)
            for result in results['sync_results'].values()
        )
        results['success'] = all_successful

        # Calculate totals
        total_created = sum(
            result.get('stats', {}).get('events_created', 0)
            for result in results['sync_results'].values()
        )
        total_duplicates = sum(
            result.get('stats', {}).get('duplicates_skipped', 0)
            for result in results['sync_results'].values()
        )

        results['total_events_created'] = total_created
        results['total_duplicates_skipped'] = total_duplicates

        # Save results
        results_file = os.path.join(PROJECT_ROOT, 'db_25live_sync_results.json')
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        self.logger.info(f"🎉 Full sync complete! Created {total_created} events, skipped {total_duplicates} duplicates")
        return results


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Database-Aware 25Live to Google Calendar Sync')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🔄 DATABASE-AWARE 25LIVE SYNC")
    print("=" * 50)
    print("Date range: August 1, 2024 to 12 months forward")
    print()

    sync_service = DBAware25LiveSync()
    results = sync_service.run_full_sync()

    if results['success']:
        print("✅ Synchronization completed successfully!")
    else:
        print("⚠️ Synchronization completed with some issues")

    print(f"\n📊 RESULTS:")
    print(f"  Date range: {results['date_range']['start']} to {results['date_range']['end']}")
    print(f"  Total events created: {results.get('total_events_created', 0)}")
    print(f"  Total duplicates skipped: {results.get('total_duplicates_skipped', 0)}")

    for calendar_type, result in results.get('sync_results', {}).items():
        status = "✅" if result.get('success') else "❌"
        print(f"  {status} {calendar_type}: {result.get('stats', {}).get('events_created', 0)} events")

    print(f"\n📄 Detailed results saved to: db_25live_sync_results.json")


if __name__ == '__main__':
    main()
