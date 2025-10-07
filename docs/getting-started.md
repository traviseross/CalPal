# Getting Started with CalPal

This guide will help you set up and run CalPal for the first time.

## Prerequisites

### Required Software
- **Python 3.8 or higher**
- **PostgreSQL 15+** (or Docker for containerized database)
- **Git** (for cloning the repository)

### Required Accounts & Access
- **Google Cloud Project** with Calendar API enabled
- **Google Service Account** with domain-wide delegation
- **25Live Account** with API access (optional, if using 25Live integration)

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/CalPal.git
cd CalPal
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Set Up Database

#### Option A: Using Docker (Recommended)

```bash
# Start PostgreSQL in Docker container
docker compose up -d

# Verify database is running
docker compose ps
```

The database will be available at `localhost:5433` with the credentials defined in `docker-compose.yml`.

#### Option B: Using Existing PostgreSQL

If you have PostgreSQL already installed:

```bash
# Create database and user
psql -U postgres
CREATE DATABASE calpal_db;
CREATE USER calpal WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE calpal_db TO calpal;
\q
```

Update your `.env` file with the connection string:
```
DATABASE_URL=postgresql://calpal:your_secure_password@localhost:5432/calpal_db
```

### 4. Configure CalPal

```bash
# Copy configuration templates
cp config.example.py config.py
cp .env.example .env
mkdir -p data
cp config/calendars.example.json data/work_subcalendars.json

# Edit configuration files
nano .env
nano config.py
nano data/work_subcalendars.json
```

**Key Configuration Values:**

In `.env`:
```bash
# Database
DATABASE_URL=postgresql://calpal:password@localhost:5433/calpal_db

# Google Calendar IDs (get from calendar settings)
WORK_CALENDAR_ID=your-email@institution.edu
PERSONAL_CALENDAR_ID=personal@gmail.com

# 25Live (if using)
TWENTYFIVE_LIVE_INSTITUTION=your_institution
```

### 5. Set Up Google Service Account

1. **Create a Google Cloud Project** at [console.cloud.google.com](https://console.cloud.google.com)

2. **Enable Google Calendar API:**
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

3. **Create Service Account:**
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Name it "calpal-sync" and create
   - Click on the service account, go to "Keys" tab
   - Click "Add Key" > "Create new key" > "JSON"
   - Download the JSON file

4. **Enable Domain-Wide Delegation:**
   - Edit the service account
   - Check "Enable Google Workspace Domain-wide Delegation"
   - Note the "Client ID" for the next step

5. **Grant Domain-Wide Delegation** (if using Google Workspace):
   - Go to your Google Admin Console
   - Navigate to Security > API Controls > Domain-wide Delegation
   - Add a new API client with the Client ID from step 4
   - Add scope: `https://www.googleapis.com/auth/calendar`

6. **Place credentials file:**
   ```bash
   mkdir -p ~/.config/calpal
   mv ~/Downloads/service-account-key-*.json ~/.config/calpal/service-account-key.json
   ```

### 6. Set Up 25Live Credentials (Optional)

If using 25Live integration:

```bash
# Create credentials file (one line each: username, then password)
echo "your-25live-username" > ~/.config/calpal/25live_credentials
echo "your-25live-password" >> ~/.config/calpal/25live_credentials

# Secure the file
chmod 600 ~/.config/calpal/25live_credentials
```

Copy the 25Live query template:
```bash
cp config/25live_queries.example.json private/25live_queries.json
nano private/25live_queries.json  # Customize for your institution
```

### 7. Initialize Database Schema

The database schema will be created automatically on first run. To test the connection:

```bash
python3 -c "from calpal.core.db_manager import DatabaseManager; db = DatabaseManager(); print('Database connection successful!')"
```

### 8. Test the Setup

Run each component individually to verify setup:

```bash
# Test Calendar Scanner
python3 -m calpal.sync.calendar_scanner --test

# Test 25Live Sync (if using)
python3 -m calpal.sync.twentyfive_live_sync --test

# Test ICS Generator
python3 -m calpal.generators.ics_generator --test
```

## Running CalPal

### Unified Service (Recommended)

Run all components together:

```bash
python3 -m calpal.sync.unified_sync_service
```

This will start the main coordination service that runs all sync components on their schedules.

### Individual Components

Run specific components:

```bash
# 25Live sync only
python3 -m calpal.sync.twentyfive_live_sync

# Calendar scanner only
python3 -m calpal.sync.calendar_scanner

# Event organizer only
python3 -m calpal.organizers.event_organizer

# ICS generator and server
python3 -m calpal.generators.ics_server
```

## Automated Scheduling

### Using Cron (Linux/macOS)

Add to your crontab (`crontab -e`):

```cron
# Run CalPal unified service every 5 minutes
*/5 * * * * cd /home/tradmin/CalPal && /home/tradmin/CalPal/venv/bin/python3 -m calpal.sync.unified_sync_service >> logs/calpal.log 2>&1
```

### Using systemd (Linux)

Create a service file `/etc/systemd/system/calpal.service`:

```ini
[Unit]
Description=CalPal Calendar Sync Service
After=network.target postgresql.service

[Service]
Type=simple
User=tradmin
WorkingDirectory=/home/tradmin/CalPal
Environment="PATH=/home/tradmin/CalPal/venv/bin"
ExecStart=/home/tradmin/CalPal/venv/bin/python3 -m calpal.sync.unified_sync_service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable calpal.service
sudo systemctl start calpal.service
sudo systemctl status calpal.service
```

### Using Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., every 5 minutes)
4. Set action: `python.exe` with arguments `-m calpal.sync.unified_sync_service`
5. Set working directory to your CalPal folder

## Verification

### Check Database

```bash
# Connect to database
docker exec -it calpal_db psql -U calpal -d calpal_db

# Verify tables
\dt

# Check event count
SELECT COUNT(*) FROM calendar_events;
```

### Check Logs

```bash
# View recent logs
tail -f logs/calpal.log

# View specific component logs
tail -f logs/25live_sync.log
tail -f logs/calendar_scanner.log
```

### Check ICS Output

```bash
# Verify ICS file generation
ls -lh private/*.ics

# View ICS file
cat private/schedule.ics
```

## Next Steps

- Read the [Architecture Guide](architecture.md) to understand how components work together
- Review [Configuration Guide](configuration.md) for advanced settings
- Check [Security Guide](security.md) for production deployment best practices
- See [API Reference](api-reference.md) for extending functionality

## Troubleshooting

### Database Connection Failed

```bash
# Check if database is running
docker compose ps

# View database logs
docker compose logs calpal_db

# Restart database
docker compose restart calpal_db
```

### Google Calendar API Errors

```bash
# Verify service account key exists
ls -la ~/.config/calpal/service-account-key.json

# Verify it's valid JSON
python3 -c "import json; json.load(open('/home/tradmin/.config/calpal/service-account-key.json'))"

# Check domain-wide delegation is enabled
# Visit Google Admin Console > Security > API Controls > Domain-wide Delegation
```

### 25Live Authentication Errors

```bash
# Verify credentials file format
cat ~/.config/calpal/25live_credentials
# Should have exactly 2 lines: username, then password

# Test credentials manually
curl -u "username:password" "https://25live.collegenet.com/your_institution/api"
```

### Import Errors

```bash
# Ensure you're in the virtual environment
which python3
# Should show: /home/tradmin/CalPal/venv/bin/python3

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Getting Help

- **Documentation:** Check the `docs/` folder for detailed guides
- **Issues:** Report bugs on GitHub Issues
- **Discussions:** Ask questions in GitHub Discussions
