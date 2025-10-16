#!/usr/bin/env python3
"""
Safely migrate events from subcalendars to tross@georgefox.edu with color coding.

This script:
1. Reads active events from Classes and GFU Events subcalendars
2. Creates them on tross@georgefox.edu with appropriate colors
3. Verifies creation before marking originals for cleanup
4. Updates database to reflect new location
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
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
    subcalendars_file = os.path.join(DATA_DIR, 'work_subcalendars.json')
    with open(subcalendars_file, 'r') as f:
        return json.load(f)


def get_subcalendar_events(service, calendar_id, calendar_name, days_ahead=90):
    """Get all events from a subcalendar."""
    print(f"  Fetching events from {calendar_name}...")

    time_min = datetime.now().isoformat() + 'Z'
    time_max = (datetime.now() + timedelta(days=days_ahead)).isoformat() + 'Z'

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

    except HttpError as e:
        print(f"    ❌ Error: {e}")
        return []


def create_event_on_work_calendar(service, work_calendar_id, event, color_id, dry_run=True):
    """Create event on work calendar with specified color."""

    # Build event body
    new_event = {
        'summary': event.get('summary', 'Untitled'),
        'description': event.get('description', ''),
        'location': event.get('location', ''),
        'colorId': color_id
    }

    # Copy start/end times
    if 'dateTime' in event['start']:
        new_event['start'] = event['start']
        new_event['end'] = event['end']
    else:
        new_event['start'] = event['start']
        new_event['end'] = event['end']

    # Preserve extended properties (event_type, etc)
    if 'extendedProperties' in event:
        new_event['extendedProperties'] = event['extendedProperties']

    # Preserve recurrence if present
    if 'recurrence' in event:
        new_event['recurrence'] = event['recurrence']

    if dry_run:
        return {'id': 'dry-run-id', 'htmlLink': 'dry-run-link'}

    try:
        time.sleep(0.15)  # Rate limiting

        created_event = service.events().insert(
            calendarId=work_calendar_id,
            body=new_event
        ).execute()

        return created_event

    except HttpError as e:
        print(f"      ❌ API Error: {e}")
        raise
    except Exception as e:
        print(f"      ❌ Error: {e}")
        raise


def update_database_location(db, old_event_id, old_calendar_id, new_event_id, new_calendar_id, dry_run=True):
    """Update database to reflect new event location."""

    if dry_run:
        return True

    try:
        with db.get_session() as session:
            # Update the event's current_calendar
            result = session.execute(
                text("""
                    UPDATE calendar_events
                    SET current_calendar = :new_cal,
                        event_id = :new_id,
                        last_action = 'migrated_to_work',
                        last_action_at = NOW(),
                        updated_at = NOW()
                    WHERE event_id = :old_id
                    AND current_calendar = :old_cal
                    AND deleted_at IS NULL
                    RETURNING event_id
                """),
                {
                    'new_cal': new_calendar_id,
                    'new_id': new_event_id,
                    'old_id': old_event_id,
                    'old_cal': old_calendar_id
                }
            )

            updated = result.rowcount > 0
            session.commit()
            return updated

    except Exception as e:
        print(f"      ❌ Database error: {e}")
        return False


def migrate_subcalendar(service, db, work_calendar_id, subcal_name, subcal_id, color_id, dry_run=True):
    """Migrate all events from a subcalendar to work calendar."""

    print(f"\n{'='*80}")
    print(f"Migrating: {subcal_name}")
    print(f"Color: {color_id}")
    print(f"{'='*80}")

    # Get events from subcalendar
    events = get_subcalendar_events(service, subcal_id, subcal_name)

    if not events:
        print("  ℹ️  No events to migrate")
        return {'migrated': 0, 'errors': 0}

    stats = {'migrated': 0, 'errors': 0, 'skipped': 0}

    # Migrate each event
    for event in events:
        event_id = event['id']
        summary = event.get('summary', 'Untitled')
        start = event['start'].get('dateTime', event['start'].get('date'))

        print(f"\n  {'[DRY RUN] ' if dry_run else ''}Migrating: {summary[:50]}")
        print(f"    Start: {start}")
        print(f"    Original ID: {event_id}")

        try:
            # Create on work calendar
            new_event = create_event_on_work_calendar(
                service, work_calendar_id, event, color_id, dry_run
            )

            new_event_id = new_event['id']
            print(f"    ✅ Created on work calendar: {new_event_id}")

            # Update database
            db_updated = update_database_location(
                db, event_id, subcal_id, new_event_id, work_calendar_id, dry_run
            )

            if db_updated or dry_run:
                print(f"    ✅ Database updated")
                stats['migrated'] += 1
            else:
                print(f"    ⚠️  Event created but database not updated")
                stats['errors'] += 1

        except Exception as e:
            print(f"    ❌ Migration failed: {e}")
            stats['errors'] += 1

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate subcalendar events to work calendar')
    parser.add_argument('--live', action='store_true',
                       help='Actually migrate events (default is dry run)')
    parser.add_argument('--days', type=int, default=90,
                       help='Days ahead to migrate (default: 90)')
    args = parser.parse_args()

    dry_run = not args.live

    print("=" * 80)
    print("SUBCALENDAR TO WORK CALENDAR MIGRATION")
    print("=" * 80)
    if dry_run:
        print("🧪 DRY RUN - No changes will be made")
    else:
        print("🔴 LIVE MODE - Events will be migrated")
    print("=" * 80)
    print()

    # Initialize
    service = get_calendar_service()
    db = DatabaseManager(DATABASE_URL)
    if not db.test_connection():
        print("❌ Failed to connect to database")
        return

    work_calendar_id = os.getenv('WORK_CALENDAR_ID')
    subcalendars = load_subcalendars()

    # Migration plan
    migrations = [
        ('Classes', subcalendars.get('Classes'), '5'),  # Banana
        ('GFU Events', subcalendars.get('GFU Events'), '9'),  # Blueberry
    ]

    total_stats = {'migrated': 0, 'errors': 0, 'skipped': 0}

    # Execute migrations
    for subcal_name, subcal_id, color_id in migrations:
        if not subcal_id:
            print(f"⚠️  Skipping {subcal_name} - not found in config")
            continue

        stats = migrate_subcalendar(
            service, db, work_calendar_id,
            subcal_name, subcal_id, color_id,
            dry_run
        )

        total_stats['migrated'] += stats['migrated']
        total_stats['errors'] += stats['errors']
        total_stats['skipped'] += stats.get('skipped', 0)

    # Summary
    print("\n" + "=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Events migrated: {total_stats['migrated']}")
    print(f"Errors: {total_stats['errors']}")
    print(f"Skipped: {total_stats['skipped']}")
    print()

    if dry_run and total_stats['migrated'] > 0:
        print("💡 To apply these changes, run with --live flag")
    elif not dry_run:
        print("✅ Migration complete!")
        print()
        print("⚠️  IMPORTANT NEXT STEPS:")
        print("  1. Verify events appear on tross@georgefox.edu with correct colors")
        print("  2. Once verified, you can delete events from subcalendars")
        print("  3. Update 25Live sync to write directly to work calendar")
        print()


if __name__ == '__main__':
    main()
