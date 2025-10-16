#!/usr/bin/env python3
"""
Audit database vs Google Calendar to ensure no data loss during migration.

This script checks:
1. Events in database that should be on tross@georgefox.edu
2. Events currently on subcalendars that need to be moved
3. Events that might have been erroneously deleted
"""

import os
import sys
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from calpal.core.db_manager import DatabaseManager

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


def audit_database(db):
    """Check what's in the database."""
    print("=" * 80)
    print("DATABASE AUDIT")
    print("=" * 80)

    with db.get_session() as session:
        # Get counts by calendar and status
        result = session.execute(text("""
            SELECT
                current_calendar,
                event_type,
                COUNT(*) FILTER (WHERE deleted_at IS NULL) as active_count,
                COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted_count
            FROM calendar_events
            WHERE start_time >= NOW() - INTERVAL '7 days'
            AND start_time <= NOW() + INTERVAL '30 days'
            GROUP BY current_calendar, event_type
            ORDER BY current_calendar, event_type
        """)).mappings().all()

        print("\nEvents by calendar and type (past 7 days to next 30 days):")
        print("-" * 80)

        current_cal = None
        for row in result:
            cal = row['current_calendar']
            if cal != current_cal:
                if current_cal is not None:
                    print()
                print(f"\n{cal}:")
                current_cal = cal

            print(f"  {row['event_type']:30} Active: {row['active_count']:4} | Deleted: {row['deleted_count']:4}")

        # Check for events that should be on tross but might be missing
        work_calendar_id = os.getenv('WORK_CALENDAR_ID')

        print("\n" + "=" * 80)
        print("EVENTS THAT SHOULD BE ON TROSS@GEORGEFOX.EDU")
        print("=" * 80)

        # 25Live classes
        classes = session.execute(text("""
            SELECT event_id, summary, start_time, current_calendar, deleted_at
            FROM calendar_events
            WHERE event_type = '25live_class'
            AND start_time >= NOW()
            AND start_time <= NOW() + INTERVAL '30 days'
            ORDER BY deleted_at NULLS FIRST, start_time
            LIMIT 10
        """)).mappings().all()

        print(f"\n25Live Classes (showing first 10):")
        print("-" * 80)
        for row in classes:
            status = "❌ DELETED" if row['deleted_at'] else "✅ ACTIVE"
            on_work = "📍 on tross" if row['current_calendar'] == work_calendar_id else f"📍 on {row['current_calendar'][:20]}..."
            print(f"{status} | {on_work} | {row['start_time'].strftime('%m/%d %H:%M')} | {row['summary'][:50]}")

        # 25Live events
        events = session.execute(text("""
            SELECT event_id, summary, start_time, current_calendar, deleted_at
            FROM calendar_events
            WHERE event_type = '25live_event'
            AND start_time >= NOW()
            AND start_time <= NOW() + INTERVAL '30 days'
            ORDER BY deleted_at NULLS FIRST, start_time
            LIMIT 10
        """)).mappings().all()

        print(f"\n25Live Events (showing first 10):")
        print("-" * 80)
        for row in events:
            status = "❌ DELETED" if row['deleted_at'] else "✅ ACTIVE"
            on_work = "📍 on tross" if row['current_calendar'] == work_calendar_id else f"📍 on {row['current_calendar'][:20]}..."
            print(f"{status} | {on_work} | {row['start_time'].strftime('%m/%d %H:%M')} | {row['summary'][:50]}")

        return {
            'classes': classes,
            'events': events
        }


def audit_google_calendar(service, calendar_id, calendar_name):
    """Check what's actually on a Google Calendar."""
    print(f"\n{'=' * 80}")
    print(f"GOOGLE CALENDAR AUDIT: {calendar_name}")
    print("=" * 80)

    time_min = (datetime.now() - timedelta(days=7)).isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=30)).isoformat() + 'Z'

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

        print(f"\nTotal events: {len(events)}")

        # Group by type
        by_type = {}
        for event in events:
            extended_props = event.get('extendedProperties', {})
            private = extended_props.get('private', {})
            event_type = private.get('event_type', 'unknown')

            if event_type not in by_type:
                by_type[event_type] = []
            by_type[event_type].append(event)

        print("\nEvents by type:")
        print("-" * 80)
        for event_type, events_list in sorted(by_type.items()):
            print(f"  {event_type:30} Count: {len(events_list)}")

        return events

    except Exception as e:
        print(f"❌ Error fetching from {calendar_name}: {e}")
        return []


def check_data_safety(db, service, subcalendars):
    """Check for potential data loss scenarios."""
    print("\n" + "=" * 80)
    print("DATA SAFETY CHECKS")
    print("=" * 80)

    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    with db.get_session() as session:
        # Check: Active events in DB but marked on subcalendars
        print("\n⚠️  Active events currently on subcalendars (need migration):")
        print("-" * 80)

        for subcal_name, subcal_id in subcalendars.items():
            if subcal_name in ['Personal Events', 'Family Events']:
                continue  # Skip non-work subcalendars

            result = session.execute(text("""
                SELECT COUNT(*) as count
                FROM calendar_events
                WHERE current_calendar = :subcal_id
                AND deleted_at IS NULL
                AND start_time >= NOW()
            """), {'subcal_id': subcal_id}).scalar()

            if result > 0:
                print(f"  {subcal_name:20} {result:4} active events")

        # Check: Events deleted from work calendar but still on subcalendars
        print("\n⚠️  Events deleted from tross@ but possibly still on subcalendars:")
        print("-" * 80)

        orphaned = session.execute(text("""
            SELECT
                current_calendar,
                COUNT(*) as count
            FROM calendar_events
            WHERE deleted_at IS NOT NULL
            AND start_time >= NOW()
            AND current_calendar != :work_cal
            GROUP BY current_calendar
        """), {'work_cal': work_calendar_id}).mappings().all()

        for row in orphaned:
            print(f"  {row['current_calendar'][:30]:30} {row['count']:4} deleted events")

        # Check: 25Live events that should be on tross but aren't
        print("\n⚠️  Active 25Live events NOT on tross@georgefox.edu:")
        print("-" * 80)

        misplaced = session.execute(text("""
            SELECT event_id, summary, start_time, current_calendar, event_type
            FROM calendar_events
            WHERE event_type IN ('25live_class', '25live_event')
            AND deleted_at IS NULL
            AND current_calendar != :work_cal
            AND start_time >= NOW()
            AND start_time <= NOW() + INTERVAL '30 days'
            ORDER BY start_time
            LIMIT 20
        """), {'work_cal': work_calendar_id}).mappings().all()

        print(f"Found {len(misplaced)} events:")
        for row in misplaced:
            print(f"  {row['start_time'].strftime('%m/%d %H:%M')} | {row['event_type']:15} | {row['summary'][:40]}")
            print(f"    Currently on: {row['current_calendar'][:60]}")


def main():
    print("\n" + "=" * 80)
    print("DATA SAFETY AUDIT - PRE-MIGRATION CHECK")
    print("=" * 80)
    print("\nThis audit checks for potential data loss before simplification.")
    print("=" * 80)

    # Initialize
    db = DatabaseManager(DATABASE_URL)
    if not db.test_connection():
        print("❌ Failed to connect to database")
        return

    service = get_calendar_service()
    subcalendars = load_subcalendars()
    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    # Run audits
    db_data = audit_database(db)

    # Check work calendar
    work_events = audit_google_calendar(service, work_calendar_id, "tross@georgefox.edu")

    # Check subcalendars
    for subcal_name in ['Classes', 'GFU Events', 'Appointments', 'Meetings']:
        if subcal_name in subcalendars:
            subcal_events = audit_google_calendar(service, subcalendars[subcal_name], subcal_name)

    # Safety checks
    check_data_safety(db, service, subcalendars)

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)
    print("\n⚠️  Review the output above before proceeding with migration!")
    print("=" * 80)


if __name__ == '__main__':
    main()
