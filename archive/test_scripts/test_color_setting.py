#!/usr/bin/env python3
"""
Test script to verify we can set different colors on events in the root Work calendar.
"""

import os
import sys
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import *

# Google Calendar colorId reference:
# 1: Lavender, 2: Sage, 3: Grape, 4: Flamingo, 5: Banana
# 6: Tangerine, 7: Peacock, 8: Graphite, 9: Blueberry, 10: Basil
# 11: Tomato

# Your custom hex colors mapped to nearest Google Calendar colorIds:
# Appointments #C89620 (golden/orange) -> 6 (Tangerine)
# Classes #CA8E00 (golden/yellow) -> 5 (Banana)
# GFU Events #7998AC (blue/purple) -> 9 (Blueberry)
# Meetings #536999 (navy blue) -> 7 (Peacock)

def get_calendar_service():
    """Initialize Google Calendar API service."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=GOOGLE_SCOPES
    )

    return build('calendar', 'v3', credentials=credentials)


def create_test_events(service):
    """Create test events with different colors."""
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    # Base time for test events
    start_time = datetime.now() + timedelta(days=1, hours=10)

    test_events = [
        {
            'name': 'TEST Appointment Color',
            'color': '6',  # Tangerine (closest to #C89620)
            'description': 'Testing appointment color #C89620 -> colorId 6 (Tangerine)'
        },
        {
            'name': 'TEST Class Color',
            'color': '5',  # Banana (closest to #CA8E00)
            'description': 'Testing class color #CA8E00 -> colorId 5 (Banana)'
        },
        {
            'name': 'TEST GFU Event Color',
            'color': '9',  # Blueberry (closest to #7998AC)
            'description': 'Testing GFU event color #7998AC -> colorId 9 (Blueberry)'
        },
        {
            'name': 'TEST Meeting Color',
            'color': '7',  # Peacock (closest to #536999)
            'description': 'Testing meeting color #536999 -> colorId 7 (Peacock)'
        }
    ]

    created_events = []

    for i, test_event in enumerate(test_events):
        # Stagger events by 30 minutes
        event_start = start_time + timedelta(minutes=i*30)
        event_end = event_start + timedelta(minutes=20)

        event_body = {
            'summary': test_event['name'],
            'description': test_event['description'],
            'start': {
                'dateTime': event_start.isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'end': {
                'dateTime': event_end.isoformat(),
                'timeZone': 'America/Los_Angeles'
            },
            'colorId': test_event['color']
        }

        print(f"Creating test event: {test_event['name']} with colorId {test_event['color']}")

        try:
            created_event = service.events().insert(
                calendarId=work_calendar_id,
                body=event_body
            ).execute()

            created_events.append({
                'id': created_event['id'],
                'summary': created_event['summary'],
                'colorId': created_event.get('colorId', 'default'),
                'link': created_event.get('htmlLink')
            })

            print(f"  ✅ Created: {created_event['id']}")
            print(f"     Color: {created_event.get('colorId', 'default')}")
            print(f"     Link: {created_event.get('htmlLink')}")

        except Exception as e:
            print(f"  ❌ Error creating event: {e}")

    return created_events


def main():
    """Main test function."""
    print("=" * 60)
    print("COLOR SETTING TEST FOR ROOT WORK CALENDAR")
    print("=" * 60)
    print()

    print("This script will create 4 test events with different colors:")
    print("  • Appointment (Tangerine/Orange)")
    print("  • Class (Banana/Yellow)")
    print("  • GFU Event (Blueberry/Blue)")
    print("  • Meeting (Peacock/Navy)")
    print()

    # Get calendar service
    print("Initializing Google Calendar API...")
    service = get_calendar_service()
    print("✅ API initialized")
    print()

    # Create test events
    print("Creating test events...")
    created_events = create_test_events(service)
    print()

    # Summary
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print(f"Created {len(created_events)} test events")
    print()
    print("Please check your Work calendar to verify the colors appear correctly.")
    print()
    print("Event IDs (for cleanup):")
    for event in created_events:
        print(f"  {event['id']} - {event['summary']}")
    print()
    print("To delete these test events, run:")
    print(f"  python3 -c \"from test_color_setting import cleanup_test_events; cleanup_test_events({[e['id'] for e in created_events]})\"")
    print()


def cleanup_test_events(event_ids):
    """Delete test events."""
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    print(f"Deleting {len(event_ids)} test events...")

    for event_id in event_ids:
        try:
            service.events().delete(
                calendarId=work_calendar_id,
                eventId=event_id
            ).execute()
            print(f"  ✅ Deleted: {event_id}")
        except Exception as e:
            print(f"  ❌ Error deleting {event_id}: {e}")


if __name__ == '__main__':
    main()
