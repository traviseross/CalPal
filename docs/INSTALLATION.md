# CalPal Installation Guide

Complete step-by-step installation instructions for setting up CalPal from scratch.

## Table of Contents

- [Prerequisites](#prerequisites)
- [System Requirements](#system-requirements)
- [Installation Steps](#installation-steps)
- [Database Setup](#database-setup)
- [Google Cloud Setup](#google-cloud-setup)
- [25Live API Setup](#25live-api-setup)
- [Configuration](#configuration)
- [Initial Sync](#initial-sync)
- [Running as a Service](#running-as-a-service)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- **Python 3.8 or higher**
  ```bash
  python3 --version  # Should show 3.8+
  ```

- **PostgreSQL 15 or higher** (or Docker for containerized database)
  ```bash
  postgres --version  # Should show 15+
  # OR
  docker --version  # For Docker-based setup
  ```

- **Git**
  ```bash
  git --version
  ```

- **pip** (Python package installer)
  ```bash
  pip3 --version
  ```

### Required Accounts/Access

- **Google Cloud Project** with Calendar API enabled
- **25Live Account** with API access credentials
- **Google Workspace** with domain admin permissions (for service account delegation)

## System Requirements

### Minimum Requirements

- **OS**: Linux, macOS, or Windows (with WSL2)
- **RAM**: 2GB minimum, 4GB recommended
- **Disk**: 1GB free space (plus database storage)
- **Network**: Reliable internet connection for API calls

### Recommended Setup

- **OS**: Ubuntu 20.04+ or Debian 11+
- **RAM**: 4GB+
- **Disk**: 5GB+ (for logs and database growth)
- **CPU**: 2+ cores

## Installation Steps

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/CalPal.git
cd CalPal

# Create a backup of example configs
cp config.example.py config.example.py.backup
```

### 2. Set Up Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/macOS
# OR
venv\Scripts\activate  # On Windows

# Verify activation (should show venv in prompt)
which python3  # Should point to venv/bin/python3
```

### 3. Install Python Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install CalPal dependencies
pip install -r requirements.txt

# Verify installation
python3 -c "import googleapiclient, icalendar, flask, psycopg2, sqlalchemy; print('All dependencies installed successfully')"
```

## Database Setup

### Option A: Docker Setup (Recommended)

```bash
# Ensure Docker and Docker Compose are installed
docker --version
docker compose version

# Start PostgreSQL database
docker compose up -d

# Verify database is running
docker compose ps

# Check database logs
docker compose logs calpal_db

# Test database connection
docker exec -it calpal_db psql -U calpal -d calpal_db -c "SELECT 1;"
```

**Database Connection Details:**
- Host: `localhost`
- Port: `5433`
- Database: `calpal_db`
- Username: `calpal`
- Password: `calpal_dev_password` (change for production!)

### Option B: Manual PostgreSQL Setup

```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql << EOF
CREATE USER calpal WITH PASSWORD 'your_secure_password';
CREATE DATABASE calpal_db OWNER calpal;
GRANT ALL PRIVILEGES ON DATABASE calpal_db TO calpal;
\q
EOF

# Initialize schema
psql -U calpal -d calpal_db -f db/init/01_schema.sql
```

### Verify Database Schema

```bash
# Check tables exist
docker exec -it calpal_db psql -U calpal -d calpal_db -c "\dt"

# Should show:
#  Schema |      Name       | Type  | Owner
# --------+-----------------+-------+-------
#  public | calendar_events | table | calpal

# Check schema details
docker exec -it calpal_db psql -U calpal -d calpal_db -c "\d calendar_events"
```

## Google Cloud Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Note your Project ID

### 2. Enable Google Calendar API

```bash
# Via gcloud CLI (if installed)
gcloud services enable calendar-json.googleapis.com --project=YOUR_PROJECT_ID

# Or via Console:
# 1. Navigate to "APIs & Services" > "Library"
# 2. Search for "Google Calendar API"
# 3. Click "Enable"
```

### 3. Create Service Account

1. **Navigate to IAM & Admin** > **Service Accounts**
2. **Click "Create Service Account"**
   - Name: `calpal-service-account`
   - Description: `CalPal calendar sync service`
3. **Skip role assignment** (not needed for calendar access)
4. **Create and download key**:
   - Click on the created service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose "JSON" format
   - Download the key file

### 4. Set Up Domain-Wide Delegation (Optional)

Only needed if accessing other users' calendars:

1. **Enable Domain-Wide Delegation**:
   - In service account details, click "Show Domain-Wide Delegation"
   - Enable "Enable Google Workspace Domain-wide Delegation"
   - Note the Client ID

2. **Configure in Google Admin Console**:
   - Go to [admin.google.com](https://admin.google.com)
   - Security > API Controls > Domain-wide Delegation
   - Add new API client:
     - Client ID: (from service account)
     - OAuth Scopes: `https://www.googleapis.com/auth/calendar`

### 5. Install Service Account Key

```bash
# Create config directory
mkdir -p ~/.config/calpal

# Copy service account key
cp ~/Downloads/your-service-account-key.json ~/.config/calpal/service-account-key.json

# Secure the file
chmod 600 ~/.config/calpal/service-account-key.json

# Verify
ls -l ~/.config/calpal/service-account-key.json
# Should show: -rw------- (readable only by you)
```

### 6. Grant Calendar Access

The service account needs access to the calendars it will manage:

**Option A: Via Google Calendar UI**
1. Open Google Calendar
2. Go to calendar settings
3. Share with service account email (found in JSON key file)
4. Grant "Make changes to events" permission

**Option B: Via Calendar API (if you have the calendar ID)**
```bash
# Use the share_calendar.py utility (create this if needed)
# Or manually add ACL via API
```

## 25Live API Setup

### 1. Obtain 25Live Credentials

Contact your 25Live administrator to get:
- API username
- API password
- Institution identifier (e.g., "georgefox", "university")

### 2. Create Credentials File

```bash
# Create credentials file
nano ~/.config/calpal/25live_credentials

# Add two lines (username, then password):
your_25live_username
your_25live_password

# Secure the file
chmod 600 ~/.config/calpal/25live_credentials

# Verify
cat ~/.config/calpal/25live_credentials
# Should show your username and password (two lines)
```

### 3. Identify Calendar IDs

You need the Google Calendar IDs for your target calendars:

```bash
# List all calendars (requires service account setup)
python3 << EOF
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    '~/.config/calpal/service-account-key.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)
service = build('calendar', 'v3', credentials=creds)

calendars = service.calendarList().list().execute()
for cal in calendars['items']:
    print(f"{cal['summary']}: {cal['id']}")
EOF
```

## Configuration

### 1. Create Configuration File

```bash
# Copy example config
cp config.example.py config.py

# Open for editing
nano config.py
```

### 2. Configure Essential Settings

Edit `config.py`:

```python
# Google Calendar API Settings
GOOGLE_CREDENTIALS_FILE = '/home/youruser/.config/calpal/service-account-key.json'
WORK_CALENDAR_ID = 'your-work-calendar@example.edu'
PERSONAL_CALENDAR_ID = 'your-personal@gmail.com'

# 25Live API Settings
TWENTYFIVE_LIVE_CREDENTIALS_FILE = '/home/youruser/.config/calpal/25live_credentials'
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'  # e.g., 'georgefox'

# Calendar Mappings (update with your actual calendar IDs)
CALENDAR_MAPPINGS = {
    'Classes': 'abc123def456@group.calendar.google.com',
    'Events': 'xyz789uvw012@group.calendar.google.com'
}

# Database Settings
DATABASE_URL = 'postgresql://calpal:your_db_password@localhost:5433/calpal_db'

# Security Settings (generate random tokens!)
SECURE_ENDPOINT_PATH = 'your-random-secure-path-here'
ACCESS_TOKEN = 'your-random-access-token-here'
```

### 3. Generate Security Tokens

```bash
# Generate random tokens
python3 << EOF
import secrets
print(f"SECURE_ENDPOINT_PATH = '{secrets.token_urlsafe(32)}'")
print(f"ACCESS_TOKEN = '{secrets.token_urlsafe(32)}'")
EOF

# Copy these values into config.py
```

### 4. Verify Configuration

```bash
# Test configuration loads
python3 -c "import config; print('Config loaded successfully')"

# Test database connection
python3 -c "from src.db_manager import DatabaseManager; db = DatabaseManager(); db.test_connection()"
```

## Initial Sync

### 1. Test Database Connection

```bash
python3 src/db_manager.py
# Should output: "✅ Database connection successful"
```

### 2. Run Initial 25Live Sync

```bash
# Run with debug logging to see what happens
python3 src/db_aware_25live_sync.py --log-level DEBUG

# Check results
cat db_25live_sync_results.json
```

### 3. Scan Existing Google Calendars

```bash
# Scan all configured calendars
python3 src/calendar_scanner.py

# Check database for imported events
docker exec -it calpal_db psql -U calpal -d calpal_db -c "SELECT COUNT(*) FROM calendar_events WHERE deleted_at IS NULL;"
```

### 4. Generate Initial ICS File

```bash
# Generate ICS file
python3 src/db_aware_wife_ics_generator.py

# Verify ICS file created
ls -lh private/*.ics
```

### 5. Test Web Server

```bash
# Start Flask server
python3 src/calpal_flask_server.py

# In another terminal, test endpoint
curl http://localhost:5001/YOUR_SECURE_PATH/calendar.ics?token=YOUR_ACCESS_TOKEN

# Should return ICS calendar data
```

## Running as a Service

### Option A: Systemd Service (Linux)

Create `/etc/systemd/system/calpal.service`:

```ini
[Unit]
Description=CalPal Calendar Sync Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/CalPal
Environment="PATH=/home/youruser/CalPal/venv/bin:/usr/bin:/bin"
ExecStart=/home/youruser/CalPal/venv/bin/python3 /home/youruser/CalPal/src/unified_db_calpal_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable calpal

# Start service
sudo systemctl start calpal

# Check status
sudo systemctl status calpal

# View logs
sudo journalctl -u calpal -f
```

### Option B: Cron Jobs

```bash
# Edit crontab
crontab -e

# Add entries for each service
# Run 25Live sync every 30 minutes
*/30 * * * * /home/youruser/CalPal/venv/bin/python3 /home/youruser/CalPal/src/db_aware_25live_sync.py >> /home/youruser/CalPal/logs/25live_sync.log 2>&1

# Run calendar scanner every 15 minutes
*/15 * * * * /home/youruser/CalPal/venv/bin/python3 /home/youruser/CalPal/src/calendar_scanner.py >> /home/youruser/CalPal/logs/calendar_scan.log 2>&1

# Generate ICS every 5 minutes
*/5 * * * * /home/youruser/CalPal/venv/bin/python3 /home/youruser/CalPal/src/db_aware_wife_ics_generator.py >> /home/youruser/CalPal/logs/ics_gen.log 2>&1
```

### Option C: Docker Compose (Full Stack)

Create enhanced `docker-compose.yml` with CalPal service:

```yaml
version: '3.8'

services:
  calpal_db:
    image: postgres:15-alpine
    container_name: calpal_db
    environment:
      POSTGRES_USER: calpal
      POSTGRES_PASSWORD: ${DB_PASSWORD:-calpal_dev_password}
      POSTGRES_DB: calpal_db
    ports:
      - "5433:5432"
    volumes:
      - calpal_db_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    restart: unless-stopped

  calpal_service:
    build: .
    container_name: calpal_service
    depends_on:
      - calpal_db
    volumes:
      - ./config.py:/app/config.py:ro
      - ~/.config/calpal:/root/.config/calpal:ro
      - ./private:/app/private
      - ./logs:/app/logs
    environment:
      - DATABASE_URL=postgresql://calpal:${DB_PASSWORD:-calpal_dev_password}@calpal_db:5432/calpal_db
    restart: unless-stopped
    command: python3 src/unified_db_calpal_service.py

volumes:
  calpal_db_data:
```

## Troubleshooting

### Database Connection Issues

```bash
# Check database is running
docker compose ps

# Check database logs
docker compose logs calpal_db

# Test connection manually
docker exec -it calpal_db psql -U calpal -d calpal_db -c "SELECT 1;"

# Restart database
docker compose restart calpal_db
```

### Google API Authentication Errors

```bash
# Verify service account key exists and is valid
python3 << EOF
from google.oauth2.service_account import Credentials
try:
    creds = Credentials.from_service_account_file(
        '~/.config/calpal/service-account-key.json'
    )
    print("✅ Service account key is valid")
    print(f"Service account email: {creds.service_account_email}")
except Exception as e:
    print(f"❌ Error: {e}")
EOF

# Check calendar permissions
# Make sure the service account email has access to calendars
```

### 25Live API Connection Issues

```bash
# Test 25Live credentials
python3 << EOF
import requests
from requests.auth import HTTPBasicAuth

# Read credentials
with open('~/.config/calpal/25live_credentials', 'r') as f:
    username = f.readline().strip()
    password = f.readline().strip()

# Test connection
url = 'https://25live.collegenet.com/your-institution/api/v1/spaces'
response = requests.get(url, auth=HTTPBasicAuth(username, password))
print(f"Status: {response.status_code}")
print(f"Success: {response.status_code == 200}")
EOF
```

### Permission Denied Errors

```bash
# Fix file permissions
chmod 600 ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/25live_credentials
chmod 600 config.py

# Fix directory permissions
chmod 700 ~/.config/calpal
chmod 755 /home/youruser/CalPal
```

### Module Import Errors

```bash
# Verify virtual environment is activated
which python3  # Should show venv path

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Check specific module
python3 -c "import googleapiclient; print(googleapiclient.__version__)"
```

### Database Migration Errors

```bash
# Check current schema
docker exec -it calpal_db psql -U calpal -d calpal_db -c "\d calendar_events"

# Rerun initialization
docker exec -i calpal_db psql -U calpal -d calpal_db < db/init/01_schema.sql

# Apply migrations
for file in db/migrations/*.sql; do
  docker exec -i calpal_db psql -U calpal -d calpal_db < "$file"
done
```

## Next Steps

After successful installation:

1. **Review Configuration**: See [CONFIGURATION.md](CONFIGURATION.md) for advanced options
2. **Understand Services**: Read [SERVICES.md](SERVICES.md) for service details
3. **Database Management**: Check [DATABASE.md](DATABASE.md) for database operations
4. **Security Hardening**: Review [SECURITY.md](SECURITY.md) for production deployment

## Getting Help

- **Documentation**: Check [docs/](../docs/) folder for detailed guides
- **GitHub Issues**: Report bugs and request features
- **Logs**: Check `logs/` directory for error details
- **Database**: Query database for event tracking issues
