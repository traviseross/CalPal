#!/usr/bin/env python3
"""
Update appointment/booking event colors to orange (colorId 6).

Appointments should be in the yellow family but distinct from classes.
Classes: Yellow (5)
Appointments: Tangerine/Orange (6)
"""

import os
import sys
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


def get_calendar_service():
    """Initialize Google Calendar API service."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=GOOGLE_SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def get_appointment_events(service, work_calendar_id):
    """Get all appointment/booking events."""
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'

    print(f"Fetching events from tross@georgefox.edu...")

    try:
        events_result = service.events().list(
            calendarId=work_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=2500
        ).execute()

        all_events = events_result.get('items', [])
        print(f"  Found {len(all_events)} total events")

        # Filter for appointments
        appointment_events = []
        for event in all_events:
            ext_props = event.get('extendedProperties', {}).get('private', {})
            event_type = ext_props.get('event_type', '')
            summary = event.get('summary', '')

            # Check if it's an appointment/booking
            if ('booking' in event_type.lower() or
                'appointment' in event_type.lower() or
                'Meet with Travis Ross' in summary):
                appointment_events.append(event)

        print(f"  Found {len(appointment_events)} appointment events")
        return appointment_events

    except Exception as e:
        print(f"  Error: {e}")
        return []


def update_colors(service, work_calendar_id, events, target_color='6', dry_run=True):
    """Update event colors."""

    print(f"\n{'=' * 80}")
    if dry_run:
        print("DRY RUN - Would update these events to orange (colorId 6):")
    else:
        print("LIVE MODE - Updating events to orange (colorId 6):")
    print(f"{'=' * 80}\n")

    stats = {'updated': 0, 'skipped': 0, 'errors': 0}

    for event in events:
        event_id = event['id']
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))
        current_color = event.get('colorId', 'default')

        print(f"{stats['updated'] + stats['skipped'] + 1}. {summary[:60]}")
        print(f"   Start: {start}")
        print(f"   Current color: {current_color} → Target: {target_color}")

        if current_color == target_color:
            print(f"   ✓ Already correct color")
            stats['skipped'] += 1
        elif not dry_run:
            try:
                time.sleep(0.1)  # Rate limiting

                service.events().patch(
                    calendarId=work_calendar_id,
                    eventId=event_id,
                    body={'colorId': target_color}
                ).execute()

                print(f"   ✅ Updated")
                stats['updated'] += 1

            except HttpError as e:
                print(f"   ❌ Error: {e}")
                stats['errors'] += 1
        else:
            stats['updated'] += 1

        print()

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Update appointment colors to orange')
    parser.add_argument('--live', action='store_true',
                       help='Actually update colors (default is dry run)')
    args = parser.parse_args()

    dry_run = not args.live

    print("\n" + "=" * 80)
    print("APPOINTMENT COLOR UPDATE")
    print("=" * 80)
    if dry_run:
        print("🧪 DRY RUN - No changes will be made")
    else:
        print("🔴 LIVE MODE - Will update appointment colors")
    print("=" * 80)
    print()

    # Initialize
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    # Get appointment events
    appointments = get_appointment_events(service, work_calendar_id)

    if not appointments:
        print("✅ No appointments found!")
        return

    # Update colors
    stats = update_colors(service, work_calendar_id, appointments, target_color='6', dry_run=dry_run)

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total appointments: {len(appointments)}")
    if not dry_run:
        print(f"Updated: {stats['updated']}")
        print(f"Already correct: {stats['skipped']}")
        print(f"Errors: {stats['errors']}")
    else:
        print(f"Would update: {stats['updated']}")
        print(f"Already correct: {stats['skipped']}")
    print()

    if dry_run:
        print("💡 To apply these changes, run with --live flag")
    else:
        print("✅ Color update complete!")


if __name__ == '__main__':
    main()
