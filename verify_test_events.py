#!/usr/bin/env python3
"""
Verify test events exist on Google Calendar.
"""

import os
import sys
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *

def get_calendar_service():
    """Initialize Google Calendar API service."""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=GOOGLE_SCOPES
    )
    return build('calendar', 'v3', credentials=credentials)

def main():
    service = get_calendar_service()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    print(f"Checking calendar: {work_calendar_id}")
    print()

    # Check for events tomorrow
    tomorrow = datetime.now() + timedelta(days=1)
    time_min = tomorrow.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
    time_max = tomorrow.replace(hour=23, minute=59, second=59).isoformat() + 'Z'

    print(f"Looking for events on {tomorrow.strftime('%Y-%m-%d')}")
    print()

    events_result = service.events().list(
        calendarId=work_calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    print(f"Found {len(events)} events tomorrow:")
    print()

    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'Untitled')
        event_id = event['id']
        color_id = event.get('colorId', 'default')
        print(f"  • {start} - {summary}")
        print(f"    ID: {event_id}")
        print(f"    Color: {color_id}")
        print()

if __name__ == '__main__':
    main()
