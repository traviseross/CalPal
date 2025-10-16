#!/usr/bin/env python3
"""
Simplified CalPal Service - Transition Mode

During transition to single-calendar architecture:
- Run 25Live sync (creates events on tross@georgefox.edu with colors)
- Run ICS generator (creates wife calendar)
- Skip all mirroring and reconciliation
- Don't delete anything from old subcalendars

This is a safe "additive only" mode while we transition.
"""

import logging
import signal
import sys
import os
import time
from datetime import datetime
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from calpal.sync.twentyfive_live_sync import DBAware25LiveSync
from calpal.generators.ics_generator import DBWifeICSGenerator


class SimplifiedCalPalService:
    """Simplified service that only adds events, never deletes."""

    def __init__(self):
        self.logger = logging.getLogger('simplified-calpal')
        self.running = False
        self.cycle_count = 0

        # Component schedules (in minutes)
        self.schedules = {
            '25live_sync': {'interval': 30, 'last_run': None},
            'ics_generator': {'interval': 5, 'last_run': None}
        }

    def should_run(self, component: str) -> bool:
        """Check if component should run based on schedule."""
        schedule = self.schedules.get(component)
        if not schedule:
            return False

        last_run = schedule['last_run']
        interval = schedule['interval']

        if last_run is None:
            return True

        elapsed = (datetime.now() - last_run).total_seconds() / 60
        return elapsed >= interval

    def run_25live_sync(self):
        """Run 25Live sync - creates events on work calendar with colors."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Running 25Live Sync")
            self.logger.info("=" * 60)

            sync = DBAware25LiveSync()
            results = sync.run_full_sync()

            if results.get('success'):
                self.logger.info("✅ 25Live sync completed successfully")
                self.logger.info(f"   Created: {results.get('total_events_created', 0)}")
                self.logger.info(f"   Skipped: {results.get('total_duplicates_skipped', 0)}")
            else:
                self.logger.warning("⚠️  25Live sync completed with issues")

            self.schedules['25live_sync']['last_run'] = datetime.now()

        except Exception as e:
            self.logger.error(f"❌ 25Live sync failed: {e}")
            import traceback
            traceback.print_exc()

    def run_ics_generator(self):
        """Generate wife calendar ICS file."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Running ICS Generator")
            self.logger.info("=" * 60)

            generator = DBWifeICSGenerator()
            metadata = generator.run_generation()

            self.logger.info(f"✅ ICS generated: {metadata.get('events_count', 0)} events")

            self.schedules['ics_generator']['last_run'] = datetime.now()

        except Exception as e:
            self.logger.error(f"❌ ICS generation failed: {e}")
            import traceback
            traceback.print_exc()

    def run_cycle(self):
        """Run one cycle of all scheduled components."""
        self.cycle_count += 1
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"CYCLE {self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)

        # Run 25Live sync if scheduled
        if self.should_run('25live_sync'):
            self.run_25live_sync()

        # Run ICS generator if scheduled
        if self.should_run('ics_generator'):
            self.run_ics_generator()

        self.logger.info("")
        self.logger.info(f"✅ Cycle {self.cycle_count} complete")
        self.logger.info("=" * 60)

    def run(self):
        """Run service continuously."""
        self.running = True
        self.logger.info("🚀 Simplified CalPal Service started")
        self.logger.info("   Mode: TRANSITION (additive only, no deletions)")
        self.logger.info("")

        while self.running:
            try:
                self.run_cycle()

                # Sleep for 1 minute between checks
                self.logger.info("💤 Sleeping 60 seconds...")
                time.sleep(60)

            except KeyboardInterrupt:
                self.logger.info("⚠️  Interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in main loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)

        self.logger.info("👋 Service stopped")

    def shutdown(self, signum, frame):
        """Graceful shutdown handler."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Simplified CalPal Service (Transition Mode)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--run-once', action='store_true',
                       help='Run one cycle then exit')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("🎯 SIMPLIFIED CALPAL SERVICE (TRANSITION MODE)")
    print("=" * 60)
    print("Active components:")
    print("  ✅ 25Live Sync → tross@georgefox.edu (with colors)")
    print("  ✅ ICS Generator → wife calendar")
    print("")
    print("Disabled (during transition):")
    print("  ❌ Subcalendar mirroring")
    print("  ❌ Reconciliation")
    print("  ❌ Event deletion")
    print("=" * 60)
    print()

    service = SimplifiedCalPalService()

    # Register signal handlers
    signal.signal(signal.SIGTERM, service.shutdown)
    signal.signal(signal.SIGINT, service.shutdown)

    if args.run_once:
        print("Running single cycle...\n")
        service.run_cycle()
        print("\n✅ Single cycle complete!")
    else:
        service.run()


if __name__ == '__main__':
    main()
