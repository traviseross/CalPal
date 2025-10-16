#!/usr/bin/env python3
"""
Remove duplicate events created by migration script.

Keeps: Events with event_type='25live_class' or '25live_event' (from 25Live sync)
Removes: Events with event_type='unknown' (from migration script)
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from collections import defaultdict
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


def find_migration_duplicates(events):
    """Find events that were created by migration and have 25Live duplicates."""

    # Group by (summary, start_time)
    event_groups = defaultdict(list)

    for event in events:
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))
        key = (summary, start)
        event_groups[key].append(event)

    # Find duplicates where one is from migration (unknown) and one is from 25Live
    to_delete = []

    for key, events_list in event_groups.items():
        if len(events_list) <= 1:
            continue

        # Categorize events
        migration_events = []
        twentyfive_live_events = []

        for event in events_list:
            ext_props = event.get('extendedProperties', {}).get('private', {})
            event_type = ext_props.get('event_type', '')
            source = ext_props.get('source', '')

            # Migration events: source=25live but event_type is empty/unknown
            # 25Live sync events: source=25live and event_type is 25live_class/25live_event
            if source == '25live':
                if event_type in ('25live_class', '25live_event'):
                    twentyfive_live_events.append(event)
                else:
                    migration_events.append(event)

        # If we have both migration and 25Live versions, delete migration ones
        if migration_events and twentyfive_live_events:
            to_delete.extend(migration_events)

    return to_delete


def delete_events(service, db, calendar_id, events_to_delete, dry_run=True):
    """Delete events from Google Calendar and mark in database."""

    print(f"\n{'=' * 80}")
    if dry_run:
        print("DRY RUN - Would delete these events:")
    else:
        print("LIVE MODE - Deleting events:")
    print(f"{'=' * 80}\n")

    stats = {'deleted': 0, 'errors': 0, 'db_updated': 0}

    for i, event in enumerate(events_to_delete, 1):
        event_id = event['id']
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))

        print(f"{i}. {summary[:60]}")
        print(f"   Start: {start}")
        print(f"   Event ID: {event_id}")

        if not dry_run:
            try:
                time.sleep(0.1)  # Rate limiting

                # Delete from Google Calendar
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=event_id
                ).execute()

                print(f"   ✅ Deleted from Google Calendar")
                stats['deleted'] += 1

                # Mark as deleted in database
                try:
                    with db.get_session() as session:
                        result = session.execute(
                            text("""
                                UPDATE calendar_events
                                SET deleted_at = NOW(),
                                    status = 'deleted',
                                    last_action = 'removed_migration_duplicate',
                                    last_action_at = NOW()
                                WHERE event_id = :event_id
                                AND current_calendar = :calendar_id
                            """),
                            {
                                'event_id': event_id,
                                'calendar_id': calendar_id
                            }
                        )
                        session.commit()

                        if result.rowcount > 0:
                            stats['db_updated'] += 1
                            print(f"   ✅ Marked deleted in database")
                        else:
                            print(f"   ⚠️  Not found in database (may be OK)")

                except Exception as e:
                    print(f"   ⚠️  Database error: {e}")

            except HttpError as e:
                if e.resp.status in [404, 410]:
                    print(f"   ℹ️  Already deleted from Google Calendar")
                    stats['deleted'] += 1
                else:
                    print(f"   ❌ Error deleting: {e}")
                    stats['errors'] += 1
            except Exception as e:
                print(f"   ❌ Unexpected error: {e}")
                stats['errors'] += 1

        print()

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Remove migration duplicate events')
    parser.add_argument('--live', action='store_true',
                       help='Actually delete events (default is dry run)')
    args = parser.parse_args()

    dry_run = not args.live

    print("\n" + "=" * 80)
    print("MIGRATION DUPLICATE REMOVAL")
    print("=" * 80)
    if dry_run:
        print("🧪 DRY RUN - No changes will be made")
    else:
        print("🔴 LIVE MODE - Will delete duplicate events")
    print("=" * 80)
    print()

    # Initialize
    service = get_calendar_service()
    db = DatabaseManager(DATABASE_URL)
    if not db.test_connection():
        print("❌ Failed to connect to database")
        return

    work_calendar_id = os.getenv('WORK_CALENDAR_ID')

    # Get events
    events = get_calendar_events(service, work_calendar_id)

    # Find duplicates to delete
    print("\nAnalyzing duplicates...")
    events_to_delete = find_migration_duplicates(events)

    print(f"\nFound {len(events_to_delete)} migration duplicates to remove")

    if not events_to_delete:
        print("✅ No duplicates to remove!")
        return

    # Delete events
    stats = delete_events(service, db, work_calendar_id, events_to_delete, dry_run)

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Events to delete: {len(events_to_delete)}")
    if not dry_run:
        print(f"Deleted from Google Calendar: {stats['deleted']}")
        print(f"Marked deleted in database: {stats['db_updated']}")
        print(f"Errors: {stats['errors']}")
    print()

    if dry_run:
        print("💡 To apply these changes, run with --live flag")
    else:
        print("✅ Cleanup complete!")


if __name__ == '__main__':
    main()
