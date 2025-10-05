# CalPal Configuration Guide

Complete reference for all CalPal configuration options.

## Table of Contents

- [Configuration Files](#configuration-files)
- [Core Settings](#core-settings)
- [Google Calendar API](#google-calendar-api)
- [25Live API](#25live-api)
- [Database Configuration](#database-configuration)
- [Calendar Mappings](#calendar-mappings)
- [Security Settings](#security-settings)
- [Service Intervals](#service-intervals)
- [File Paths](#file-paths)
- [Event Processing](#event-processing)
- [Logging Configuration](#logging-configuration)
- [Environment Variables](#environment-variables)
- [Advanced Configuration](#advanced-configuration)

## Configuration Files

CalPal uses multiple configuration mechanisms:

| File | Purpose | Format | Git Tracked |
|------|---------|--------|-------------|
| `config.py` | Main configuration | Python | No (sensitive) |
| `config.example.py` | Configuration template | Python | Yes |
| `.env` | Environment overrides | KEY=VALUE | No (sensitive) |
| `docker-compose.yml` | Database settings | YAML | Yes |
| `~/.config/calpal/service-account-key.json` | Google API credentials | JSON | No (sensitive) |
| `~/.config/calpal/25live_credentials` | 25Live credentials | Text | No (sensitive) |

## Core Settings

### config.py Structure

```python
"""
Configuration settings for CalPal 25Live Sync System.
"""

import os
from pathlib import Path

# Base configuration directory
CONFIG_DIR = os.path.expanduser('~/.config/calpal')

# Project paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / 'data'
PRIVATE_DIR = PROJECT_ROOT / 'private'
LOGS_DIR = PROJECT_ROOT / 'logs'
METADATA_DIR = PROJECT_ROOT / 'metadata'

# Ensure directories exist
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PRIVATE_DIR, exist_ok=True)
```

### Directory Structure

- **CONFIG_DIR**: Stores sensitive credentials outside repository
- **PROJECT_ROOT**: Base directory for CalPal installation
- **DATA_DIR**: Runtime data files (git-ignored)
- **PRIVATE_DIR**: Generated ICS files and private data (git-ignored)
- **LOGS_DIR**: Application logs (git-ignored)
- **METADATA_DIR**: Event tracking metadata (git-ignored)

## Google Calendar API

### Authentication

```python
# Service Account Key File
GOOGLE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'service-account-key.json')

# Required OAuth Scopes
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']
```

**Setup Steps:**
1. Download service account key from Google Cloud Console
2. Save as `~/.config/calpal/service-account-key.json`
3. Set file permissions: `chmod 600 ~/.config/calpal/service-account-key.json`

### Calendar IDs

```python
# Primary work calendar (your main Google Calendar)
WORK_CALENDAR_ID = 'username@example.edu'

# Personal calendar (for personal/family events)
PERSONAL_CALENDAR_ID = 'username@gmail.com'

# Family calendar (optional)
FAMILY_CALENDAR_ID = 'family_calendar@group.calendar.google.com'
```

**Finding Calendar IDs:**
```python
# Run this Python snippet:
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    '~/.config/calpal/service-account-key.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
service = build('calendar', 'v3', credentials=creds)
calendars = service.calendarList().list().execute()

for calendar in calendars['items']:
    print(f"{calendar['summary']}: {calendar['id']}")
```

## 25Live API

### Credentials

```python
# Path to 25Live credentials file
TWENTYFIVE_LIVE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, '25live_credentials')

# 25Live API base URL
TWENTYFIVE_LIVE_BASE_URL = 'https://25live.collegenet.com'

# Your institution's identifier
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'  # e.g., 'georgefox', 'stanford'
```

**Credentials File Format:**
```
username
password
```
Two lines: username on first line, password on second line.

**Example Setup:**
```bash
echo "your_username" > ~/.config/calpal/25live_credentials
echo "your_password" >> ~/.config/calpal/25live_credentials
chmod 600 ~/.config/calpal/25live_credentials
```

### 25Live Query Configuration

```python
# Custom 25Live queries (optional)
TWENTYFIVE_LIVE_QUERIES = {
    'Classes': {
        'query_id': '12345',  # Your Classes query ID
        'calendar_id': 'abc123@group.calendar.google.com'
    },
    'Events': {
        'query_id': '67890',  # Your Events query ID
        'calendar_id': 'def456@group.calendar.google.com'
    }
}
```

## Database Configuration

### Connection Settings

```python
# Database connection string
DATABASE_URL = 'postgresql://username:password@host:port/database'

# Example for Docker setup:
DATABASE_URL = 'postgresql://calpal:calpal_dev_password@localhost:5433/calpal_db'

# Example for remote database:
DATABASE_URL = 'postgresql://calpal:secure_password@db.example.com:5432/calpal_db'
```

### Connection String Format

```
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

| Component | Description | Example |
|-----------|-------------|---------|
| USER | Database username | `calpal` |
| PASSWORD | Database password | `secure_password` |
| HOST | Database host | `localhost` or `db.example.com` |
| PORT | Database port | `5433` (Docker) or `5432` (standard) |
| DATABASE | Database name | `calpal_db` |

### Environment Variable Override

```python
# Allow environment variable to override config.py
DATABASE_URL = os.getenv('DATABASE_URL',
    'postgresql://calpal:calpal_dev_password@localhost:5433/calpal_db'
)
```

**Usage:**
```bash
export DATABASE_URL='postgresql://user:pass@host:5432/db'
python3 src/unified_db_calpal_service.py
```

## Calendar Mappings

### Basic Mappings

```python
CALENDAR_MAPPINGS = {
    # Friendly Name: Google Calendar ID
    'Classes': 'abc123def456@group.calendar.google.com',
    'Events': 'xyz789uvw012@group.calendar.google.com',
    'Appointments': 'bookings123@group.calendar.google.com',
}
```

### Subcalendar Structure

```python
# Subcalendars for event organization
SUBCALENDARS = {
    'Appointments': 'appointments_calendar_id@group.calendar.google.com',
    'Meetings': 'meetings_calendar_id@group.calendar.google.com',
    'Personal Mirror': 'personal_mirror_id@group.calendar.google.com',
    'Family Mirror': 'family_mirror_id@group.calendar.google.com',
}
```

### Calendar Hierarchy

```
Work Calendar (Main)
├── Classes (from 25Live)
├── Events (from 25Live)
├── Appointments (bookings)
├── Meetings (invitations)
├── Personal Mirror (mirrored from personal)
└── Family Mirror (mirrored from family)
```

## Security Settings

### Web Server Security

```python
# Flask server settings
FLASK_HOST = '0.0.0.0'  # Listen on all interfaces
FLASK_PORT = 5001       # Web server port

# Secure endpoint path (random, unguessable)
SECURE_ENDPOINT_PATH = 'zj9ETjqLo2EFWwwUtMORWgnI94ji_4Obbsanw5ld8EM'

# Access token for ICS downloads
ACCESS_TOKEN = 'your-random-secure-token-here'
```

**Generating Secure Tokens:**
```python
import secrets

# Generate random endpoint path (32 bytes = 43 chars base64)
endpoint_path = secrets.token_urlsafe(32)
print(f"SECURE_ENDPOINT_PATH = '{endpoint_path}'")

# Generate access token
access_token = secrets.token_urlsafe(32)
print(f"ACCESS_TOKEN = '{access_token}'")
```

### ICS File Settings

```python
# ICS file location
ICS_FILE_PATH = os.path.join(PRIVATE_DIR, 'calendar.ics')

# ICS file permissions (octal notation)
ICS_FILE_MODE = 0o600  # Read/write for owner only
```

### Credential Permissions

All credential files should have restricted permissions:

```bash
chmod 600 ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/25live_credentials
chmod 600 config.py
chmod 700 ~/.config/calpal  # Directory
```

## Service Intervals

### Unified Service Timing

```python
# Component intervals (in seconds)
SERVICE_INTERVALS = {
    '25live_sync': 30 * 60,       # 30 minutes
    'calendar_scan': 15 * 60,     # 15 minutes
    'personal_family': 10 * 60,   # 10 minutes
    'work_organizer': 5 * 60,     # 5 minutes
    'subcalendar_sync': 10 * 60,  # 10 minutes
    'wife_ics': 5 * 60            # 5 minutes
}
```

### Customizing Intervals

```python
# Faster sync for development/testing
SERVICE_INTERVALS = {
    '25live_sync': 5 * 60,   # Every 5 minutes
    'calendar_scan': 2 * 60,  # Every 2 minutes
    'wife_ics': 1 * 60        # Every minute
}

# Slower sync for low-activity environments
SERVICE_INTERVALS = {
    '25live_sync': 60 * 60,   # Every hour
    'calendar_scan': 30 * 60,  # Every 30 minutes
    'wife_ics': 10 * 60        # Every 10 minutes
}
```

### Interval Recommendations

| Service | Minimum | Recommended | Maximum |
|---------|---------|-------------|---------|
| 25Live Sync | 5 min | 30 min | 2 hours |
| Calendar Scan | 1 min | 15 min | 1 hour |
| ICS Generation | 1 min | 5 min | 15 min |
| Work Organizer | 1 min | 5 min | 15 min |

## File Paths

### Generated Files

```python
# ICS calendar output
ICS_OUTPUT_FILE = os.path.join(PRIVATE_DIR, 'travis_schedule.ics')

# Metadata tracking
ICS_METADATA_FILE = os.path.join(PRIVATE_DIR, 'travis_schedule_metadata.json')

# Sync results
SYNC_RESULTS_FILE = os.path.join(PROJECT_ROOT, '25live_sync_results.json')
DB_SYNC_RESULTS_FILE = os.path.join(PROJECT_ROOT, 'db_25live_sync_results.json')

# Scan results
CALENDAR_SCAN_RESULTS_FILE = os.path.join(PROJECT_ROOT, 'calendar_scan_results.json')
```

### Log Files

```python
# Log file paths
MAIN_LOG_FILE = os.path.join(LOGS_DIR, 'calpal.log')
ERROR_LOG_FILE = os.path.join(LOGS_DIR, 'errors.log')
SYNC_LOG_FILE = os.path.join(LOGS_DIR, '25live_sync.log')
SCAN_LOG_FILE = os.path.join(LOGS_DIR, 'calendar_scan.log')
```

## Event Processing

### Event Type Classification

```python
# Event type rules
EVENT_TYPE_RULES = {
    'booking': {
        'summary_contains': ['booked by', 'meet with'],
        'description_contains': ['booking', 'appointment']
    },
    '25live_class': {
        'description_contains': ['source: 25live classes']
    },
    '25live_event': {
        'description_contains': ['source: 25live events']
    }
}
```

### Event Filtering

```python
# Keywords to filter out
EVENT_FILTER_KEYWORDS = [
    'committee', 'governance', 'council', 'board',
    'senate', 'faculty', 'meeting'
]

# Calendars to exclude from ICS
EXCLUDED_CALENDARS = [
    'personal_calendar@gmail.com',
    'family_calendar@group.calendar.google.com'
]
```

### Event Transformations

```python
# ICS output transformation rules
ICS_TRANSFORMATION_RULES = {
    'classes': {
        'summary': 'In class',
        'location': None,  # Hide location
        'description': None  # Hide description
    },
    '25live_events': {
        'summary': 'Campus Event',
        'include_location': True,
        'include_description': False
    },
    'work_events': {
        'summary': 'In a meeting',
        'include_location': True,
        'include_description': False
    }
}
```

## Logging Configuration

### Basic Logging

```python
import logging

# Logging level
LOG_LEVEL = logging.INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Date format
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.FileHandler(MAIN_LOG_FILE),
        logging.StreamHandler()  # Also log to console
    ]
)
```

### Advanced Logging

```python
# Separate loggers for different components
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
        'simple': {
            'format': '%(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'INFO'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/calpal.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'detailed',
            'level': 'DEBUG'
        },
        'error_file': {
            'class': 'logging.FileHandler',
            'filename': 'logs/errors.log',
            'formatter': 'detailed',
            'level': 'ERROR'
        }
    },
    'loggers': {
        'calpal': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}
```

### Log Rotation

```python
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

# Size-based rotation (10MB per file, keep 5 backups)
handler = RotatingFileHandler(
    'logs/calpal.log',
    maxBytes=10*1024*1024,
    backupCount=5
)

# Time-based rotation (daily, keep 30 days)
handler = TimedRotatingFileHandler(
    'logs/calpal.log',
    when='midnight',
    interval=1,
    backupCount=30
)
```

## Environment Variables

### Supported Variables

```python
# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://...')

# Google credentials path
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE',
    os.path.join(CONFIG_DIR, 'service-account-key.json')
)

# 25Live institution
TWENTYFIVE_LIVE_INSTITUTION = os.getenv('TWENTYFIVE_LIVE_INSTITUTION',
    'your-institution'
)

# Flask settings
FLASK_PORT = int(os.getenv('FLASK_PORT', 5001))
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')

# Log level
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
```

### Using .env File

Create `.env` in project root:

```bash
# .env file
DATABASE_URL=postgresql://calpal:password@localhost:5433/calpal_db
GOOGLE_CREDENTIALS_FILE=/home/user/.config/calpal/service-account-key.json
TWENTYFIVE_LIVE_INSTITUTION=myuniversity
FLASK_PORT=5001
LOG_LEVEL=DEBUG
```

Load with python-dotenv:

```python
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Access variables
db_url = os.getenv('DATABASE_URL')
```

## Advanced Configuration

### Date Range Settings

```python
# Sync lookback/lookahead periods
SYNC_LOOKBACK_DAYS = 30    # Scan 30 days in past
SYNC_LOOKAHEAD_DAYS = 365  # Scan 365 days in future

# 25Live API limits (max range per request)
TWENTYFIVE_LIVE_MAX_DAYS = 140  # 20 weeks
```

### Rate Limiting

```python
# API request delays
GOOGLE_API_DELAY = 0.1  # 100ms between Google API calls
TWENTYFIVE_LIVE_API_DELAY = 0.5  # 500ms between 25Live API calls

# Batch sizes
GOOGLE_BATCH_SIZE = 100  # Max events per batch request
TWENTYFIVE_LIVE_BATCH_SIZE = 50  # Max events per 25Live query
```

### Retry Configuration

```python
# Retry settings for API calls
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff: 1s, 2s, 4s
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # Retry on these HTTP codes
```

### Performance Tuning

```python
# Database connection pool
DB_POOL_SIZE = 5        # Number of connections in pool
DB_MAX_OVERFLOW = 10    # Max connections beyond pool_size
DB_POOL_TIMEOUT = 30    # Seconds to wait for connection

# Calendar scan optimization
SCAN_MAX_RESULTS = 2500  # Max events to fetch per calendar
SCAN_PARALLEL_REQUESTS = 3  # Parallel API requests
```

### Feature Flags

```python
# Enable/disable features
ENABLE_25LIVE_SYNC = True
ENABLE_CALENDAR_SCAN = True
ENABLE_PERSONAL_MIRROR = True
ENABLE_ICS_GENERATION = True
ENABLE_WEB_SERVER = True

# Debug features
DEBUG_MODE = False
VERBOSE_LOGGING = False
DRY_RUN = False  # Simulate changes without making them
```

## Configuration Validation

### Validation Script

```python
def validate_config():
    """Validate configuration settings."""
    errors = []

    # Check required files exist
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        errors.append(f"Google credentials not found: {GOOGLE_CREDENTIALS_FILE}")

    if not os.path.exists(TWENTYFIVE_LIVE_CREDENTIALS_FILE):
        errors.append(f"25Live credentials not found: {TWENTYFIVE_LIVE_CREDENTIALS_FILE}")

    # Check database connection
    try:
        from src.db_manager import DatabaseManager
        db = DatabaseManager(DATABASE_URL)
        if not db.test_connection():
            errors.append("Database connection failed")
    except Exception as e:
        errors.append(f"Database error: {e}")

    # Check calendar IDs format
    if '@' not in WORK_CALENDAR_ID:
        errors.append(f"Invalid WORK_CALENDAR_ID: {WORK_CALENDAR_ID}")

    # Report results
    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("✅ Configuration valid")
        return True

if __name__ == '__main__':
    validate_config()
```

## Example Configurations

### Development Configuration

```python
# config.py - Development
DATABASE_URL = 'postgresql://calpal:dev_password@localhost:5433/calpal_db'
LOG_LEVEL = logging.DEBUG
FLASK_PORT = 5001
FLASK_HOST = '127.0.0.1'  # Localhost only
SERVICE_INTERVALS = {
    '25live_sync': 5 * 60,   # Faster for testing
    'calendar_scan': 2 * 60,
    'wife_ics': 1 * 60
}
DEBUG_MODE = True
DRY_RUN = False
```

### Production Configuration

```python
# config.py - Production
DATABASE_URL = os.getenv('DATABASE_URL')  # From environment
LOG_LEVEL = logging.INFO
FLASK_PORT = 8080
FLASK_HOST = '0.0.0.0'  # All interfaces
SERVICE_INTERVALS = {
    '25live_sync': 30 * 60,
    'calendar_scan': 15 * 60,
    'wife_ics': 5 * 60
}
DEBUG_MODE = False
DRY_RUN = False

# Stricter security
SECURE_ENDPOINT_PATH = os.getenv('SECURE_ENDPOINT_PATH')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
```

### Minimal Configuration (No 25Live)

```python
# config.py - Google Calendar only
ENABLE_25LIVE_SYNC = False
ENABLE_CALENDAR_SCAN = True
ENABLE_PERSONAL_MIRROR = True
ENABLE_ICS_GENERATION = True

DATABASE_URL = 'postgresql://calpal:password@localhost:5433/calpal_db'
WORK_CALENDAR_ID = 'username@example.com'
PERSONAL_CALENDAR_ID = 'username@gmail.com'

SERVICE_INTERVALS = {
    'calendar_scan': 10 * 60,
    'personal_family': 5 * 60,
    'wife_ics': 5 * 60
}
```

## Troubleshooting Configuration

### Common Issues

**Config not found:**
```bash
# Verify config.py exists
ls -l config.py

# Copy from example
cp config.example.py config.py
```

**Import errors:**
```python
# Test config loading
python3 -c "import config; print('Config loaded')"
```

**Credential errors:**
```bash
# Check file permissions
ls -l ~/.config/calpal/

# Fix permissions
chmod 600 ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/25live_credentials
```

**Database connection errors:**
```bash
# Test database
python3 -c "from src.db_manager import DatabaseManager; db = DatabaseManager(); db.test_connection()"

# Check Docker
docker compose ps
docker compose logs calpal_db
```

## Next Steps

- See [INSTALLATION.md](INSTALLATION.md) for setup instructions
- See [SERVICES.md](SERVICES.md) for service documentation
- See [SECURITY.md](SECURITY.md) for security best practices
