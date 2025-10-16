#!/usr/bin/env python3
"""
Find duplicate events WITHIN tross@georgefox.edu (same event appearing multiple times).
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


def get_calendar_events(service, calendar_id, days_ahead=30):
    """Get all events from work calendar."""
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=days_ahead)).isoformat() + 'Z'

    print(f"Fetching events from tross@georgefox.edu...")

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
        print(f"  Found {len(events)} total events")
        return events

    except Exception as e:
        print(f"  Error: {e}")
        return []


def find_internal_duplicates(events):
    """Find events that appear multiple times on the same calendar."""

    # Group by (summary, start_time)
    event_groups = defaultdict(list)

    for event in events:
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))
        key = (summary, start)
        event_groups[key].append(event)

    # Find groups with duplicates
    duplicates = {}
    for key, events_list in event_groups.items():
        if len(events_list) > 1:
            duplicates[key] = events_list

    return duplicates


def main():
    print("\n" + "=" * 80)
    print("INTERNAL DUPLICATE FINDER - tross@georgefox.edu")
    print("=" * 80)
    print("Finding events that appear MULTIPLE TIMES on the work calendar")
    print("=" * 80)
    print()

    # Initialize
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    # Get events
    events = get_calendar_events(service, work_calendar_id)

    # Find duplicates
    duplicates = find_internal_duplicates(events)

    # Report
    print("\n" + "=" * 80)
    print("DUPLICATE REPORT")
    print("=" * 80)

    if not duplicates:
        print("\n✅ No internal duplicates found!")
    else:
        total_duplicate_events = sum(len(events_list) for events_list in duplicates.values())
        print(f"\n⚠️  Found {len(duplicates)} unique events with duplicates")
        print(f"    Total duplicate instances: {total_duplicate_events}")
        print()

        for i, ((summary, start), events_list) in enumerate(sorted(duplicates.items(), key=lambda x: x[0][1]), 1):
            print(f"\n{i}. {summary}")
            print(f"   Start: {start}")
            print(f"   Appears {len(events_list)} times:")
            print()

            for j, event in enumerate(events_list, 1):
                event_id = event['id']
                color = event.get('colorId', 'default')
                location = event.get('location', '')

                # Get extended properties for source info
                ext_props = event.get('extendedProperties', {}).get('private', {})
                source = ext_props.get('source', 'unknown')
                event_type = ext_props.get('event_type', 'unknown')

                print(f"     Instance {j}:")
                print(f"       Event ID: {event_id}")
                print(f"       Color: {color}")
                print(f"       Source: {source}")
                print(f"       Event Type: {event_type}")
                if location:
                    print(f"       Location: {location}")

                # Check database for this event
                profile = ext_props.get('calendar_type', '')
                if profile:
                    print(f"       Calendar Type: {profile}")
                print()

    print("=" * 80)

    # Save detailed report
    report = []
    for (summary, start), events_list in duplicates.items():
        report.append({
            'summary': summary,
            'start': start,
            'count': len(events_list),
            'instances': [
                {
                    'event_id': e['id'],
                    'color': e.get('colorId', 'default'),
                    'location': e.get('location', ''),
                    'source': e.get('extendedProperties', {}).get('private', {}).get('source', ''),
                    'event_type': e.get('extendedProperties', {}).get('private', {}).get('event_type', '')
                }
                for e in events_list
            ]
        })

    report_file = 'work_calendar_duplicates.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n📄 Detailed report saved to: {report_file}")
    print()


if __name__ == '__main__':
    main()
