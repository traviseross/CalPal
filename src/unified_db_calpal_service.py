#!/usr/bin/env python3
"""
Unified Database-Aware CalPal Service

Coordinates all CalPal components in a continuous loop:
1. 25Live Sync (every 30 minutes) - Pull 25Live events into database
2. Calendar Scanner (every 15 minutes) - Scan all calendars for changes/deletions
3. Personal/Family Mirror (every 10 minutes) - Mirror personal/family to subcalendars + Work
4. Work Event Organizer (every 5 minutes) - Move bookings, mirror meetings
5. Subcalendar → Work Sync (every 10 minutes) - Ensure subcalendars mirrored to Work
6. Wife ICS Generator (every 5 minutes) - Generate ICS file from database

All components use the database as single source of truth.
"""

import logging
import time
import signal
import sys
import os
from datetime import datetime, timedelta
from threading import Thread, Event
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.db_manager import DatabaseManager
from src.db_aware_25live_sync import DBAware25LiveSync
from src.calendar_scanner import CalendarScanner
from src.personal_family_mirror import PersonalFamilyMirror
from src.work_event_organizer import WorkEventOrganizer
from src.subcalendar_work_sync import SubcalendarWorkSync
from src.db_aware_wife_ics_generator import DBWifeICSGenerator


class UnifiedCalPalService:
    """Unified service coordinating all CalPal components."""

    def __init__(self):
        self.logger = logging.getLogger('unified-calpal')

        # Shutdown signal
        self.shutdown_event = Event()

        # Component intervals (in seconds)
        self.intervals = {
            '25live_sync': 30 * 60,       # 30 minutes
            'calendar_scan': 15 * 60,     # 15 minutes
            'personal_family': 10 * 60,   # 10 minutes
            'work_organizer': 5 * 60,     # 5 minutes
            'subcalendar_sync': 10 * 60,  # 10 minutes
            'wife_ics': 5 * 60,           # 5 minutes
            'duplicate_check': 60 * 60    # 60 minutes (hourly)
        }

        # Last run times
        self.last_run = {
            '25live_sync': datetime.min,
            'calendar_scan': datetime.min,
            'personal_family': datetime.min,
            'work_organizer': datetime.min,
            'subcalendar_sync': datetime.min,
            'wife_ics': datetime.min,
            'duplicate_check': datetime.min
        }

        # Component instances (lazy loaded)
        self.components = {}

        # Initialize database connection check
        self.db = DatabaseManager(DATABASE_URL)
        if not self.db.test_connection():
            raise Exception("Failed to connect to database")

        self.logger.info("✅ Unified CalPal Service initialized")

    def _get_component(self, name: str):
        """Lazy load component instances."""
        if name not in self.components:
            self.logger.info(f"Initializing component: {name}")

            if name == '25live_sync':
                self.components[name] = DBAware25LiveSync()
            elif name == 'calendar_scan':
                self.components[name] = CalendarScanner()
            elif name == 'personal_family':
                self.components[name] = PersonalFamilyMirror()
            elif name == 'work_organizer':
                self.components[name] = WorkEventOrganizer()
            elif name == 'subcalendar_sync':
                self.components[name] = SubcalendarWorkSync()
            elif name == 'wife_ics':
                self.components[name] = DBWifeICSGenerator()

            self.logger.info(f"✅ Component initialized: {name}")

        return self.components[name]

    def should_run(self, component_name: str) -> bool:
        """Check if component should run based on interval."""
        now = datetime.now()
        last_run = self.last_run[component_name]
        interval = timedelta(seconds=self.intervals[component_name])

        return now - last_run >= interval

    def run_25live_sync(self) -> Dict[str, Any]:
        """Run 25Live sync."""
        try:
            self.logger.info("🔄 Running 25Live sync...")
            component = self._get_component('25live_sync')
            results = component.run_full_sync()
            self.last_run['25live_sync'] = datetime.now()

            self.logger.info(f"✅ 25Live sync complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ 25Live sync failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_calendar_scan(self) -> Dict[str, Any]:
        """Run calendar scanner."""
        try:
            self.logger.info("🔄 Running calendar scan...")
            component = self._get_component('calendar_scan')
            results = component.scan_all_calendars()
            self.last_run['calendar_scan'] = datetime.now()

            self.logger.info(f"✅ Calendar scan complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ Calendar scan failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_personal_family_mirror(self) -> Dict[str, Any]:
        """Run personal/family mirror sync."""
        try:
            self.logger.info("🔄 Running personal/family mirror...")
            component = self._get_component('personal_family')
            results = component.run_mirror_sync()
            self.last_run['personal_family'] = datetime.now()

            self.logger.info(f"✅ Personal/family mirror complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ Personal/family mirror failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_work_organizer(self) -> Dict[str, Any]:
        """Run work event organizer."""
        try:
            self.logger.info("🔄 Running work event organizer...")
            component = self._get_component('work_organizer')
            results = component.run_organization()
            self.last_run['work_organizer'] = datetime.now()

            self.logger.info(f"✅ Work event organizer complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ Work event organizer failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_subcalendar_sync(self) -> Dict[str, Any]:
        """Run subcalendar → Work sync."""
        try:
            self.logger.info("🔄 Running subcalendar → Work sync...")
            component = self._get_component('subcalendar_sync')
            results = component.run_sync()
            self.last_run['subcalendar_sync'] = datetime.now()

            self.logger.info(f"✅ Subcalendar sync complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ Subcalendar sync failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_wife_ics_generator(self) -> Dict[str, Any]:
        """Run wife ICS generator."""
        try:
            self.logger.info("🔄 Running wife ICS generator...")
            component = self._get_component('wife_ics')
            results = component.run_generation()
            self.last_run['wife_ics'] = datetime.now()

            self.logger.info(f"✅ Wife ICS generator complete")
            return results

        except Exception as e:
            self.logger.error(f"❌ Wife ICS generator failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_duplicate_check(self) -> Dict[str, Any]:
        """Check for and clean up duplicate events."""
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            from collections import defaultdict

            self.logger.info("🔍 Checking for duplicate events...")

            # Initialize Google Calendar
            credentials = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)

            # Calendars to check
            calendars = {
                'Work': WORK_CALENDAR_ID,
                'GFU Events': 'b0036cc72ee16aa510489117a037184cacc1b8d81b0fbbe19dfdea443915ce29@group.calendar.google.com',
                'Classes': '5e9b1db4268177878d1d06b8eb67a299e753d17d271b4d7301dac593c308b106@group.calendar.google.com'
            }

            results = {
                'duplicates_found': 0,
                'duplicates_removed': 0,
                'calendars_checked': []
            }

            for cal_name, cal_id in calendars.items():
                self.logger.info(f"  Checking {cal_name}...")

                # Fetch events
                events_result = service.events().list(
                    calendarId=cal_id,
                    timeMin=datetime.now().isoformat() + 'Z',
                    timeMax=(datetime.now() + timedelta(days=365)).isoformat() + 'Z',
                    maxResults=2500,
                    singleEvents=True
                ).execute()

                events = events_result.get('items', [])

                # Group by (summary, start_time)
                by_key = defaultdict(list)
                for event in events:
                    summary = event.get('summary', 'No Title')
                    start = event.get('start', {})
                    start_time = start.get('dateTime', start.get('date', 'unknown'))
                    key = (summary, start_time)
                    by_key[key].append(event)

                # Find and cleanup duplicates
                duplicates_in_cal = 0
                removed_in_cal = 0

                for (summary, start_time), evts in by_key.items():
                    if len(evts) > 1:
                        duplicates_in_cal += 1

                        # Keep oldest, delete rest
                        evts_sorted = sorted(evts, key=lambda e: e.get('created', ''))

                        for evt in evts_sorted[1:]:
                            try:
                                service.events().delete(
                                    calendarId=cal_id,
                                    eventId=evt['id']
                                ).execute()
                                removed_in_cal += 1
                                time.sleep(0.5)  # Rate limiting
                            except Exception as e:
                                self.logger.error(f"Error deleting {evt['id']}: {e}")

                results['duplicates_found'] += duplicates_in_cal
                results['duplicates_removed'] += removed_in_cal
                results['calendars_checked'].append({
                    'name': cal_name,
                    'duplicates': duplicates_in_cal,
                    'removed': removed_in_cal
                })

                self.logger.info(f"    {cal_name}: {duplicates_in_cal} duplicate groups, {removed_in_cal} removed")

            self.last_run['duplicate_check'] = datetime.now()

            self.logger.info(f"✅ Duplicate check complete - {results['duplicates_removed']} duplicates removed")
            return results

        except Exception as e:
            self.logger.error(f"❌ Duplicate check failed: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def run_cycle(self):
        """Run one cycle of all components that are due."""
        cycle_start = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info(f"🚀 Starting sync cycle at {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")

        components_run = []

        # Run components in order if they're due
        if self.should_run('25live_sync'):
            self.run_25live_sync()
            components_run.append('25Live Sync')

        if self.should_run('calendar_scan'):
            self.run_calendar_scan()
            components_run.append('Calendar Scanner')

        if self.should_run('personal_family'):
            self.run_personal_family_mirror()
            components_run.append('Personal/Family Mirror')

        if self.should_run('work_organizer'):
            self.run_work_organizer()
            components_run.append('Work Event Organizer')

        if self.should_run('subcalendar_sync'):
            self.run_subcalendar_sync()
            components_run.append('Subcalendar Sync')

        if self.should_run('wife_ics'):
            self.run_wife_ics_generator()
            components_run.append('Wife ICS Generator')

        if self.should_run('duplicate_check'):
            self.run_duplicate_check()
            components_run.append('Duplicate Check')

        cycle_end = datetime.now()
        cycle_duration = (cycle_end - cycle_start).total_seconds()

        if components_run:
            self.logger.info(f"✅ Cycle complete in {cycle_duration:.1f}s - Ran: {', '.join(components_run)}")
        else:
            self.logger.info(f"⏸️  No components due to run (cycle: {cycle_duration:.1f}s)")

        # Show next run times
        self.logger.info("\n📅 Next scheduled runs:")
        for component, last_run in sorted(self.last_run.items()):
            interval = timedelta(seconds=self.intervals[component])
            next_run = last_run + interval
            time_until = next_run - datetime.now()

            if time_until.total_seconds() < 0:
                self.logger.info(f"   {component}: NOW (overdue)")
            else:
                minutes = int(time_until.total_seconds() / 60)
                seconds = int(time_until.total_seconds() % 60)
                self.logger.info(f"   {component}: in {minutes}m {seconds}s")

        self.logger.info("=" * 60 + "\n")

    def run(self):
        """Main service loop."""
        self.logger.info("🚀 UNIFIED CALPAL SERVICE STARTING")
        self.logger.info("=" * 60)
        self.logger.info("Component intervals:")
        for component, interval in self.intervals.items():
            minutes = interval / 60
            self.logger.info(f"  {component}: every {minutes:.0f} minutes")
        self.logger.info("=" * 60 + "\n")

        # Run initial cycle immediately
        self.run_cycle()

        # Main loop - check every 30 seconds
        while not self.shutdown_event.is_set():
            try:
                # Sleep for 30 seconds
                if self.shutdown_event.wait(30):
                    break

                # Run cycle if any component is due
                self.run_cycle()

            except KeyboardInterrupt:
                self.logger.info("\n🛑 Received keyboard interrupt, shutting down...")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in main loop: {e}")
                import traceback
                traceback.print_exc()
                # Continue running despite errors
                time.sleep(60)

        self.logger.info("👋 Unified CalPal Service stopped")

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown handler."""
        self.logger.info(f"\n🛑 Received shutdown signal (signal: {signum})")
        self.shutdown_event.set()


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Unified CalPal Service')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--run-once', action='store_true',
                       help='Run one cycle then exit (for testing)')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("🎯 UNIFIED DATABASE-AWARE CALPAL SERVICE")
    print("=" * 60)
    print("Components:")
    print("  • 25Live Sync (30 min)")
    print("  • Calendar Scanner (15 min)")
    print("  • Personal/Family Mirror (10 min)")
    print("  • Work Event Organizer (5 min)")
    print("  • Subcalendar → Work Sync (10 min)")
    print("  • Wife ICS Generator (5 min)")
    print("=" * 60)
    print()

    # Create service
    service = UnifiedCalPalService()

    # Register signal handlers
    signal.signal(signal.SIGTERM, service.shutdown)
    signal.signal(signal.SIGINT, service.shutdown)

    if args.run_once:
        print("Running single cycle for testing...\n")
        service.run_cycle()
        print("\n✅ Single cycle complete!")
    else:
        # Run continuous service
        service.run()


if __name__ == '__main__':
    main()
