# 25Live Classes Sync Documentation

## Overview

The 25Live Classes sync system provides automated synchronization between 25Live class scheduling data and Google Calendar. This system is specifically designed for Classes calendar management and includes automatic restoration capabilities.

## System Components

### Core Files
- `twentyfive_live_sync.py` - Main synchronization engine
- `classes_mirrored_events.json` - Tracks all Classes events synced to work calendar
- `25live_sync_results.json` - Contains results from latest sync run

### Calendar Configuration
- **Source**: 25Live Classes calendar data
- **Classes Calendar**: `5e9b1db4268177878d1d06b8eb67a299e753d17d271b4d7301dac593c308b106@group.calendar.google.com`
- **Work Calendar**: `tross@georgefox.edu` (mirrored events destination)

## Classes-Only Sync Usage

### Basic Classes Sync
```bash
# Run full sync (includes Classes + GFU Events)
python3 twentyfive_live_sync.py

# Run with custom start date for Classes
python3 twentyfive_live_sync.py --custom-start 2024-01-01

# Run with debug logging to see Classes processing
python3 twentyfive_live_sync.py --log-level DEBUG
```

### Classes-Specific Features

#### 1. Automatic Restoration
Classes events are protected with automatic restoration:
```bash
# If a Classes event is accidentally deleted from work calendar,
# it will be automatically restored on next sync
python3 twentyfive_live_sync.py
```

#### 2. Duplicate Prevention
Uses 25Live Reservation IDs for reliable duplicate detection:
- Classes use schedule patterns: `MWF 1200-1250 01/13`
- System prevents duplicate creation even with content changes

#### 3. Event Mirroring
Classes events are mirrored to work calendar with:
- Original summary preserved
- Schedule information in description
- Location data maintained
- 25Live profile information included

## Programming Interface

### Initialize Sync Service
```python
from twentyfive_live_sync import TwentyFiveLiveSync

# Initialize the sync service
sync_service = TwentyFiveLiveSync()

# Access Classes calendar ID
classes_calendar_id = sync_service.calendars.get('Classes')
```

### Sync Classes Only (Programmatic)
```python
# Run Classes calendar synchronization
result = sync_service.sync_calendar_type(
    calendar_type='Classes',
    custom_start_date='2024-01-01',  # Optional
    backfill_mode=False  # Optional
)

print(f"Classes sync result: {result}")
```

### Access Classes Tracking Data
```python
# Load Classes tracking data
import json

with open('/home/tradmin/CalPal/classes_mirrored_events.json', 'r') as f:
    classes_events = json.load(f)

# Each event is keyed by Reservation ID and contains:
for reservation_id, event_data in classes_events.items():
    print(f"Reservation ID: {reservation_id}")
    print(f"Classes Event ID: {event_data['classes_event_id']}")
    print(f"Work Event ID: {event_data['work_event_id']}")
    print(f"Summary: {event_data['summary']}")
    print(f"Synced to Work: {event_data['synced_to_work']}")
    print("---")
```

### Extract 25Live Reservation ID
```python
# Extract Reservation ID from Classes event
reservation_id = sync_service._extract_25live_reservation_id(event_data)

# Classes events use schedule patterns like: "MWF 1200-1250 01/13"
```

## Classes Event Structure

### 25Live Classes Event Format
```json
{
  "summary": "The Modern & Postmodern World",
  "description": "Source: 25Live Classes\nProfile: MWF 1200-1250 01/13\nEvent ID: 2024-ABBPAR",
  "start": {"dateTime": "2025-01-13T12:00:00-08:00"},
  "end": {"dateTime": "2025-01-13T12:50:00-08:00"},
  "location": "Ross Center ROS 105"
}
```

### Tracked Event Data Structure
```json
{
  "timestamp": "2025-09-23T20:57:24.000000",
  "classes_event_id": "google_calendar_event_id",
  "work_event_id": "work_calendar_mirror_id",
  "summary": "The Modern & Postmodern World",
  "start": {"dateTime": "2025-01-13T12:00:00-08:00"},
  "location": "Ross Center ROS 105",
  "synced_to_work": true
}
```

## Automation Examples

### 1. Daily Classes Sync Automation
```bash
#!/bin/bash
# daily_classes_sync.sh

echo "$(date): Starting daily Classes sync"
cd /home/tradmin/CalPal

# Run sync with error handling
if python3 twentyfive_live_sync.py --log-level INFO; then
    echo "$(date): Classes sync completed successfully"

    # Check sync results
    CLASSES_CREATED=$(grep -o '"events_created": [0-9]*' 25live_sync_results.json | grep -A1 '"Classes"' | tail -1 | grep -o '[0-9]*')
    echo "$(date): Created $CLASSES_CREATED new Classes events"
else
    echo "$(date): Classes sync failed" >&2
    exit 1
fi
```

### 2. Classes Restoration Check
```bash
#!/bin/bash
# check_classes_restoration.sh

cd /home/tradmin/CalPal

echo "Running Classes restoration check..."
python3 twentyfive_live_sync.py --log-level DEBUG 2>&1 | grep -E "(restoration|missing|restored)"

# Check restoration results
RESTORED=$(grep -o '"events_restored": [0-9]*' 25live_sync_results.json | grep -A5 '"classes_restoration"' | tail -1 | grep -o '[0-9]*')
echo "Restored $RESTORED Classes events"
```

### 3. Classes Analytics
```python
#!/usr/bin/env python3
# classes_analytics.py

import json
from datetime import datetime
from collections import Counter

def analyze_classes_events():
    with open('/home/tradmin/CalPal/classes_mirrored_events.json', 'r') as f:
        classes_data = json.load(f)

    # Count events by summary (course)
    courses = Counter(event['summary'] for event in classes_data.values())

    print("=== Classes Analytics ===")
    print(f"Total Classes events tracked: {len(classes_data)}")
    print(f"Unique courses: {len(courses)}")
    print("\nTop courses by event count:")
    for course, count in courses.most_common(5):
        print(f"  {course}: {count} events")

    # Count events by location
    locations = Counter(event.get('location', 'No location') for event in classes_data.values())
    print("\nTop locations:")
    for location, count in locations.most_common(3):
        print(f"  {location}: {count} events")

if __name__ == '__main__':
    analyze_classes_events()
```

## Integration with Other Systems

### 1. Custom Calendar Creation
```python
# Create a custom calendar with only specific Classes
def create_filtered_classes_calendar(course_filter):
    sync_service = TwentyFiveLiveSync()

    with open('/home/tradmin/CalPal/classes_mirrored_events.json', 'r') as f:
        classes_data = json.load(f)

    # Filter events by course name
    filtered_events = {
        res_id: event for res_id, event in classes_data.items()
        if course_filter.lower() in event['summary'].lower()
    }

    return filtered_events
```

### 2. External API Integration
```python
# Export Classes data to external system
def export_classes_to_external_api():
    import requests

    with open('/home/tradmin/CalPal/classes_mirrored_events.json', 'r') as f:
        classes_data = json.load(f)

    # Transform for external API
    export_data = []
    for res_id, event in classes_data.items():
        export_data.append({
            'reservation_id': res_id,
            'course_name': event['summary'],
            'start_time': event['start']['dateTime'],
            'location': event.get('location', ''),
            'google_event_id': event['work_event_id']
        })

    # Send to external API
    response = requests.post('https://your-api.com/classes', json=export_data)
    return response.status_code == 200
```

## Monitoring and Maintenance

### Check Classes Sync Health
```bash
# Verify Classes calendar sync is working
python3 -c "
from twentyfive_live_sync import TwentyFiveLiveSync
import json

sync = TwentyFiveLiveSync()
result = sync.detect_and_restore_classes()

print('Classes Restoration Results:')
print(json.dumps(result, indent=2))
"
```

### Classes Event Count Monitoring
```bash
# Monitor Classes event counts over time
echo "$(date): $(cat /home/tradmin/CalPal/classes_mirrored_events.json | jq 'length') Classes events tracked" >> classes_tracking.log
```

## Configuration

### Required Files
- `/home/tradmin/.config/calpal/service-account-key.json` - Google Calendar API credentials
- `/home/tradmin/.config/calpal/25live_credentials.json` - 25Live API credentials
- `/home/tradmin/.config/calpal/calendar_config.json` - Calendar configuration

### Environment Variables
```bash
export CALPAL_CONFIG_DIR="/home/tradmin/.config/calpal"
export CALPAL_DATA_DIR="/home/tradmin/CalPal"
```

## Troubleshooting

### Common Issues

1. **Missing Classes Events**
   ```bash
   # Force restoration check
   python3 twentyfive_live_sync.py --log-level DEBUG 2>&1 | grep "Classes restoration"
   ```

2. **Duplicate Classes Events**
   - System uses Reservation IDs to prevent duplicates
   - Check for events with same Reservation ID pattern

3. **API Rate Limits**
   ```bash
   # Add delays between API calls if needed
   # System includes built-in rate limiting
   ```

### Log Analysis
```bash
# Check Classes-specific log entries
grep -E "(Classes|classes)" /var/log/calpal/sync.log

# Monitor restoration activity
grep "restored" /var/log/calpal/sync.log
```

## Best Practices

1. **Regular Syncing**: Run sync at least daily for current class schedules
2. **Backup Tracking Data**: Regularly backup `classes_mirrored_events.json`
3. **Monitor Restoration**: Check restoration results to catch deleted events
4. **Use Reservation IDs**: Always reference events by their 25Live Reservation ID
5. **Test Changes**: Use `--log-level DEBUG` when testing configuration changes

## Creating Custom Versions for Other Purposes

### Option 1: Copy Existing System to New Directory

To create a custom version for other purposes in a different directory:

```bash
# 1. Create new directory for your custom sync
mkdir -p /home/tradmin/MyCustomCalSync
cd /home/tradmin/MyCustomCalSync

# 2. Copy the existing sync system as a starting point
cp /home/tradmin/CalPal/twentyfive_live_sync.py ./my_custom_sync.py

# 3. Copy configuration files
mkdir -p config
cp /home/tradmin/.config/calpal/*.json ./config/

# 4. Copy documentation for reference
cp /home/tradmin/CalPal/docs/25Live_Classes_Sync.md ./README.md
```

### Option 2: View Existing System for Reference

Use these commands to examine the existing system:

```bash
# View the main sync system structure
cat /home/tradmin/CalPal/twentyfive_live_sync.py | head -100

# View Classes-specific methods
grep -A 20 "def.*classes" /home/tradmin/CalPal/twentyfive_live_sync.py

# View configuration structure
cat /home/tradmin/.config/calpal/calendar_config.json

# View current Classes tracking data
head -20 /home/tradmin/CalPal/classes_mirrored_events.json
```

### Custom Sync Template

Here's a minimal template for creating your own Classes-focused sync:

```python
#!/usr/bin/env python3
"""
Custom Classes Sync System
Based on the CalPal 25Live sync system
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

class CustomClassesSync:
    """Custom Classes synchronization system."""

    def __init__(self, config_dir: str = "./config"):
        self.config_dir = config_dir
        self.logger = logging.getLogger('custom-classes-sync')

        # Initialize Google Calendar service
        self.calendar_service = self._initialize_calendar_service()

        # Load configuration
        self._load_configuration()

        # Initialize tracking
        self.classes_events = {}
        self._load_tracking_data()

    def _initialize_calendar_service(self):
        """Initialize Google Calendar API service."""
        try:
            credentials = Credentials.from_service_account_file(
                f'{self.config_dir}/service-account-key.json',
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("✅ Google Calendar API service initialized")
            return service
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Calendar API: {e}")
            raise

    def _load_configuration(self):
        """Load calendar configuration."""
        with open(f'{self.config_dir}/calendar_config.json', 'r') as f:
            config = json.load(f)
            self.classes_calendar = config['calendars']['Classes']
            self.target_calendar = "your-target-calendar@gmail.com"  # Customize this

    def sync_classes_to_custom_calendar(self):
        """Sync Classes events to your custom calendar."""
        self.logger.info("🔄 Starting custom Classes sync...")

        # Fetch Classes events
        classes_events = self._fetch_classes_events()

        # Process each event for your custom needs
        for event in classes_events:
            self._process_classes_event(event)

        self.logger.info(f"✅ Processed {len(classes_events)} Classes events")

    def _fetch_classes_events(self) -> List[Dict]:
        """Fetch events from Classes calendar."""
        try:
            # Calculate time range
            time_min = (datetime.now() - timedelta(days=7)).isoformat() + 'Z'
            time_max = (datetime.now() + timedelta(days=30)).isoformat() + 'Z'

            events_result = self.calendar_service.events().list(
                calendarId=self.classes_calendar,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            return events_result.get('items', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch Classes events: {e}")
            return []

    def _process_classes_event(self, event: Dict):
        """Process a Classes event for your custom needs."""
        # Extract 25Live Reservation ID
        reservation_id = self._extract_reservation_id(event)
        if not reservation_id:
            return

        # Check if already processed
        if reservation_id in self.classes_events:
            return

        # Your custom processing logic here
        custom_event = self._create_custom_event(event)

        # Track the event
        self.classes_events[reservation_id] = {
            'timestamp': datetime.now().isoformat(),
            'original_event_id': event.get('id'),
            'summary': event.get('summary', ''),
            'start': event.get('start', {}),
            'location': event.get('location', ''),
            'custom_processed': True
        }

        self._save_tracking_data()

    def _extract_reservation_id(self, event: Dict) -> Optional[str]:
        """Extract 25Live Reservation ID from Classes event."""
        description = event.get('description', '')
        if 'Profile: ' in description:
            for line in description.split('\n'):
                if line.startswith('Profile: '):
                    profile_value = line.replace('Profile: ', '').strip()
                    if profile_value and any(c.isdigit() for c in profile_value):
                        return profile_value
        return None

    def _create_custom_event(self, event: Dict) -> Dict:
        """Create your custom event format."""
        # Customize this for your needs
        return {
            'summary': f"[Custom] {event.get('summary', '')}",
            'description': f"Custom processing of: {event.get('summary', '')}",
            'start': event.get('start'),
            'end': event.get('end'),
            'location': event.get('location', '')
        }

    def _load_tracking_data(self):
        """Load tracking data."""
        try:
            with open('custom_classes_tracking.json', 'r') as f:
                self.classes_events = json.load(f)
        except FileNotFoundError:
            self.classes_events = {}

    def _save_tracking_data(self):
        """Save tracking data."""
        with open('custom_classes_tracking.json', 'w') as f:
            json.dump(self.classes_events, f, indent=2, default=str)

def main():
    """Main function."""
    logging.basicConfig(level=logging.INFO)

    sync = CustomClassesSync()
    sync.sync_classes_to_custom_calendar()

if __name__ == '__main__':
    main()
```

### Adaptation Instructions

1. **Modify Calendar Targets**: Change `self.target_calendar` to your desired destination
2. **Customize Event Processing**: Modify `_create_custom_event()` for your specific needs
3. **Add Custom Logic**: Implement your business logic in `_process_classes_event()`
4. **Change Tracking**: Modify tracking data structure for your use case
5. **Update Configuration**: Create your own config files based on the originals

### Quick Start for New Directory

```bash
#!/bin/bash
# setup_custom_classes_sync.sh

# Create directory structure
mkdir -p /home/tradmin/MyClassesSync/{config,logs,data}
cd /home/tradmin/MyClassesSync

# Copy reference files
echo "Copying reference files..."
cp /home/tradmin/CalPal/twentyfive_live_sync.py ./reference_sync.py
cp /home/tradmin/.config/calpal/*.json ./config/

# Create custom sync from template above
cat > custom_classes_sync.py << 'EOF'
# [Insert the template code above]
EOF

# Make executable
chmod +x custom_classes_sync.py

echo "Custom Classes sync setup complete!"
echo "Directory: /home/tradmin/MyClassesSync"
echo "Edit custom_classes_sync.py to customize for your needs"
```

### Integration with Existing System

To use the existing system as a library in your custom project:

```python
# In your custom project
import sys
sys.path.append('/home/tradmin/CalPal')
from twentyfive_live_sync import TwentyFiveLiveSync

class MyCustomClassesHandler:
    def __init__(self):
        # Use the existing sync system as a library
        self.calpal_sync = TwentyFiveLiveSync()

    def get_classes_data(self):
        """Get Classes data from CalPal system."""
        import json
        with open('/home/tradmin/CalPal/classes_mirrored_events.json', 'r') as f:
            return json.load(f)

    def process_for_my_needs(self):
        """Process Classes data for your custom needs."""
        classes_data = self.get_classes_data()

        # Your custom processing here
        for reservation_id, event_data in classes_data.items():
            # Do something with each Classes event
            print(f"Processing {event_data['summary']} ({reservation_id})")
```

## API Reference

### Key Methods
- `sync_calendar_type('Classes')` - Sync Classes calendar only
- `detect_and_restore_classes()` - Check for deleted Classes events and restore
- `_extract_25live_reservation_id(event_data)` - Extract unique 25Live identifier
- `_create_classes_event_signature(event_data)` - Generate tracking signature

### Configuration Access
- `self.calendars['Classes']` - Classes calendar ID
- `self.work_calendar` - Work calendar ID for mirroring
- `self.classes_event_tracker` - Classes tracking data structure