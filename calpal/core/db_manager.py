#!/usr/bin/env python3
"""
CalPal Database Manager

Handles all database operations for tracking calendar events
across CalPal's managed calendars.
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import logging

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class DatabaseManager:
    """Manages database connections and queries for CalPal event tracking."""

    def __init__(self, connection_string: str = None):
        self.logger = logging.getLogger('db-manager')

        # Default connection string from environment variable
        # Set DATABASE_URL environment variable or pass connection_string parameter
        if connection_string is None:
            connection_string = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/calpal')

        self.connection_string = connection_string

        # Create engine with connection pooling
        self.engine = create_engine(
            self.connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using
            echo=False  # Set to True for SQL debugging
        )

        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)

        self.logger.info("✅ Database manager initialized")

    @contextmanager
    def get_session(self):
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    @contextmanager
    def advisory_lock(self, key: str):
        """
        Acquire PostgreSQL advisory lock for the duration of the context.
        Prevents concurrent execution of critical sections.
        """
        # Convert key to 32-bit integer for PostgreSQL
        lock_id = hash(key) % (2**31 - 1)

        session = self.SessionLocal()
        try:
            # Acquire lock (blocks until available)
            session.execute(text("SELECT pg_advisory_lock(:lock_id)"),
                          {"lock_id": lock_id})
            self.logger.debug(f"Acquired advisory lock: {key} (ID: {lock_id})")

            yield

            # Release lock
            session.execute(text("SELECT pg_advisory_unlock(:lock_id)"),
                          {"lock_id": lock_id})
            self.logger.debug(f"Released advisory lock: {key} (ID: {lock_id})")

            session.commit()
        except Exception as e:
            self.logger.error(f"Error with advisory lock {key}: {e}")
            session.rollback()
            raise
        finally:
            session.close()

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_session() as session:
                result = session.execute(text("SELECT 1")).scalar()
                if result == 1:
                    self.logger.info("✅ Database connection successful")
                    return True
        except Exception as e:
            self.logger.error(f"❌ Database connection failed: {e}")
            return False

    def get_event_by_id(self, event_id: str, calendar_id: str) -> Optional[Dict]:
        """Get a specific event by event_id and calendar_id."""
        try:
            with self.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE event_id = :event_id
                        AND current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        LIMIT 1
                    """),
                    {"event_id": event_id, "calendar_id": calendar_id}
                ).mappings().first()

                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error fetching event {event_id}: {e}")
            return None

    def check_recently_deleted(self, event_id: str, calendar_id: str, hours: int = 1) -> bool:
        """
        Check if an event was recently deleted (within specified hours).
        Checks for deletions on ANY calendar, not just the specified one,
        to prevent re-creation of orphaned mirrors.
        """
        try:
            with self.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT deleted_at FROM calendar_events
                        WHERE event_id = :event_id
                        AND deleted_at IS NOT NULL
                        AND deleted_at > NOW() - INTERVAL :hours HOUR
                        LIMIT 1
                    """),
                    {"event_id": event_id, "hours": hours}
                ).first()

                return result is not None
        except Exception as e:
            self.logger.error(f"Error checking recently deleted for {event_id}: {e}")
            return False

    def get_event_by_25live_id(self, reservation_id: str, calendar_id: str) -> Optional[Dict]:
        """Get a specific event by 25Live reservation ID and calendar_id."""
        try:
            with self.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE metadata->>'25live_reservation_id' = :reservation_id
                        AND current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        LIMIT 1
                    """),
                    {"reservation_id": reservation_id, "calendar_id": calendar_id}
                ).mappings().first()

                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error fetching event by 25Live ID {reservation_id}: {e}")
            return None

    def get_event_by_time_and_summary(self, summary: str, start_time, calendar_id: str) -> Optional[Dict]:
        """Get event by summary + start_time + calendar (fallback duplicate detection for 25Live events without reservation_id)."""
        try:
            with self.get_session() as session:
                result = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE summary = :summary
                        AND start_time = :start_time
                        AND current_calendar = :calendar_id
                        AND deleted_at IS NULL
                        LIMIT 1
                    """),
                    {"summary": summary, "start_time": start_time, "calendar_id": calendar_id}
                ).mappings().first()

                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error checking event by time/summary: {e}")
            return None

    def record_event(self, event_data: Dict) -> bool:
        """Record a new event or update existing one."""
        try:
            with self.get_session() as session:
                # Check if event already exists
                existing = session.execute(
                    text("""
                        SELECT id FROM calendar_events
                        WHERE event_id = :event_id
                        AND current_calendar = :calendar_id
                        AND deleted_at IS NULL
                    """),
                    {
                        "event_id": event_data['event_id'],
                        "calendar_id": event_data['current_calendar']
                    }
                ).scalar()

                if existing:
                    # Update existing event (including event_type to fix misclassifications)
                    session.execute(
                        text("""
                            UPDATE calendar_events
                            SET summary = :summary,
                                description = :description,
                                location = :location,
                                start_time = :start_time,
                                end_time = :end_time,
                                event_type = :event_type,
                                organizer_email = :organizer_email,
                                last_seen_at = NOW(),
                                updated_at = NOW()
                            WHERE id = :id
                        """),
                        {
                            "id": existing,
                            "summary": event_data.get('summary'),
                            "description": event_data.get('description'),
                            "location": event_data.get('location'),
                            "start_time": event_data.get('start_time'),
                            "end_time": event_data.get('end_time'),
                            "event_type": event_data.get('event_type', 'other'),
                            "organizer_email": event_data.get('organizer_email')
                        }
                    )
                    self.logger.debug(f"Updated event {event_data['event_id']}")
                else:
                    # Insert new event
                    import json
                    from sqlalchemy import cast
                    from sqlalchemy.dialects.postgresql import JSONB

                    session.execute(
                        text("""
                            INSERT INTO calendar_events (
                                event_id, ical_uid, summary, description, location,
                                start_time, end_time, source_calendar, current_calendar,
                                event_type, is_attendee_event, organizer_email,
                                creator_email, status, last_action, last_seen_at, metadata
                            ) VALUES (
                                :event_id, :ical_uid, :summary, :description, :location,
                                :start_time, :end_time, :source_calendar, :current_calendar,
                                :event_type, :is_attendee_event, :organizer_email,
                                :creator_email, :status, :last_action, NOW(), CAST(:metadata AS jsonb)
                            )
                        """),
                        {
                            "event_id": event_data['event_id'],
                            "ical_uid": event_data.get('ical_uid'),
                            "summary": event_data.get('summary'),
                            "description": event_data.get('description'),
                            "location": event_data.get('location'),
                            "start_time": event_data.get('start_time'),
                            "end_time": event_data.get('end_time'),
                            "source_calendar": event_data.get('source_calendar'),
                            "current_calendar": event_data.get('current_calendar'),
                            "event_type": event_data.get('event_type', 'other'),
                            "is_attendee_event": event_data.get('is_attendee_event', False),
                            "organizer_email": event_data.get('organizer_email'),
                            "creator_email": event_data.get('creator_email'),
                            "status": event_data.get('status', 'active'),
                            "last_action": event_data.get('last_action', 'created'),
                            "metadata": json.dumps(event_data.get('metadata', {}))
                        }
                    )
                    self.logger.debug(f"Inserted new event {event_data['event_id']}")

                return True
        except Exception as e:
            self.logger.error(f"Error recording event: {e}")
            return False

    def upsert_mirror_event(self, event_data: Dict) -> bool:
        """
        Insert or update a mirror event atomically.

        Uses PostgreSQL's ON CONFLICT to prevent race conditions.
        If a mirror with the same source_event_id + current_calendar exists,
        it updates the existing record instead of creating a duplicate.
        """
        try:
            with self.get_session() as session:
                import json

                # Use ON CONFLICT on the unique partial index
                # ON (metadata->>'source_event_id', current_calendar) WHERE source_event_id IS NOT NULL
                session.execute(
                    text("""
                        INSERT INTO calendar_events (
                            event_id, ical_uid, summary, description, location,
                            start_time, end_time, source_calendar, current_calendar,
                            event_type, is_attendee_event, organizer_email,
                            creator_email, status, last_action, last_seen_at, metadata, is_all_day
                        ) VALUES (
                            :event_id, :ical_uid, :summary, :description, :location,
                            :start_time, :end_time, :source_calendar, :current_calendar,
                            :event_type, :is_attendee_event, :organizer_email,
                            :creator_email, :status, :last_action, NOW(), CAST(:metadata AS jsonb), :is_all_day
                        )
                        ON CONFLICT ((metadata->>'source_event_id'), current_calendar)
                        WHERE metadata->>'source_event_id' IS NOT NULL AND deleted_at IS NULL
                        DO UPDATE SET
                            summary = EXCLUDED.summary,
                            description = EXCLUDED.description,
                            location = EXCLUDED.location,
                            start_time = EXCLUDED.start_time,
                            end_time = EXCLUDED.end_time,
                            last_seen_at = NOW(),
                            updated_at = NOW(),
                            last_action = 'updated'
                        RETURNING id
                    """),
                    {
                        "event_id": event_data['event_id'],
                        "ical_uid": event_data.get('ical_uid'),
                        "summary": event_data.get('summary'),
                        "description": event_data.get('description'),
                        "location": event_data.get('location'),
                        "start_time": event_data.get('start_time'),
                        "end_time": event_data.get('end_time'),
                        "source_calendar": event_data.get('source_calendar'),
                        "current_calendar": event_data.get('current_calendar'),
                        "event_type": event_data.get('event_type', 'other'),
                        "is_attendee_event": event_data.get('is_attendee_event', False),
                        "organizer_email": event_data.get('organizer_email'),
                        "creator_email": event_data.get('creator_email'),
                        "status": event_data.get('status', 'active'),
                        "last_action": event_data.get('last_action', 'created'),
                        "metadata": json.dumps(event_data.get('metadata', {})),
                        "is_all_day": event_data.get('is_all_day', False)
                    }
                ).scalar()

                self.logger.debug(f"Upserted mirror event {event_data['event_id']}")
                return True

        except Exception as e:
            self.logger.error(f"Error upserting mirror event: {e}")
            import traceback
            traceback.print_exc()
            return False

    def mark_as_deleted(self, event_id: str, calendar_id: str) -> bool:
        """Mark an event as deleted."""
        try:
            with self.get_session() as session:
                session.execute(
                    text("""
                        UPDATE calendar_events
                        SET status = 'deleted',
                            deleted_at = NOW(),
                            last_action = 'deleted',
                            last_action_at = NOW()
                        WHERE event_id = :event_id
                        AND current_calendar = :calendar_id
                        AND deleted_at IS NULL
                    """),
                    {"event_id": event_id, "calendar_id": calendar_id}
                )
                return True
        except Exception as e:
            self.logger.error(f"Error marking event as deleted: {e}")
            return False

    def get_events_for_calendar(self, calendar_id: str) -> List[Dict]:
        """Get all active events for a specific calendar."""
        try:
            with self.get_session() as session:
                results = session.execute(
                    text("""
                        SELECT * FROM calendar_events
                        WHERE current_calendar = :calendar_id
                        AND status = 'active'
                        AND deleted_at IS NULL
                        ORDER BY start_time
                    """),
                    {"calendar_id": calendar_id}
                ).mappings().all()

                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error fetching events for calendar: {e}")
            return []

    def get_stats(self) -> Dict:
        """Get database statistics."""
        try:
            with self.get_session() as session:
                stats = {}

                # Total events
                stats['total_events'] = session.execute(
                    text("SELECT COUNT(*) FROM calendar_events WHERE deleted_at IS NULL")
                ).scalar()

                # Events by status
                status_counts = session.execute(
                    text("""
                        SELECT status, COUNT(*) as count
                        FROM calendar_events
                        WHERE deleted_at IS NULL
                        GROUP BY status
                    """)
                ).mappings().all()
                stats['by_status'] = {row['status']: row['count'] for row in status_counts}

                # Events by type
                type_counts = session.execute(
                    text("""
                        SELECT event_type, COUNT(*) as count
                        FROM calendar_events
                        WHERE deleted_at IS NULL
                        GROUP BY event_type
                    """)
                ).mappings().all()
                stats['by_type'] = {row['event_type']: row['count'] for row in type_counts}

                return stats
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}


# Test function
def test_database():
    """Test database connection and basic operations."""
    logging.basicConfig(level=logging.INFO)

    db = DatabaseManager()

    print("Testing database connection...")
    if db.test_connection():
        print("✅ Connection successful!")

        print("\nTesting stats query...")
        stats = db.get_stats()
        print(f"Database stats: {stats}")

        return True
    else:
        print("❌ Connection failed!")
        return False


if __name__ == '__main__':
    test_database()
