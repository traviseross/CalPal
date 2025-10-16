#!/usr/bin/env python3
"""
Find duplicate events on tross@georgefox.edu and identify their subcalendar sources.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


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


def get_calendar_events(service, calendar_id, calendar_name, days_ahead=30):
    """Get all events from a calendar."""
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=days_ahead)).isoformat() + 'Z'

    print(f"  Fetching events from {calendar_name}...")

    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=2500
        ).execute()

        events = events_result.get('items', [])
        print(f"    Found {len(events)} events")
        return events

    except Exception as e:
        print(f"    Error: {e}")
        return []


def find_duplicates_on_work_calendar(service, work_calendar_id, subcalendars):
    """Find events on work calendar that match events on subcalendars."""

    print("\n" + "=" * 80)
    print("DUPLICATE DETECTION")
    print("=" * 80)

    # Get events from work calendar
    print("\n1. Scanning work calendar (tross@georgefox.edu)...")
    work_events = get_calendar_events(service, work_calendar_id, "tross@georgefox.edu")

    # Build lookup by (summary, start_time)
    work_event_lookup = {}
    for event in work_events:
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))
        key = (summary, start)
        work_event_lookup[key] = event

    print(f"\n   Created lookup with {len(work_event_lookup)} unique events")

    # Check each subcalendar for matches
    duplicates = defaultdict(list)

    print("\n2. Checking subcalendars for duplicates...")
    for subcal_name, subcal_id in subcalendars.items():
        if subcal_name in ['Personal Events', 'Family Events']:
            continue  # Skip non-work subcalendars

        print(f"\n   Checking {subcal_name}...")
        subcal_events = get_calendar_events(service, subcal_id, subcal_name)

        matches = 0
        for event in subcal_events:
            summary = event.get('summary', 'Untitled')
            start = event['start'].get('dateTime', event['start'].get('date'))
            key = (summary, start)

            if key in work_event_lookup:
                # Found a duplicate!
                work_event = work_event_lookup[key]
                duplicates[subcal_name].append({
                    'summary': summary,
                    'start': start,
                    'work_event_id': work_event['id'],
                    'subcal_event_id': event['id'],
                    'work_color': work_event.get('colorId', 'default'),
                    'location': event.get('location', '')
                })
                matches += 1

        print(f"      → Found {matches} duplicates")

    return duplicates


def main():
    print("\n" + "=" * 80)
    print("DUPLICATE FINDER")
    print("=" * 80)
    print("Finding events that exist on both tross@georgefox.edu and subcalendars")
    print("=" * 80)

    # Initialize
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')
    subcalendars = load_subcalendars()

    # Find duplicates
    duplicates = find_duplicates_on_work_calendar(service, work_calendar_id, subcalendars)

    # Report
    print("\n" + "=" * 80)
    print("DUPLICATE REPORT")
    print("=" * 80)

    total_duplicates = sum(len(dupes) for dupes in duplicates.values())

    if total_duplicates == 0:
        print("\n✅ No duplicates found!")
    else:
        print(f"\n⚠️  Found {total_duplicates} duplicate events across subcalendars:")
        print()

        for subcal_name, dupes in sorted(duplicates.items()):
            if dupes:
                print(f"\n{subcal_name}: {len(dupes)} duplicates")
                print("-" * 80)

                for i, dup in enumerate(dupes[:10], 1):  # Show first 10
                    print(f"  {i}. {dup['summary'][:60]}")
                    print(f"     Start: {dup['start']}")
                    print(f"     Work event ID: {dup['work_event_id']}")
                    print(f"     Work color: {dup['work_color']}")
                    print(f"     Subcal event ID: {dup['subcal_event_id']}")
                    if dup['location']:
                        print(f"     Location: {dup['location'][:50]}")
                    print()

                if len(dupes) > 10:
                    print(f"  ... and {len(dupes) - 10} more")
                    print()

    print("=" * 80)

    # Save detailed report
    report_file = 'duplicate_report.json'
    with open(report_file, 'w') as f:
        json.dump(duplicates, f, indent=2, default=str)

    print(f"\n📄 Detailed report saved to: {report_file}")
    print()


if __name__ == '__main__':
    main()
