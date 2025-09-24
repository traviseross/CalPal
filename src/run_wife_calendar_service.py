#!/usr/bin/env python3
"""
Continuous Wife Calendar ICS Service

Runs continuously to keep the wife calendar ICS file updated.
Can be run as a daemon or scheduled service.
"""

import time
import logging
import argparse
import signal
import sys
from datetime import datetime
try:
    from wife_calendar_ics_service import WifeCalendarICSService
except ImportError:
    # If running from different directory, add current directory to path
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wife_calendar_ics_service import WifeCalendarICSService

class ContinuousWifeCalendarService:
    """Continuously update wife calendar ICS file."""

    def __init__(self, update_interval_minutes: int = 15):
        self.update_interval = update_interval_minutes * 60  # Convert to seconds
        self.running = True
        self.logger = logging.getLogger('continuous-wife-calendar')

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run_continuous(self):
        """Run the service continuously."""
        self.logger.info(f"🔄 Starting continuous wife calendar service...")
        self.logger.info(f"Update interval: {self.update_interval // 60} minutes")

        service = WifeCalendarICSService()

        while self.running:
            try:
                self.logger.info("📅 Updating wife calendar ICS file...")
                start_time = datetime.now()

                # Generate updated ICS file
                metadata = service.run_generation()

                duration = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"✅ Update completed in {duration:.1f}s - {metadata['events_count']} events")

                # Wait for next update
                if self.running:
                    self.logger.info(f"💤 Sleeping for {self.update_interval // 60} minutes...")
                    time.sleep(self.update_interval)

            except Exception as e:
                self.logger.error(f"❌ Error during update: {e}")
                if self.running:
                    self.logger.info("⏳ Waiting 5 minutes before retry...")
                    time.sleep(300)  # Wait 5 minutes before retry

        self.logger.info("👋 Service stopped")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Continuous wife calendar ICS service')
    parser.add_argument('--interval', type=int, default=15,
                       help='Update interval in minutes (default: 15)')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit (not continuous)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Set logging level')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.once:
        # Run once and exit
        service = WifeCalendarICSService()
        service.run_generation()
    else:
        # Run continuously
        continuous_service = ContinuousWifeCalendarService(args.interval)
        continuous_service.run_continuous()

if __name__ == '__main__':
    main()