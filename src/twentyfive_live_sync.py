#!/usr/bin/env python3
"""
25Live Calendar Sync Service

Syncs events from 25Live to Google Calendars:
- Classes: Travis's teaching schedule (role_id=-3) → Classes calendar
- GFU Events: University events (5 different queries) → GFU Events calendar

Features:
- Rigorous duplicate detection (never create identical time blocks)
- Backward and forward date coverage (respecting 20-week API limit)
- Proper mapping to cleaned calendar structure
- Event tracking for deletion learning
"""

import json
import logging
import os
import requests
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import hashlib

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class TwentyFiveLiveSync:
    """Complete 25Live to Google Calendar sync service."""

    def __init__(self):
        self.logger = logging.getLogger('25live-sync')

        # Initialize 25Live client
        self.session = requests.Session()
        self.authenticated = False

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Initialize work calendar and security settings FIRST
        self.work_calendar = 'tross@georgefox.edu'

        # SECURITY: Define allowed write calendars - NEVER write to personal calendars
        self.ALLOWED_WRITE_CALENDARS = {
            self.work_calendar,  # Main work calendar
            # Will be populated with work subcalendars after config load
        }

        # SECURITY: Define FORBIDDEN write calendars - NEVER write to these
        self.FORBIDDEN_WRITE_CALENDARS = {
            'travis.e.ross@gmail.com',
            '63cbe19d6ecd1869e68c4b46a96a705e6d0f9d3e31af6b2c251cb6ed81f26ad0@group.calendar.google.com'  # Ross Family
        }

        # Load calendars from config
        self.calendars = CALENDAR_MAPPINGS.copy()

        # Load configurations
        self.load_credentials()
        self.load_query_config()

        # Event tracking for duplicates and ML
        self.processed_events = set()  # Track processed events this run
        self.existing_events = {}      # Cache of existing calendar events

        # GFU Events specific tracking
        self.gfu_event_tracker = self._initialize_gfu_tracking()

        # Classes specific tracking
        self.classes_event_tracker = self._initialize_classes_tracking()

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
            with open('/home/tradmin/CalPal/25live_queries.json', 'r') as f:
                self.query_config = json.load(f)
                self.logger.info("✅ Loaded 25Live query configuration")
        except Exception as e:
            self.logger.error(f"❌ Failed to load query config: {e}")
            raise

    def load_calendar_config(self):
        """Load calendar configuration."""
        try:
            with open('/home/tradmin/CalPal/work_subcalendars.json', 'r') as f:
                self.calendars = json.load(f)

                # Add work subcalendars to allowed write list
                for calendar_id in self.calendars.values():
                    if calendar_id:
                        self.ALLOWED_WRITE_CALENDARS.add(calendar_id)

                # SECURITY: Verify no forbidden calendars in config
                for calendar_name, calendar_id in self.calendars.items():
                    if calendar_id in self.FORBIDDEN_WRITE_CALENDARS:
                        raise ValueError(f"SECURITY ERROR: Forbidden calendar {calendar_id} found in config for {calendar_name}")

                self.logger.info("✅ Loaded calendar configuration")
                self.logger.info(f"  Classes: {self.calendars['Classes']}")
                self.logger.info(f"  GFU Events: {self.calendars['GFU Events']}")
                self.logger.info(f"  Allowed write calendars: {len(self.ALLOWED_WRITE_CALENDARS)}")
        except Exception as e:
            self.logger.error(f"❌ Failed to load calendar config: {e}")
            raise

    def _initialize_gfu_tracking(self):
        """Initialize GFU Events tracking system."""
        return {
            'added_events': self._load_gfu_tracking_file('gfu_added_events.json'),
            'deleted_events': self._load_gfu_tracking_file('gfu_deleted_events.json'),
            'blocklist': self._load_gfu_tracking_file('gfu_blocklist.json')
        }

    def _initialize_classes_tracking(self):
        """Initialize Classes tracking system."""
        return {
            'mirrored_events': self._load_gfu_tracking_file('classes_mirrored_events.json')
        }

    def _load_gfu_tracking_file(self, filename: str) -> Dict:
        """Load a GFU tracking file or create empty if doesn't exist."""
        try:
            import sys
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from config import DATA_DIR
            filepath = os.path.join(DATA_DIR, filename)
        except (ImportError, AttributeError):
            filepath = f'/home/tradmin/CalPal/data/{filename}'
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.info(f"Creating new tracking file: {filename}")
            return {}
        except Exception as e:
            self.logger.error(f"Error loading {filename}: {e}")
            return {}

    def _save_gfu_tracking_file(self, filename: str, data: Dict):
        """Save GFU tracking data to file."""
        try:
            import sys
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from config import DATA_DIR
            filepath = os.path.join(DATA_DIR, filename)
        except (ImportError, AttributeError):
            filepath = f'/home/tradmin/CalPal/data/{filename}'
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving {filename}: {e}")

    def _extract_25live_reservation_id(self, event_data: Dict) -> Optional[str]:
        """Extract 25Live Reservation ID from event description or reservation data."""
        # First try from event description (for existing calendar events)
        description = event_data.get('description', '')
        if 'Profile: ' in description:
            for line in description.split('\n'):
                if line.startswith('Profile: '):
                    profile_value = line.replace('Profile: ', '').strip()
                    # Handle both GFU Events (Rsrv_XXXXX) and Classes (schedule patterns) formats
                    if profile_value and (profile_value.startswith('Rsrv_') or any(c.isdigit() for c in profile_value)):
                        return profile_value

        # Try from reservation data (during sync process)
        if 'profile_name' in event_data and event_data['profile_name']:
            profile_name = event_data['profile_name']
            if profile_name and (profile_name.startswith('Rsrv_') or any(c.isdigit() for c in profile_name)):
                return profile_name

        # Try from reservation object directly
        reservation = event_data.get('reservation', {})
        if reservation and reservation.get('profile_name'):
            profile_name = reservation['profile_name']
            if profile_name and (profile_name.startswith('Rsrv_') or any(c.isdigit() for c in profile_name)):
                return profile_name

        return None

    def _create_gfu_event_signature(self, event_data: Dict) -> str:
        """Create a unique signature for GFU event tracking using 25Live Reservation ID when available."""
        # Use 25Live Reservation ID as the primary identifier
        reservation_id = self._extract_25live_reservation_id(event_data)
        if reservation_id:
            return reservation_id

        # Fallback to content-based signature for events without reservation IDs
        summary = event_data.get('summary', '')
        start = event_data.get('start', {}).get('dateTime', event_data.get('start', {}).get('date', ''))
        end = event_data.get('end', {}).get('dateTime', event_data.get('end', {}).get('date', ''))
        location = event_data.get('location', '')

        signature_data = f"{summary}-{start}-{end}-{location}"
        return hashlib.md5(signature_data.encode()).hexdigest()

    def _is_gfu_event_blocked(self, event_data: Dict) -> bool:
        """Check if GFU event is in blocklist."""
        signature = self._create_gfu_event_signature(event_data)
        return signature in self.gfu_event_tracker['blocklist']

    def _add_to_gfu_blocklist(self, event_data: Dict, reason: str = 'user_deleted'):
        """Add event to GFU blocklist for ML training."""
        signature = self._create_gfu_event_signature(event_data)
        self.gfu_event_tracker['blocklist'][signature] = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason,
            'event_summary': event_data.get('summary', ''),
            'event_start': event_data.get('start', {}),
            'event_location': event_data.get('location', ''),
            'full_event_data': event_data  # For ML training
        }
        self._save_gfu_tracking_file('gfu_blocklist.json', self.gfu_event_tracker['blocklist'])

    def _create_classes_event_signature(self, event_data: Dict) -> str:
        """Create a unique signature for Classes event tracking using 25Live Reservation ID when available."""
        # Use 25Live Reservation ID as the primary identifier
        reservation_id = self._extract_25live_reservation_id(event_data)
        if reservation_id:
            return reservation_id

        # Fallback to content-based signature for events without reservation IDs
        summary = event_data.get('summary', '')
        start = event_data.get('start', {}).get('dateTime', event_data.get('start', {}).get('date', ''))
        end = event_data.get('end', {}).get('dateTime', event_data.get('end', {}).get('date', ''))
        location = event_data.get('location', '')

        signature_data = f"{summary}-{start}-{end}-{location}"
        return hashlib.md5(signature_data.encode()).hexdigest()

    def _validate_calendar_write(self, calendar_id: str, operation: str) -> bool:
        """SECURITY: Validate that we're allowed to write to this calendar."""
        if calendar_id in self.FORBIDDEN_WRITE_CALENDARS:
            self.logger.error(f"🚨 SECURITY VIOLATION: Attempted {operation} to FORBIDDEN calendar {calendar_id}")
            raise ValueError(f"SECURITY ERROR: Cannot write to forbidden calendar {calendar_id}")

        if calendar_id not in self.ALLOWED_WRITE_CALENDARS:
            self.logger.error(f"🚨 SECURITY VIOLATION: Attempted {operation} to UNAUTHORIZED calendar {calendar_id}")
            raise ValueError(f"SECURITY ERROR: Calendar {calendar_id} not in allowed write list")

        self.logger.debug(f"✅ Calendar write validation passed for {operation} to {calendar_id}")
        return True

    def _parse_space_reservation(self, space_res: Any) -> str:
        """Parse space reservation data with robust error handling for malformed data."""
        if not space_res:
            return ''

        try:
            # Handle string data (sometimes space_res comes as string)
            if isinstance(space_res, str):
                # Check if it looks like malformed JSON
                if space_res.startswith('{') and 'nil' in space_res:
                    self.logger.debug(f"Skipping malformed location data: {space_res}")
                    return ''
                return space_res

            # Handle list of rooms (multiple locations)
            if isinstance(space_res, list) and space_res:
                room_names = []
                for room in space_res:
                    room_name = self._extract_room_name(room)
                    if room_name:
                        room_names.append(room_name)

                if room_names:
                    # For events with many rooms, use primary location + count
                    if len(room_names) > 3:
                        return f"{room_names[0]} (+ {len(room_names)-1} other locations)"
                    else:
                        return ', '.join(room_names)
                return ''

            # Handle single room (dict)
            if isinstance(space_res, dict):
                return self._extract_room_name(space_res)

            # Handle unexpected data types
            self.logger.warning(f"Unexpected space_reservation type: {type(space_res)} - {space_res}")
            return str(space_res)[:50] + '...' if len(str(space_res)) > 50 else str(space_res)

        except Exception as e:
            self.logger.error(f"Error parsing space reservation: {e} - Data: {space_res}")
            return ''

    def _extract_room_name(self, room_data: Any) -> str:
        """Extract clean room name from room data."""
        if not room_data:
            return ''

        try:
            # Handle dict room data
            if isinstance(room_data, dict):
                # Check for nil/empty indicators
                if room_data.get('nil') or not room_data:
                    return ''

                # Extract room and building info
                building_raw = room_data.get('building_name', '')
                space_name = room_data.get('space_name', '') or room_data.get('formal_name', '')

                # Handle building name that might be an object with 'nil'
                building = ''
                if building_raw and not (isinstance(building_raw, dict) and building_raw.get('nil')):
                    building = str(building_raw)

                # Clean up space name if it contains building info already
                if space_name and building:
                    # Avoid redundant building names
                    if building.split()[0] not in space_name:
                        return f"{building} {space_name}"
                    else:
                        return space_name
                elif space_name:
                    return space_name
                elif building:
                    return building
                return ''

            # Handle string room data
            if isinstance(room_data, str):
                return room_data

            # Handle other types
            return str(room_data) if room_data else ''

        except Exception as e:
            self.logger.error(f"Error extracting room name: {e} - Data: {room_data}")
            return ''

    def _safe_extract_text(self, text_data: Any) -> str:
        """Safely extract text from potentially malformed data."""
        if not text_data:
            return ''

        try:
            # Handle string data
            if isinstance(text_data, str):
                # Clean up common malformed patterns
                text = text_data.strip()

                # Fix trailing quote issues like "Master Calendar '26"
                if text.endswith("'") and not text.startswith("'"):
                    # This looks like a malformed truncation, try to clean it
                    if "'26" in text:
                        text = text.replace("'26", " 2026")
                    elif "'25" in text:
                        text = text.replace("'25", " 2025")
                    elif "'24" in text:
                        text = text.replace("'24", " 2024")

                return text

            # Handle dict data with 'value' field
            if isinstance(text_data, dict):
                value = text_data.get('value', '') or text_data.get('text', '') or str(text_data)
                return self._safe_extract_text(value)  # Recursive call to handle nested structures

            # Handle other types
            return str(text_data) if text_data else ''

        except Exception as e:
            self.logger.error(f"Error extracting text: {e} - Data: {text_data}")
            return str(text_data)[:100] if text_data else ''

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

    def fetch_reservations(self, url_fragment: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch reservations from 25Live for a specific URL fragment and date range."""
        if not self.authenticated:
            raise Exception("Must authenticate with 25Live first")

        calendar_url = "https://25live.collegenet.com/25live/data/georgefox/run/home/calendar/calendardata.json"

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
                self.logger.debug(f"Retrieved {len(reservations)} reservations")
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

    def generate_date_ranges(self, months_back: int = 6, months_forward: int = 12,
                           custom_start_date: Optional[str] = None,
                           backfill_mode: bool = False) -> List[tuple]:
        """Generate date ranges respecting 25Live's 20-week limit.

        Args:
            months_back: Months to go back from today (ignored if custom_start_date provided)
            months_forward: Months to go forward from today
            custom_start_date: Custom start date in YYYY-MM-DD format for historical backfill
            backfill_mode: If True, goes from custom_start_date to today, otherwise normal forward range
        """
        ranges = []

        if custom_start_date:
            start_date = datetime.strptime(custom_start_date, '%Y-%m-%d')
            if backfill_mode:
                # Historical backfill: from custom_start_date to today
                end_date = datetime.now()
                self.logger.info(f"🔄 Backfill mode: syncing from {custom_start_date} to today")
            else:
                # Custom start with normal forward range
                end_date = start_date + timedelta(days=months_forward * 30)
                self.logger.info(f"🔄 Custom start mode: syncing from {custom_start_date} forward {months_forward} months")
        else:
            # Normal mode: back and forward from today
            start_date = datetime.now() - timedelta(days=months_back * 30)
            end_date = datetime.now() + timedelta(days=months_forward * 30)
            self.logger.info(f"🔄 Normal mode: syncing {months_back} months back to {months_forward} months forward")

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
        self.logger.info(f"Generated {len(ranges)} date ranges covering {total_days} days")
        return ranges

    def create_event_signature(self, reservation: Dict) -> str:
        """Create unique signature for duplicate detection."""
        # Use event details that should be unique
        signature_data = f"{reservation.get('event_start_dt', '')}-{reservation.get('event_end_dt', '')}-{reservation.get('event_name', '')}-{reservation.get('space_reservation', {}).get('space_name', '')}"
        return hashlib.md5(signature_data.encode()).hexdigest()

    def load_existing_events(self, calendar_id: str):
        """Load existing events from calendar for duplicate detection."""
        if calendar_id in self.existing_events:
            return  # Already loaded

        self.logger.info(f"Loading existing events from calendar: {calendar_id}")

        try:
            # Get events from the last 6 months to 1 year forward
            time_min = (datetime.now() - timedelta(days=180)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Index by time signature for quick duplicate checking
            self.existing_events[calendar_id] = {}
            for event in events:
                start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
                end = event.get('end', {}).get('dateTime', event.get('end', {}).get('date', ''))
                summary = event.get('summary', '')
                location = event.get('location', '')

                signature_data = f"{start}-{end}-{summary}-{location}"
                signature = hashlib.md5(signature_data.encode()).hexdigest()
                self.existing_events[calendar_id][signature] = event

            self.logger.info(f"Loaded {len(events)} existing events for duplicate detection")

        except Exception as e:
            self.logger.error(f"Failed to load existing events: {e}")
            self.existing_events[calendar_id] = {}

    def should_filter_event(self, reservation: Dict, calendar_type: str) -> bool:
        """Check if event should be filtered out (blocked)."""
        event_name = reservation.get('event_name', '')
        event_title = reservation.get('event_title', '')

        # Handle cases where values might be dictionaries or other types
        if isinstance(event_name, dict):
            event_name = str(event_name.get('value', ''))
        elif not isinstance(event_name, str):
            event_name = str(event_name) if event_name else ''

        if isinstance(event_title, dict):
            event_title = str(event_title.get('value', ''))
        elif not isinstance(event_title, str):
            event_title = str(event_title) if event_title else ''

        # Filter out events with no meaningful title
        # Only filter if BOTH event_name and event_title are empty or "no title"
        # This prevents filtering committee events that have event_name but event_title is {'nil': True}

        filter_patterns = [
            'no title',
            '',  # Empty string
        ]

        event_name_filtered = False
        event_title_filtered = False

        for pattern in filter_patterns:
            if event_name.lower().strip() == pattern.lower():
                event_name_filtered = True
            if event_title.lower().strip() == pattern.lower():
                event_title_filtered = True

        # Only filter if BOTH name and title are empty/meaningless
        if event_name_filtered and event_title_filtered:
            self.logger.debug(f"Filtering out event with no meaningful name or title: '{event_name}' / '{event_title}'")
            return True

        # Check interactive filter for specific titles to filter out
        filter_config_path = '/home/tradmin/CalPal/interactive_filter_config.json'
        try:
            import os
            if os.path.exists(filter_config_path):
                import json
                with open(filter_config_path, 'r') as f:
                    filter_config = json.load(f)

                filter_out_titles = filter_config.get('filter_out_titles', [])

                # Check if this event title should be filtered out
                for filter_title in filter_out_titles:
                    if event_name.strip() == filter_title.strip():
                        self.logger.debug(f"Filtering out event by interactive filter: '{event_name}'")
                        return True
                    if event_title.strip() == filter_title.strip():
                        self.logger.debug(f"Filtering out event by interactive filter: '{event_title}'")
                        return True
        except Exception as e:
            self.logger.debug(f"Error loading interactive filter config: {e}")

        return False

    def reservation_to_calendar_event(self, reservation: Dict, calendar_type: str) -> Optional[Dict]:
        """Convert 25Live reservation to Google Calendar event."""
        # Extract basic info with improved parsing
        event_name = self._safe_extract_text(reservation.get('event_name', ''))
        event_title = self._safe_extract_text(reservation.get('event_title', ''))
        start_dt = reservation.get('event_start_dt', '')
        end_dt = reservation.get('event_end_dt', '')

        # Extract location info with improved parsing
        space_res = reservation.get('space_reservation', {})
        location = ''

        # Enhanced location parsing to handle malformed data
        location = self._parse_space_reservation(space_res)

        # Create title based on calendar type
        if calendar_type == 'Classes':
            # For classes, use the course info (prefer event_title which has course names)
            title = event_title if event_title else event_name
        else:
            # For GFU Events, use the actual event name (not the category in event_title)
            # event_name contains the real event name, event_title contains categories like "Master Calendar"
            title = event_name if event_name else event_title


        # Build description
        description_parts = []
        description_parts.append(f"Source: 25Live {calendar_type}")

        if reservation.get('profile_name'):
            description_parts.append(f"Profile: {reservation['profile_name']}")

        if reservation.get('organization_name') and reservation['organization_name'] != '(Private)':
            description_parts.append(f"Organization: {reservation['organization_name']}")

        if reservation.get('event_locator'):
            description_parts.append(f"Event ID: {reservation['event_locator']}")

        description = '\n'.join(description_parts)

        # Create calendar event
        calendar_event = {
            'summary': title,
            'description': description,
            'location': location,
            'start': {
                'dateTime': start_dt,
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': end_dt,
                'timeZone': 'America/Los_Angeles'
            },
            'extendedProperties': {
                'private': {
                    'source': '25live',
                    'calendar_type': calendar_type,
                    'event_id': str(reservation.get('event_id', '')),
                    'reservation_id': str(reservation.get('reservation_id', '')),
                    'sync_time': datetime.now().isoformat()
                }
            }
        }

        return calendar_event

    def is_duplicate_event(self, calendar_id: str, calendar_event: Dict) -> bool:
        """Check if event already exists to prevent duplicates."""
        start = calendar_event.get('start', {}).get('dateTime', '')
        end = calendar_event.get('end', {}).get('dateTime', '')
        summary = calendar_event.get('summary', '')
        location = calendar_event.get('location', '')

        signature_data = f"{start}-{end}-{summary}-{location}"
        signature = hashlib.md5(signature_data.encode()).hexdigest()

        # Check against existing events
        if calendar_id in self.existing_events:
            if signature in self.existing_events[calendar_id]:
                return True

        # Check against events processed this run
        if signature in self.processed_events:
            return True

        # Mark as processed
        self.processed_events.add(signature)
        return False

    def create_calendar_event(self, calendar_id: str, calendar_event: Dict) -> bool:
        """Create event in Google Calendar."""
        try:
            # SECURITY: Validate calendar write permission
            self._validate_calendar_write(calendar_id, "create_calendar_event")

            created_event = self.calendar_service.events().insert(
                calendarId=calendar_id,
                body=calendar_event
            ).execute()

            self.logger.debug(f"Created event: {calendar_event.get('summary', 'Unknown')}")
            return True

        except HttpError as e:
            self.logger.error(f"Failed to create event: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error creating event: {e}")
            return False

    def create_gfu_event_with_mirror(self, gfu_calendar_id: str, calendar_event: Dict) -> bool:
        """Create GFU event on both GFU Events calendar and work calendar with tracking."""
        try:
            # SECURITY: Validate calendar write permissions
            self._validate_calendar_write(gfu_calendar_id, "create_gfu_event")
            self._validate_calendar_write(self.work_calendar, "create_gfu_work_mirror")

            # Create event signature for tracking
            signature = self._create_gfu_event_signature(calendar_event)

            # Create event on GFU Events calendar
            gfu_event = self.calendar_service.events().insert(
                calendarId=gfu_calendar_id,
                body=calendar_event
            ).execute()

            # Create mirror event on work calendar
            work_event = self._create_work_mirror_event(calendar_event)
            work_created = self.calendar_service.events().insert(
                calendarId=self.work_calendar,
                body=work_event
            ).execute()

            # Track the created events
            self.gfu_event_tracker['added_events'][signature] = {
                'timestamp': datetime.now().isoformat(),
                'gfu_event_id': gfu_event.get('id'),
                'work_event_id': work_created.get('id'),
                'summary': calendar_event.get('summary', ''),
                'start': calendar_event.get('start', {}),
                'location': calendar_event.get('location', ''),
                'synced_to_work': True
            }
            self._save_gfu_tracking_file('gfu_added_events.json', self.gfu_event_tracker['added_events'])

            self.logger.debug(f"Created GFU event with work mirror: {calendar_event.get('summary', 'Unknown')}")
            return True

        except HttpError as e:
            self.logger.error(f"Failed to create GFU event with mirror: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error creating GFU event with mirror: {e}")
            return False

    def _create_work_mirror_event(self, gfu_event: Dict) -> Dict:
        """Create a mirror event for the work calendar."""
        work_event = {
            'summary': gfu_event.get('summary', ''),
            'start': gfu_event.get('start', {}),
            'end': gfu_event.get('end', {}),
            'location': gfu_event.get('location', ''),
            'description': f"GFU Event (mirrored)\n\n{gfu_event.get('description', '')}",
            'extendedProperties': {
                'private': {
                    'source': 'gfu_events_mirror',
                    'original_gfu_event': 'true',
                    'sync_time': datetime.now().isoformat()
                }
            }
        }

        # Make it transparent so it doesn't conflict with other events
        work_event['transparency'] = 'transparent'
        work_event['visibility'] = 'private'

        return work_event

    def create_classes_event_with_mirror(self, classes_calendar_id: str, calendar_event: Dict) -> bool:
        """Create Classes event on both Classes calendar and work calendar with tracking."""
        try:
            # SECURITY: Validate calendar write permissions
            self._validate_calendar_write(classes_calendar_id, "create_classes_event")
            self._validate_calendar_write(self.work_calendar, "create_classes_work_mirror")

            # Create event signature for tracking
            signature = self._create_classes_event_signature(calendar_event)

            # Create event on Classes calendar
            classes_event = self.calendar_service.events().insert(
                calendarId=classes_calendar_id,
                body=calendar_event
            ).execute()

            # Create mirror event on work calendar
            work_event = self._create_classes_work_mirror_event(calendar_event)
            work_created = self.calendar_service.events().insert(
                calendarId=self.work_calendar,
                body=work_event
            ).execute()

            # Track the created events
            self.classes_event_tracker['mirrored_events'][signature] = {
                'timestamp': datetime.now().isoformat(),
                'classes_event_id': classes_event.get('id'),
                'work_event_id': work_created.get('id'),
                'summary': calendar_event.get('summary', ''),
                'start': calendar_event.get('start', {}),
                'location': calendar_event.get('location', ''),
                'synced_to_work': True
            }
            self._save_gfu_tracking_file('classes_mirrored_events.json', self.classes_event_tracker['mirrored_events'])

            self.logger.debug(f"Created Classes event with work mirror: {calendar_event.get('summary', 'Unknown')}")
            return True

        except HttpError as e:
            self.logger.error(f"Failed to create Classes event with mirror: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error creating Classes event with mirror: {e}")
            return False

    def _create_classes_work_mirror_event(self, classes_event: Dict) -> Dict:
        """Create a mirror event for the work calendar from a Classes event."""
        work_event = {
            'summary': classes_event.get('summary', ''),
            'start': classes_event.get('start', {}),
            'end': classes_event.get('end', {}),
            'location': classes_event.get('location', ''),
            'description': f"Class (mirrored from Classes calendar)\n\n{classes_event.get('description', '')}",
            'extendedProperties': {
                'private': {
                    'source': 'classes_mirror',
                    'original_classes_event': 'true',
                    'sync_time': datetime.now().isoformat()
                }
            }
        }

        # Make it show as busy (unlike GFU events which are transparent)
        work_event['transparency'] = 'opaque'  # Shows as busy for class times
        work_event['visibility'] = 'private'

        return work_event

    def detect_gfu_deletions(self) -> Dict[str, Any]:
        """Detect deleted GFU events and handle cleanup."""
        self.logger.info("🔍 Detecting GFU event deletions...")

        gfu_calendar_id = self.calendars.get('GFU Events')
        if not gfu_calendar_id:
            return {'success': False, 'error': 'No GFU Events calendar configured'}

        # Get current events from GFU Events calendar
        try:
            current_events = self._fetch_current_gfu_events(gfu_calendar_id)
            current_signatures = {self._create_gfu_event_signature(event) for event in current_events}

            # Check for deletions
            deletions_found = []
            for signature, tracked_event in self.gfu_event_tracker['added_events'].items():
                if signature not in current_signatures:
                    # Event was deleted from GFU Events calendar
                    deletions_found.append((signature, tracked_event))

            # Process deletions
            deletion_results = {
                'deletions_detected': len(deletions_found),
                'work_events_removed': 0,
                'blocklist_additions': 0,
                'errors': 0
            }

            for signature, tracked_event in deletions_found:
                try:
                    self.logger.info(f"Detected deletion: {tracked_event.get('summary', 'Unknown')}")

                    # Remove from work calendar if it exists
                    work_event_id = tracked_event.get('work_event_id')
                    if work_event_id and self._remove_work_mirror_event(work_event_id):
                        deletion_results['work_events_removed'] += 1

                    # Add to blocklist
                    event_data = {
                        'summary': tracked_event.get('summary', ''),
                        'start': tracked_event.get('start', {}),
                        'location': tracked_event.get('location', '')
                    }
                    self._add_to_gfu_blocklist(event_data, 'user_deleted_from_gfu')
                    deletion_results['blocklist_additions'] += 1

                    # Move to deleted events tracking
                    self.gfu_event_tracker['deleted_events'][signature] = {
                        **tracked_event,
                        'deletion_detected': datetime.now().isoformat(),
                        'removed_from_work': work_event_id is not None
                    }

                    # Remove from added events
                    del self.gfu_event_tracker['added_events'][signature]

                except Exception as e:
                    self.logger.error(f"Error processing deletion for {tracked_event.get('summary', 'Unknown')}: {e}")
                    deletion_results['errors'] += 1

            # Save updated tracking files
            self._save_gfu_tracking_file('gfu_added_events.json', self.gfu_event_tracker['added_events'])
            self._save_gfu_tracking_file('gfu_deleted_events.json', self.gfu_event_tracker['deleted_events'])

            self.logger.info(f"✅ Deletion detection complete: {deletion_results['deletions_detected']} deletions, "
                           f"{deletion_results['work_events_removed']} work events removed, "
                           f"{deletion_results['blocklist_additions']} added to blocklist")

            return {
                'success': True,
                'results': deletion_results
            }

        except Exception as e:
            self.logger.error(f"Failed to detect GFU deletions: {e}")
            return {'success': False, 'error': str(e)}

    def _fetch_current_gfu_events(self, gfu_calendar_id: str) -> List[Dict]:
        """Fetch current events from GFU Events calendar."""
        try:
            # Get events from 30 days back to 365 days forward
            time_min = (datetime.now() - timedelta(days=30)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId=gfu_calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])

        except Exception as e:
            self.logger.error(f"Failed to fetch current GFU events: {e}")
            return []

    def _remove_work_mirror_event(self, work_event_id: str) -> bool:
        """Remove mirrored event from work calendar."""
        try:
            self.calendar_service.events().delete(
                calendarId=self.work_calendar,
                eventId=work_event_id
            ).execute()
            self.logger.debug(f"Removed work mirror event: {work_event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.debug(f"Work mirror event already gone: {work_event_id}")
                return True  # Already deleted, consider it success
            self.logger.error(f"Failed to remove work mirror event {work_event_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error removing work mirror event {work_event_id}: {e}")
            return False

    def detect_and_restore_classes(self) -> Dict[str, Any]:
        """Detect missing Classes events from work calendar and restore them."""
        self.logger.info("🔍 Detecting missing Classes events from work calendar...")

        classes_calendar_id = self.calendars.get('Classes')
        if not classes_calendar_id:
            return {'success': False, 'error': 'No Classes calendar configured'}

        try:
            # Get current events from Classes calendar
            classes_events = self._fetch_current_classes_events(classes_calendar_id)

            # Get current events from work calendar (Classes mirrors only)
            work_classes_events = self._fetch_current_work_classes_events()

            # Create signatures for comparison
            classes_signatures = {self._create_classes_event_signature(event): event for event in classes_events}
            work_signatures = {self._create_classes_event_signature(event) for event in work_classes_events}

            # Find missing events (in Classes but not in work calendar)
            missing_signatures = set(classes_signatures.keys()) - work_signatures

            restoration_results = {
                'classes_events_found': len(classes_events),
                'work_mirror_events_found': len(work_classes_events),
                'missing_detected': len(missing_signatures),
                'events_restored': 0,
                'errors': 0
            }

            # Restore missing events
            for signature in missing_signatures:
                try:
                    classes_event = classes_signatures[signature]
                    self.logger.info(f"Restoring missing class: {classes_event.get('summary', 'Unknown')}")

                    # Create mirror event on work calendar
                    work_event = self._create_classes_work_mirror_event(classes_event)
                    # SECURITY: Validate work calendar write (redundant but safe)
                    self._validate_calendar_write(self.work_calendar, "restore_classes_work_mirror")
                    work_created = self.calendar_service.events().insert(
                        calendarId=self.work_calendar,
                        body=work_event
                    ).execute()

                    # Update tracking
                    self.classes_event_tracker['mirrored_events'][signature] = {
                        'timestamp': datetime.now().isoformat(),
                        'classes_event_id': classes_event.get('id'),
                        'work_event_id': work_created.get('id'),
                        'summary': classes_event.get('summary', ''),
                        'start': classes_event.get('start', {}),
                        'location': classes_event.get('location', ''),
                        'synced_to_work': True,
                        'restored': True,
                        'restoration_timestamp': datetime.now().isoformat()
                    }

                    restoration_results['events_restored'] += 1

                except Exception as e:
                    self.logger.error(f"Error restoring class {classes_signatures[signature].get('summary', 'Unknown')}: {e}")
                    restoration_results['errors'] += 1

            # Save updated tracking
            self._save_gfu_tracking_file('classes_mirrored_events.json', self.classes_event_tracker['mirrored_events'])

            self.logger.info(f"✅ Classes restoration complete: {restoration_results['events_restored']} events restored, "
                           f"{restoration_results['errors']} errors")

            return {
                'success': True,
                'results': restoration_results
            }

        except Exception as e:
            self.logger.error(f"Failed to detect/restore Classes events: {e}")
            return {'success': False, 'error': str(e)}

    def _fetch_current_classes_events(self, classes_calendar_id: str) -> List[Dict]:
        """Fetch current events from Classes calendar."""
        try:
            # Get events from 30 days back to 365 days forward
            time_min = (datetime.now() - timedelta(days=30)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId=classes_calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])

        except Exception as e:
            self.logger.error(f"Failed to fetch current Classes events: {e}")
            return []

    def _fetch_current_work_classes_events(self) -> List[Dict]:
        """Fetch current Classes mirror events from work calendar."""
        try:
            # Get events from 30 days back to 365 days forward
            time_min = (datetime.now() - timedelta(days=30)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId=self.work_calendar,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            # Filter for Classes mirror events only
            all_events = events_result.get('items', [])
            classes_events = []

            for event in all_events:
                extended_props = event.get('extendedProperties', {}).get('private', {})
                if extended_props.get('source') == 'classes_mirror':
                    classes_events.append(event)

            return classes_events

        except Exception as e:
            self.logger.error(f"Failed to fetch current work Classes events: {e}")
            return []

    def sync_calendar_type(self, calendar_type: str, custom_start_date: Optional[str] = None,
                         backfill_mode: bool = False) -> Dict[str, Any]:
        """Sync all events for a specific calendar type."""
        mode_desc = "historical backfill" if backfill_mode else "normal sync"
        self.logger.info(f"🔄 Syncing {calendar_type} events ({mode_desc})...")

        # Get configuration
        type_config = self.query_config.get(calendar_type, {})
        urls = type_config.get('URLs', [])
        calendar_id = self.calendars.get(calendar_type)

        if not calendar_id:
            return {'success': False, 'error': f'No calendar ID for {calendar_type}'}

        if not urls:
            return {'success': False, 'error': f'No URLs configured for {calendar_type}'}

        # Load existing events for duplicate detection
        self.load_existing_events(calendar_id)

        # Get date ranges (with custom start date support)
        date_ranges = self.generate_date_ranges(
            custom_start_date=custom_start_date,
            backfill_mode=backfill_mode
        )

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
                        # Check if event should be filtered out
                        if self.should_filter_event(reservation, calendar_type):
                            stats['filtered'] = stats.get('filtered', 0) + 1
                            continue

                        # Convert to calendar event
                        calendar_event = self.reservation_to_calendar_event(reservation, calendar_type)
                        if not calendar_event:  # Could be None if filtered
                            stats['filtered'] = stats.get('filtered', 0) + 1
                            continue

                        # GFU Events specific: Check blocklist
                        if calendar_type == 'GFU Events' and self._is_gfu_event_blocked(calendar_event):
                            stats['blocked'] = stats.get('blocked', 0) + 1
                            self.logger.debug(f"Skipping blocked GFU event: {calendar_event.get('summary', 'Unknown')}")
                            continue

                        # Check for duplicates
                        if self.is_duplicate_event(calendar_id, calendar_event):
                            stats['duplicates_skipped'] += 1
                            continue

                        # Create the event
                        if calendar_type == 'GFU Events':
                            # Special handling for GFU Events: create on both calendars
                            if self.create_gfu_event_with_mirror(calendar_id, calendar_event):
                                stats['events_created'] += 1
                            else:
                                stats['errors'] += 1
                        elif calendar_type == 'Classes':
                            # Special handling for Classes: create on both calendars (always mirror to work)
                            if self.create_classes_event_with_mirror(calendar_id, calendar_event):
                                stats['events_created'] += 1
                            else:
                                stats['errors'] += 1
                        else:
                            # Regular handling for other calendar types
                            if self.create_calendar_event(calendar_id, calendar_event):
                                stats['events_created'] += 1
                            else:
                                stats['errors'] += 1

                    except Exception as e:
                        self.logger.error(f"Error processing reservation: {e}")
                        stats['errors'] += 1

        self.logger.info(f"✅ {calendar_type} sync complete:")
        self.logger.info(f"  Total reservations: {stats['total_reservations']}")
        self.logger.info(f"  Events created: {stats['events_created']}")
        self.logger.info(f"  Duplicates skipped: {stats['duplicates_skipped']}")
        self.logger.info(f"  Filtered events: {stats.get('filtered', 0)}")
        if calendar_type == 'GFU Events':
            self.logger.info(f"  Blocked events: {stats.get('blocked', 0)}")
        self.logger.info(f"  Errors: {stats['errors']}")

        return {
            'success': True,
            'calendar_type': calendar_type,
            'stats': stats
        }

    def run_full_sync(self, custom_start_date: Optional[str] = None,
                    backfill_mode: bool = False) -> Dict[str, Any]:
        """Run complete synchronization of all calendar types."""
        mode_desc = f"historical backfill from {custom_start_date}" if backfill_mode else "normal"
        self.logger.info(f"🚀 Starting full 25Live synchronization ({mode_desc})...")

        # Authenticate with 25Live
        if not self.authenticate_25live():
            return {'success': False, 'error': 'Failed to authenticate with 25Live'}

        results = {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'sync_mode': 'backfill' if backfill_mode else 'normal',
            'custom_start_date': custom_start_date,
            'sync_results': {}
        }

        # Run deletion detection for GFU Events first
        self.logger.info("🔍 Running GFU Events deletion detection...")
        gfu_deletion_results = self.detect_gfu_deletions()
        results['gfu_deletion_detection'] = gfu_deletion_results

        # Run Classes restoration detection
        self.logger.info("🔍 Running Classes restoration detection...")
        classes_restoration_results = self.detect_and_restore_classes()
        results['classes_restoration'] = classes_restoration_results

        # Sync each calendar type
        for calendar_type in ['Classes', 'GFU Events']:
            try:
                result = self.sync_calendar_type(
                    calendar_type,
                    custom_start_date=custom_start_date,
                    backfill_mode=backfill_mode
                )
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
        with open('/home/tradmin/CalPal/25live_sync_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

        self.logger.info(f"🎉 Full sync complete! Created {total_created} events, skipped {total_duplicates} duplicates")
        return results

def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='25Live to Google Calendar Sync')
    parser.add_argument('--backfill-from', type=str, metavar='YYYY-MM-DD',
                       help='Backfill historical data from this date to today (e.g., 2024-01-01)')
    parser.add_argument('--custom-start', type=str, metavar='YYYY-MM-DD',
                       help='Custom start date for sync (normal forward sync from this date)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🔄 25LIVE CALENDAR SYNC")
    print("=" * 50)

    if args.backfill_from:
        print(f"Historical backfill mode: syncing from {args.backfill_from} to today...")
        custom_start_date = args.backfill_from
        backfill_mode = True
    elif args.custom_start:
        print(f"Custom start mode: syncing from {args.custom_start} forward...")
        custom_start_date = args.custom_start
        backfill_mode = False
    else:
        print("Normal mode: syncing recent past and future events...")
        custom_start_date = None
        backfill_mode = False

    print()

    sync_service = TwentyFiveLiveSync()
    results = sync_service.run_full_sync(
        custom_start_date=custom_start_date,
        backfill_mode=backfill_mode
    )

    if results['success']:
        print("✅ Synchronization completed successfully!")
    else:
        print("⚠️ Synchronization completed with some issues")

    print(f"\n📊 RESULTS:")
    if results.get('sync_mode') == 'backfill':
        print(f"  Mode: Historical backfill from {results.get('custom_start_date')}")
    elif results.get('custom_start_date'):
        print(f"  Mode: Custom start from {results.get('custom_start_date')}")
    else:
        print("  Mode: Normal sync")

    print(f"  Total events created: {results.get('total_events_created', 0)}")
    print(f"  Total duplicates skipped: {results.get('total_duplicates_skipped', 0)}")

    for calendar_type, result in results.get('sync_results', {}).items():
        status = "✅" if result.get('success') else "❌"
        print(f"  {status} {calendar_type}: {result.get('stats', {}).get('events_created', 0)} events")

    print(f"\n📄 Detailed results saved to: 25live_sync_results.json")

    # Usage examples
    if not any([args.backfill_from, args.custom_start]):
        print(f"\n💡 USAGE EXAMPLES:")
        print(f"  Normal sync:      python3 twentyfive_live_sync.py")
        print(f"  Historical fill:  python3 twentyfive_live_sync.py --backfill-from 2024-01-01")
        print(f"  Custom start:     python3 twentyfive_live_sync.py --custom-start 2024-08-01")

if __name__ == '__main__':
    main()