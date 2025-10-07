# Configuration Reference

Complete reference for all CalPal configuration options.

## Configuration Files

CalPal uses multiple configuration files:
- `config.py` - Main Python configuration
- `.env` - Environment variables (credentials, secrets)
- `data/work_subcalendars.json` - Calendar ID mappings
- `private/25live_queries.json` - 25Live query configurations (optional)

## Environment Variables (`.env`)

### Required Settings

```bash
# Database connection string
DATABASE_URL=postgresql://username:password@host:port/database

# Primary calendar identifiers
WORK_CALENDAR_ID=work@institution.edu
PERSONAL_CALENDAR_ID=personal@gmail.com

# 25Live institution identifier
TWENTYFIVE_LIVE_INSTITUTION=your_institution
```

### Optional Settings

```bash
# Additional Google Calendar IDs
FAMILY_CALENDAR_ID=family-hash@group.calendar.google.com
CLASSES_CALENDAR_ID=classes-hash@group.calendar.google.com
GFU_EVENTS_CALENDAR_ID=events-hash@group.calendar.google.com
APPOINTMENTS_CALENDAR_ID=appointments-hash@group.calendar.google.com

# 25Live API settings
TWENTYFIVE_LIVE_BASE_URL=https://25live.collegenet.com

# Flask server configuration
FLASK_HOST=0.0.0.0
FLASK_PORT=5001

# Security tokens (generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
SECURE_ENDPOINT_PATH=your-random-secure-path
ACCESS_TOKEN=your-random-access-token

# Public domain for ICS URLs
PUBLIC_DOMAIN=example.com
PUBLIC_ICS_URL=https://example.com/path/schedule.ics

# Sync timing
SYNC_LOOKBACK_DAYS=30
SYNC_LOOKAHEAD_DAYS=365

# File paths
ICS_FILE_PATH=./private/schedule.ics
CALPAL_CONFIG_DIR=~/.config/calpal
```

## Python Configuration (`config.py`)

### Directory Paths

```python
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / 'data'
PRIVATE_DIR = PROJECT_ROOT / 'private'
LOGS_DIR = PROJECT_ROOT / 'logs'
METADATA_DIR = PROJECT_ROOT / 'metadata'
CONFIG_DIR = os.getenv('CALPAL_CONFIG_DIR', '~/.config/calpal')
```

### Google Calendar Settings

```python
# Service account credentials
GOOGLE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'service-account-key.json')
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']

# Calendar mappings for subcalendars
CALENDAR_MAPPINGS = {
    'Classes': os.getenv('CLASSES_CALENDAR_ID'),
    'GFU Events': os.getenv('GFU_EVENTS_CALENDAR_ID'),
    'Appointments': os.getenv('APPOINTMENTS_CALENDAR_ID')
}
```

### 25Live Settings

```python
TWENTYFIVE_LIVE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, '25live_credentials')
TWENTYFIVE_LIVE_BASE_URL = os.getenv('TWENTYFIVE_LIVE_BASE_URL', 'https://25live.collegenet.com')
TWENTYFIVE_LIVE_INSTITUTION = os.getenv('TWENTYFIVE_LIVE_INSTITUTION')
```

### Event Processing

```python
# Keywords for event filtering and categorization
EVENT_FILTER_KEYWORDS = [
    'committee', 'governance', 'council', 'board', 'senate', 'faculty'
]

# Sync time windows
SYNC_LOOKBACK_DAYS = int(os.getenv('SYNC_LOOKBACK_DAYS', '30'))
SYNC_LOOKAHEAD_DAYS = int(os.getenv('SYNC_LOOKAHEAD_DAYS', '365'))
```

## Calendar Mappings (`data/work_subcalendars.json`)

Maps subcalendar names to Google Calendar IDs:

```json
{
  "Classes": "your-classes-calendar-id@group.calendar.google.com",
  "Meetings": "your-meetings-calendar-id@group.calendar.google.com",
  "Appointments": "your-appointments-calendar-id@group.calendar.google.com",
  "GFU Events": "your-events-calendar-id@group.calendar.google.com",
  "Personal Events": "your-personal-calendar-id@group.calendar.google.com",
  "Family Events": "your-family-calendar-id@group.calendar.google.com"
}
```

## 25Live Queries (`private/25live_queries.json`)

Configure 25Live API queries:

```json
{
  "classes_query": {
    "event_type_id": "14",
    "description": "Academic class events",
    "filters": {
      "event_type": "14",
      "state": "2"
    }
  },
  "events_query": {
    "event_type_id": "all",
    "description": "Campus events",
    "filters": {
      "state": "2"
    }
  }
}
```

## Advanced Configuration

### Custom Event Routing

Edit `calpal/organizers/event_organizer.py` to customize event routing logic:

```python
def determine_target_calendar(self, event):
    # Custom routing logic
    if "exam" in event.summary.lower():
        return "Classes"
    elif "office hours" in event.summary.lower():
        return "Appointments"
    # ... add more rules
```

### Custom ICS Filters

Edit `calpal/generators/ics_generator.py` to customize ICS output:

```python
def should_include_event(self, event):
    # Exclude specific calendars
    if event.current_calendar == "Personal":
        return False
    # Include only certain event types
    return event.event_type in ['work', 'class', 'meeting']

def transform_event(self, event):
    # Privacy protection
    if event.event_type == 'personal_mirror':
        event.summary = "Busy"
        event.description = ""
    return event
```

## Database Configuration

### Connection Parameters

```python
DATABASE_URL = 'postgresql://username:password@host:port/database?options'

# Connection pool settings (for production)
DATABASE_POOL_SIZE = 10
DATABASE_MAX_OVERFLOW = 20
DATABASE_POOL_TIMEOUT = 30  # seconds
```

### PostgreSQL Settings

Recommended `postgresql.conf` settings for CalPal:

```conf
# Connection settings
max_connections = 100

# Memory settings
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

# Performance
random_page_cost = 1.1
effective_io_concurrency = 200

# Logging
log_min_duration_statement = 1000  # Log queries > 1s
```

## Logging Configuration

Configure logging in each service component:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/calpal.log'),
        logging.StreamHandler()  # Also log to console
    ]
)

# Set specific log levels
logging.getLogger('googleapiclient').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
```

## Production Configuration

### Systemd Service File

`/etc/systemd/system/calpal.service`:

```ini
[Unit]
Description=CalPal Calendar Sync Service
After=network.target postgresql.service

[Service]
Type=simple
User=calpal
WorkingDirectory=/opt/calpal
Environment="PATH=/opt/calpal/venv/bin"
EnvironmentFile=/opt/calpal/.env
ExecStart=/opt/calpal/venv/bin/python3 -m calpal.sync.unified_sync_service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy

For ICS server:

```nginx
server {
    listen 443 ssl http2;
    server_name calendar.example.com;

    ssl_certificate /etc/letsencrypt/live/calendar.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/calendar.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Environment-Specific Configurations

### Development

```bash
# .env.development
DATABASE_URL=postgresql://calpal:dev@localhost:5433/calpal_dev
SYNC_LOOKBACK_DAYS=7
SYNC_LOOKAHEAD_DAYS=30
LOG_LEVEL=DEBUG
```

### Production

```bash
# .env.production
DATABASE_URL=postgresql://calpal:prod_pw@db.example.com:5432/calpal_prod
SYNC_LOOKBACK_DAYS=30
SYNC_LOOKAHEAD_DAYS=365
LOG_LEVEL=INFO
SENTRY_DSN=https://your-sentry-dsn  # Optional error tracking
```

## Validation

Test your configuration:

```bash
# Validate config files
python3 -c "import config; print('Config loaded successfully')"

# Test database connection
python3 -c "from calpal.core.db_manager import DatabaseManager; db = DatabaseManager(); print('DB connection successful')"

# Test Google Calendar API
python3 -c "from calpal.sync.calendar_scanner import CalendarScanner; cs = CalendarScanner(); print('Google API connected')"

# Test 25Live API
python3 -c "from calpal.sync.twentyfive_live_sync import TwentyFiveLiveSync; sync = TwentyFiveLiveSync(); print('25Live connected')"
```

## Troubleshooting

### Invalid DATABASE_URL
```bash
# Verify format
echo $DATABASE_URL
# Should match: postgresql://user:pass@host:port/database

# Test connection
psql "$DATABASE_URL" -c "SELECT 1;"
```

### Missing Calendar IDs
```bash
# Verify .env variables are loaded
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('WORK_CALENDAR_ID'))"
```

### Credential File Errors
```bash
# Check permissions
ls -la ~/.config/calpal/
# Should show: -rw------- (600)

# Fix permissions
chmod 600 ~/.config/calpal/*
```
