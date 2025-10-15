#!/usr/bin/env python3
"""
Update colors on existing Work calendar events based on their source.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *

# Color mapping based on source calendar
# Appointments #C89620 -> 6 (Tangerine)
# Classes #CA8E00 -> 5 (Banana)
# GFU Events #7998AC -> 9 (Blueberry)
# Meetings #536999 -> 7 (Peacock)

def get_calendar_service():
    """Initialize Google Calendar API service."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=GOOGLE_SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)


def load_subcalendars():
    """Load subcalendar mappings."""
    try:
        subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
        with open(subcalendars_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load subcalendars: {e}")
        return {}


def get_color_for_source(extended_props, subcalendars):
    """Determine color based on extended properties."""
    if not extended_props:
        return None

    private = extended_props.get('private', {})
    mirror_source = private.get('mirror_source', '')
    event_type = private.get('event_type', '')

    # Check if this is a mirror event
    if mirror_source:
        # Appointments
        if mirror_source == subcalendars.get('Appointments'):
            return '6'  # Tangerine
        # Classes
        elif mirror_source == subcalendars.get('Classes'):
            return '5'  # Banana
        # GFU Events
        elif mirror_source == subcalendars.get('GFU Events'):
            return '9'  # Blueberry
        # Meetings
        elif mirror_source == subcalendars.get('Meetings'):
            return '7'  # Peacock

    # Check event type for non-mirror events
    if event_type:
        if 'appointment' in event_type.lower():
            return '6'
        elif 'class' in event_type.lower() or '25live_class' in event_type.lower():
            return '5'
        elif 'meeting' in event_type.lower():
            return '7'

    return None


def update_event_colors(service, work_calendar_id, subcalendars, days_ahead=7, dry_run=True):
    """Update colors on events for the next N days."""

    # Get events for the next week
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=days_ahead)).isoformat() + 'Z'

    print(f"Fetching events from {work_calendar_id}...")
    print(f"Date range: now to {days_ahead} days ahead")
    print()

    events_result = service.events().list(
        calendarId=work_calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime',
        maxResults=500
    ).execute()

    events = events_result.get('items', [])
    print(f"Found {len(events)} events")
    print()

    stats = {
        'total': len(events),
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'no_color_needed': 0
    }

    for event in events:
        event_id = event['id']
        summary = event.get('summary', 'Untitled')
        current_color = event.get('colorId', 'default')
        extended_props = event.get('extendedProperties', {})

        # Determine what color this event should have
        target_color = get_color_for_source(extended_props, subcalendars)

        if not target_color:
            stats['no_color_needed'] += 1
            continue

        # Check if color needs updating
        if current_color == target_color:
            print(f"✓ {summary[:50]} - already color {target_color}")
            stats['skipped'] += 1
            continue

        # Update needed
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"{'[DRY RUN] ' if dry_run else ''}Updating: {summary[:50]}")
        print(f"  Start: {start}")
        print(f"  Current color: {current_color} -> Target color: {target_color}")

        if not dry_run:
            try:
                time.sleep(0.1)  # Rate limiting

                # Update only the colorId
                updated_event = service.events().patch(
                    calendarId=work_calendar_id,
                    eventId=event_id,
                    body={'colorId': target_color}
                ).execute()

                print(f"  ✅ Updated successfully")
                stats['updated'] += 1

            except HttpError as e:
                print(f"  ❌ Error: {e}")
                stats['errors'] += 1
            except Exception as e:
                print(f"  ❌ Unexpected error: {e}")
                stats['errors'] += 1
        else:
            stats['updated'] += 1

        print()

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Update event colors on Work calendar')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days ahead to process (default: 7)')
    parser.add_argument('--live', action='store_true',
                       help='Actually update events (default is dry run)')
    args = parser.parse_args()

    print("=" * 60)
    print("UPDATE EVENT COLORS ON WORK CALENDAR")
    print("=" * 60)
    if args.live:
        print("🔴 LIVE MODE - Will update events")
    else:
        print("🧪 DRY RUN - Will only show what would change")
    print("=" * 60)
    print()

    # Initialize
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')
    subcalendars = load_subcalendars()

    print(f"Subcalendars loaded:")
    for name, cal_id in subcalendars.items():
        print(f"  • {name}: {cal_id}")
    print()

    # Update colors
    stats = update_event_colors(
        service,
        work_calendar_id,
        subcalendars,
        days_ahead=args.days,
        dry_run=not args.live
    )

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total events: {stats['total']}")
    print(f"Updated: {stats['updated']}")
    print(f"Skipped (already correct): {stats['skipped']}")
    print(f"No color needed: {stats['no_color_needed']}")
    print(f"Errors: {stats['errors']}")
    print()

    if not args.live and stats['updated'] > 0:
        print("💡 To apply these changes, run with --live flag")


if __name__ == '__main__':
    main()
