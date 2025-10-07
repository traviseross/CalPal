#!/usr/bin/env python3
"""
Interactive Event Blacklist Manager

Manage the list of 25Live events you don't want to sync to your calendars.
Supports exact matches and regex patterns.
"""

import json
import os
import re
import sys
from typing import Dict, List, Set

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATA_DIR, DATABASE_URL
from src.db_manager import DatabaseManager


class BlacklistManager:
    """Manage event blacklist with interactive menu."""

    def __init__(self):
        self.blacklist_file = os.path.join(DATA_DIR, 'event_blacklist.json')
        self.db = DatabaseManager(DATABASE_URL)
        self.load_blacklist()

    def load_blacklist(self):
        """Load current blacklist from file."""
        try:
            with open(self.blacklist_file, 'r') as f:
                self.data = json.load(f)
            self.blacklisted_events = set(self.data.get('blacklisted_events', []))
            self.blacklist_patterns = self.data.get('blacklist_patterns', [])
        except FileNotFoundError:
            print("⚠️  No blacklist file found. Creating new one.")
            self.data = {
                "description": "Events to exclude from CalPal calendars",
                "blacklisted_events": [],
                "blacklist_patterns": []
            }
            self.blacklisted_events = set()
            self.blacklist_patterns = []

    def save_blacklist(self):
        """Save blacklist to file."""
        self.data['blacklisted_events'] = sorted(list(self.blacklisted_events))
        self.data['blacklist_patterns'] = self.blacklist_patterns

        with open(self.blacklist_file, 'w') as f:
            json.dump(self.data, f, indent=2)
        print(f"✅ Blacklist saved to {self.blacklist_file}")

    def display_blacklist(self):
        """Display current blacklist entries."""
        print("\n" + "="*70)
        print("📋 CURRENT BLACKLIST")
        print("="*70)

        if not self.blacklisted_events and not self.blacklist_patterns:
            print("  (empty)")
        else:
            if self.blacklisted_events:
                print("\n🎯 Exact Matches:")
                for i, event in enumerate(sorted(self.blacklisted_events), 1):
                    print(f"  {i}. {event}")

            if self.blacklist_patterns:
                print("\n🔍 Regex Patterns:")
                for i, pattern in enumerate(self.blacklist_patterns, 1):
                    print(f"  {i}. {pattern}")

        print("="*70 + "\n")

    def add_exact_match(self):
        """Add an exact match entry."""
        print("\n➕ ADD EXACT MATCH")
        print("Enter the exact event name to block (or 'cancel' to go back):")
        event_name = input("> ").strip()

        if event_name.lower() == 'cancel':
            return

        if not event_name:
            print("❌ Event name cannot be empty")
            return

        if event_name in self.blacklisted_events:
            print(f"⚠️  '{event_name}' is already in the blacklist")
        else:
            self.blacklisted_events.add(event_name)
            print(f"✅ Added '{event_name}' to blacklist")

    def add_pattern(self):
        """Add a regex pattern entry."""
        print("\n➕ ADD REGEX PATTERN")
        print("Enter a regex pattern (or 'cancel' to go back):")
        print("Examples:")
        print("  ^Chapel    - matches events starting with 'Chapel'")
        print("  Committee$ - matches events ending with 'Committee'")
        print("  BOT.*      - matches events containing 'BOT'")
        pattern = input("> ").strip()

        if pattern.lower() == 'cancel':
            return

        if not pattern:
            print("❌ Pattern cannot be empty")
            return

        # Test if it's a valid regex
        try:
            re.compile(pattern)
        except re.error as e:
            print(f"❌ Invalid regex pattern: {e}")
            return

        if pattern in self.blacklist_patterns:
            print(f"⚠️  Pattern '{pattern}' is already in the blacklist")
        else:
            self.blacklist_patterns.append(pattern)
            print(f"✅ Added pattern '{pattern}' to blacklist")

    def remove_entry(self):
        """Remove an entry from the blacklist."""
        if not self.blacklisted_events and not self.blacklist_patterns:
            print("❌ Blacklist is empty, nothing to remove")
            return

        print("\n➖ REMOVE ENTRY")
        print("\nSelect entry to remove:")

        all_entries = []
        index = 1

        # List exact matches
        for event in sorted(self.blacklisted_events):
            print(f"  {index}. [Exact] {event}")
            all_entries.append(('exact', event))
            index += 1

        # List patterns
        for pattern in self.blacklist_patterns:
            print(f"  {index}. [Pattern] {pattern}")
            all_entries.append(('pattern', pattern))
            index += 1

        print(f"\nEnter number (1-{len(all_entries)}) or 'cancel':")
        choice = input("> ").strip()

        if choice.lower() == 'cancel':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_entries):
                entry_type, entry_value = all_entries[idx]
                if entry_type == 'exact':
                    self.blacklisted_events.remove(entry_value)
                else:
                    self.blacklist_patterns.remove(entry_value)
                print(f"✅ Removed '{entry_value}' from blacklist")
            else:
                print("❌ Invalid selection")
        except ValueError:
            print("❌ Invalid input")

    def get_matching_events(self) -> List[Dict]:
        """Get all events in database that match current blacklist."""
        if not self.db.test_connection():
            print("❌ Failed to connect to database")
            return []

        # Get all 25Live events
        query = """
            SELECT event_id, summary, current_calendar, deleted_at,
                   metadata->>'25live_reservation_id' as reservation_id
            FROM calendar_events
            WHERE metadata->>'25live_reservation_id' IS NOT NULL
            ORDER BY summary
        """

        try:
            from sqlalchemy import text

            with self.db.get_session() as session:
                results = session.execute(text(query)).all()

                if not results:
                    return []

                # Filter to only matching events
                matching = []
                compiled_patterns = [re.compile(p) for p in self.blacklist_patterns]

                for row in results:
                    summary = row[1] or ""
                    is_deleted = row[3] is not None

                    # Check if blacklisted
                    is_blacklisted = False
                    if summary in self.blacklisted_events:
                        is_blacklisted = True
                    else:
                        for pattern in compiled_patterns:
                            if pattern.search(summary):
                                is_blacklisted = True
                                break

                    if is_blacklisted:
                        matching.append({
                            'event_id': row[0],
                            'summary': summary,
                            'calendar': row[2],
                            'is_deleted': is_deleted,
                            'reservation_id': row[4]
                        })

                return matching
        except Exception as e:
            print(f"❌ Error querying database: {e}")
            return []

    def show_matching_events(self):
        """Show existing events that match the blacklist."""
        print("\n🔍 Checking database for matching events...")
        matching = self.get_matching_events()

        if not matching:
            print("✅ No events in database match the current blacklist")
            return

        active = [e for e in matching if not e['is_deleted']]
        deleted = [e for e in matching if e['is_deleted']]

        print(f"\n📊 Found {len(matching)} matching events:")
        print(f"   Active: {len(active)}")
        print(f"   Already deleted: {len(deleted)}")

        if active:
            print("\n🔴 Active matching events (first 20):")
            for event in active[:20]:
                print(f"   • {event['summary']} ({event['calendar']})")
            if len(active) > 20:
                print(f"   ... and {len(active) - 20} more")

    def cleanup_matching_events(self):
        """Mark matching events as deleted in database."""
        matching = self.get_matching_events()
        active = [e for e in matching if not e['is_deleted']]

        if not active:
            print("✅ No active events to clean up")
            return

        print(f"\n⚠️  Found {len(active)} active events matching the blacklist")
        print("\nThis will mark them as deleted in the database.")
        print("They will be removed from Google Calendar on next sync.")
        print("\nProceed? (yes/no):")

        confirm = input("> ").strip().lower()
        if confirm != 'yes':
            print("❌ Cancelled")
            return

        # Mark events as deleted
        try:
            from sqlalchemy import text

            deleted_count = 0
            with self.db.get_session() as session:
                for event in active:
                    query = """
                        UPDATE calendar_events
                        SET deleted_at = NOW(),
                            status = 'deleted',
                            last_action = 'blacklisted',
                            last_action_at = NOW()
                        WHERE event_id = :event_id AND current_calendar = :calendar
                    """
                    session.execute(text(query), {
                        'event_id': event['event_id'],
                        'calendar': event['calendar']
                    })
                    deleted_count += 1

            print(f"✅ Marked {deleted_count} events as deleted")
            print("💡 Run the sync to remove them from Google Calendar")
        except Exception as e:
            print(f"❌ Error updating database: {e}")

    def run(self):
        """Run the interactive menu."""
        while True:
            self.display_blacklist()

            print("📋 MENU")
            print("1. Add exact match")
            print("2. Add regex pattern")
            print("3. Remove entry")
            print("4. Show matching events in database")
            print("5. Clean up matching events")
            print("6. Save and exit")
            print("7. Exit without saving")
            print("\nSelect option (1-7):")

            choice = input("> ").strip()

            if choice == '1':
                self.add_exact_match()
            elif choice == '2':
                self.add_pattern()
            elif choice == '3':
                self.remove_entry()
            elif choice == '4':
                self.show_matching_events()
            elif choice == '5':
                self.cleanup_matching_events()
            elif choice == '6':
                self.save_blacklist()
                print("👋 Goodbye!")
                break
            elif choice == '7':
                print("❌ Exiting without saving")
                break
            else:
                print("❌ Invalid choice")


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("🚫 EVENT BLACKLIST MANAGER")
    print("="*70)
    print("\nManage events you don't want synced from 25Live\n")

    try:
        manager = BlacklistManager()
        manager.run()
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
