#!/usr/bin/env python3
"""
Check all events on Work calendar in the next week.
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

    # Check for events in next 7 days
    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=7)).isoformat() + 'Z'

    print(f"Looking for events from now through next week")
    print()

    events_result = service.events().list(
        calendarId=work_calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime',
        maxResults=50
    ).execute()

    events = events_result.get('items', [])

    print(f"Found {len(events)} events:")
    print()

    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'Untitled')
        event_id = event['id']
        color_id = event.get('colorId', 'default')
        print(f"  • {start} - {summary}")
        print(f"    ID: {event_id}, Color: {color_id}")

if __name__ == '__main__':
    main()
