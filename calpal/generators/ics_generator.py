#!/usr/bin/env python3
"""
Simplified Shared Calendar ICS Generator

Generates ICS file from database events with filtering rules:
- Include all events from Work calendar (tross@georgefox.edu)
- Include all events from Personal calendar (travis.e.ross@gmail.com)
- Exclude events from Family calendar
- Exclude deleted events (deleted_at IS NOT NULL)
- Apply anonymization rules for student appointments

Architecture: Single work calendar with color-coded events.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from icalendar import Calendar, Event as ICalEvent
from sqlalchemy import text
import pytz

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from calpal.core.db_manager import DatabaseManager


class DBWifeICSGenerator:
    """Generate wife calendar ICS from database events."""

    def __init__(self):
        self.logger = logging.getLogger('db-wife-ics')

        # Initialize database
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        # Output configuration
        self.ics_output_path = ICS_FILE_PATH
        self.public_url = os.getenv('PUBLIC_ICS_URL', f"https://example.com/{os.getenv('SECURE_ENDPOINT_PATH', 'secure')}/schedule.ics")

        # Source calendars to exclude
        self.personal_calendar = PERSONAL_CALENDAR_ID
        self.family_calendar = os.getenv('FAMILY_CALENDAR_ID', '')
        self.work_calendar = WORK_CALENDAR_ID

    def get_events_for_wife(self, days_back: int = 7, days_forward: int = 365) -> List[Dict]:
        """Get events from database that should be included in wife's ICS."""
        try:
            # Calculate time range
            time_min = datetime.now() - timedelta(days=days_back)
            time_max = datetime.now() + timedelta(days=days_forward)

            with self.db.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT DISTINCT ON (event_id, current_calendar)
                            event_id, ical_uid, summary, description, location,
                            start_time, end_time, is_all_day, current_calendar,
                            source_calendar, event_type, created_at, updated_at
                        FROM calendar_events
                        WHERE start_time >= :time_min
                        AND start_time <= :time_max
                        AND deleted_at IS NULL
                        AND status = 'active'
                        AND source_calendar != :family_calendar
                        AND (current_calendar = :work_calendar OR current_calendar = :personal_calendar)
                        ORDER BY event_id, current_calendar, start_time
                    """),
                    {
                        "time_min": time_min,
                        "time_max": time_max,
                        "personal_calendar": self.personal_calendar,
                        "family_calendar": self.family_calendar,
                        "work_calendar": self.work_calendar
                    }
                ).mappings().all()

                events = [dict(row) for row in results]
                self.logger.info(f"Found {len(events)} events for wife calendar")
                return events

        except Exception as e:
            self.logger.error(f"Error fetching events: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _anonymize_event_summary(self, event_data: Dict) -> str:
        """Apply anonymization rules to event summary."""
        summary = event_data.get('summary', 'Untitled')
        event_type = event_data.get('event_type', '')
        location = event_data.get('location', '')

        # Rule 1: Anonymize appointments
        # Check event type or summary patterns
        if ('appointment' in event_type.lower() or
            'booking' in event_type.lower() or
            'Meet with Travis Ross' in summary or
            'appointment' in summary.lower()):
            return "Student appointment"

        # Rule 2: For classes, add location if present
        if event_type == '25live_class' and location:
            # Only add location if not already in summary
            if location not in summary:
                return f"{summary} in {location}"

        return summary

    def generate_ics_file(self, events: List[Dict]) -> str:
        """Generate ICS file content from database events."""
        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//Travis Ross//Wife Calendar DB//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('x-wr-calname', 'Travis Work Status')
        cal.add('x-wr-caldesc', 'Travis work calendar status for scheduling')

        # Add events
        for event_data in events:
            try:
                event = ICalEvent()

                # Basic event properties - apply anonymization
                summary = self._anonymize_event_summary(event_data)
                event.add('summary', summary)

                # Add description if present
                description = event_data.get('description', '')
                if description:
                    event.add('description', description)

                # Add location if present
                location = event_data.get('location', '')
                if location:
                    event.add('location', location)

                # Handle start/end times
                start_time = event_data['start_time']
                end_time = event_data['end_time']
                is_all_day = event_data.get('is_all_day', False)

                if is_all_day:
                    # All-day event
                    event.add('dtstart', start_time.date())
                    event.add('dtend', end_time.date())
                else:
                    # Timed event - ensure timezone aware
                    if start_time.tzinfo is None:
                        start_time = pytz.UTC.localize(start_time)
                    if end_time.tzinfo is None:
                        end_time = pytz.UTC.localize(end_time)

                    event.add('dtstart', start_time)
                    event.add('dtend', end_time)

                # Generate unique ID from event_id or ical_uid
                ical_uid = event_data.get('ical_uid')
                event_id = event_data.get('event_id', '')

                if ical_uid:
                    uid = ical_uid
                else:
                    uid = f"{event_id}@wife-calendar.{os.getenv('PUBLIC_DOMAIN', 'example.com')}"

                event.add('uid', uid)

                # Add timestamps
                now = datetime.now(pytz.UTC)
                event.add('dtstamp', now)

                created_at = event_data.get('created_at')
                if created_at:
                    if created_at.tzinfo is None:
                        created_at = pytz.UTC.localize(created_at)
                    event.add('created', created_at)

                updated_at = event_data.get('updated_at')
                if updated_at:
                    if updated_at.tzinfo is None:
                        updated_at = pytz.UTC.localize(updated_at)
                    event.add('last-modified', updated_at)

                # Add to calendar
                cal.add_component(event)

            except Exception as e:
                self.logger.error(f"Error adding event {event_data.get('summary', 'Unknown')}: {e}")
                continue

        # Convert to ICS format
        ics_bytes = cal.to_ical()
        ics_content = ics_bytes.decode('utf-8')

        return ics_content

    def save_ics_file(self, ics_content: str, events_count: int):
        """Save ICS content to file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.ics_output_path), exist_ok=True)

            # Write ICS file
            with open(self.ics_output_path, 'w', encoding='utf-8') as f:
                f.write(ics_content)

            self.logger.info(f"✅ ICS file saved to: {self.ics_output_path}")
            self.logger.info(f"   File size: {len(ics_content)} bytes")
            self.logger.info(f"   Events included: {events_count}")

            # Save metadata
            metadata = {
                'generated_at': datetime.now().isoformat(),
                'public_url': self.public_url,
                'events_count': events_count,
                'file_size_bytes': len(ics_content),
                'source': 'database',
                'excluded_calendars': [
                    self.personal_calendar,
                    self.family_calendar
                ]
            }

            metadata_path = self.ics_output_path.replace('.ics', '_metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Force Flask to reload by restarting it
            self._restart_flask_server()

            return metadata

        except Exception as e:
            self.logger.error(f"Failed to save ICS file: {e}")
            raise

    def _restart_flask_server(self):
        """Restart Flask server to ensure it serves the updated ICS file."""
        try:
            import subprocess
            import signal as sig

            # Find Flask server process
            result = subprocess.run(
                ['pgrep', '-f', 'calpal_flask_server.py'],
                capture_output=True,
                text=True
            )

            if result.returncode == 0 and result.stdout.strip():
                pid = int(result.stdout.strip().split()[0])
                self.logger.info(f"🔄 Restarting Flask server (PID: {pid}) to serve updated ICS file...")

                # Send SIGTERM to gracefully stop Flask
                os.kill(pid, sig.SIGTERM)

                # Wait a moment for it to stop
                import time
                time.sleep(1)

                # Restart Flask in background
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                subprocess.Popen(
                    ['nohup', 'python3', 'src/calpal_flask_server.py', '--port', '5001', '--host', '0.0.0.0'],
                    cwd=project_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

                self.logger.info("✅ Flask server restarted successfully")
            else:
                self.logger.warning("Flask server not found - skipping restart")

        except Exception as e:
            self.logger.warning(f"Could not restart Flask server: {e}")
            # Don't fail the ICS generation if Flask restart fails
            pass

    def run_generation(self, days_back: int = 7, days_forward: int = 365):
        """Run the complete ICS generation process."""
        self.logger.info("🔄 Starting database-aware wife calendar ICS generation...")

        # Get events from database
        events = self.get_events_for_wife(days_back, days_forward)

        if not events:
            self.logger.warning("No events found for wife calendar")
            # Still generate empty calendar
            events = []

        self.logger.info(f"Processing {len(events)} events...")

        # Generate ICS content
        ics_content = self.generate_ics_file(events)

        # Verify content not truncated
        if len(ics_content) < 100:
            self.logger.warning("ICS content appears truncated!")
        else:
            self.logger.info(f"Generated ICS content: {len(ics_content)} bytes")

        # Save to file
        metadata = self.save_ics_file(ics_content, len(events))

        # Summary
        self.logger.info("=" * 60)
        self.logger.info("📅 WIFE CALENDAR ICS GENERATION COMPLETE")
        self.logger.info(f"Total events: {len(events)}")
        self.logger.info(f"File size: {len(ics_content)} bytes")
        self.logger.info(f"ICS file: {self.ics_output_path}")
        self.logger.info(f"Public URL: {self.public_url}")
        self.logger.info("=" * 60)

        return metadata


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Generate wife calendar ICS from database')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Days to look back for events (default: 7)')
    parser.add_argument('--days-forward', type=int, default=365,
                       help='Days to look forward for events (default: 365)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("📅 DATABASE-AWARE WIFE CALENDAR ICS GENERATOR")
    print("=" * 50)
    print("Excluding: Personal and Family calendars")
    print("Excluding: Events deleted from Work calendar")
    print()

    generator = DBWifeICSGenerator()
    generator.run_generation(args.days_back, args.days_forward)

    print("\n✅ ICS generation complete!")


if __name__ == '__main__':
    main()
