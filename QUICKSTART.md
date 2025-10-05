# CalPal Quick Start Guide

Get CalPal running in 15 minutes.

## Prerequisites

Install these before starting:
- **Python 3.8+**: `python3 --version`
- **Docker**: `docker --version`
- **Git**: `git --version`

## Step 1: Clone and Setup (2 minutes)

```bash
# Clone repository
git clone https://github.com/yourusername/CalPal.git
cd CalPal

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Start Database (1 minute)

```bash
# Start PostgreSQL in Docker
docker compose up -d

# Verify it's running
docker compose ps
```

## Step 3: Get Google Credentials (5 minutes)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project (or select existing)
3. Enable Google Calendar API
4. Create service account
5. Download JSON key

```bash
# Store credentials
mkdir -p ~/.config/calpal
mv ~/Downloads/your-key.json ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/service-account-key.json
```

## Step 4: Configure CalPal (5 minutes)

```bash
# Copy config template
cp config.example.py config.py

# Edit config
nano config.py
```

**Minimum required changes:**
```python
# Your work calendar
WORK_CALENDAR_ID = 'yourname@example.edu'

# Your institution (if using 25Live)
TWENTYFIVE_LIVE_INSTITUTION = 'yourinstitution'

# Generate security tokens
import secrets
SECURE_ENDPOINT_PATH = secrets.token_urlsafe(32)  # Run this in Python
ACCESS_TOKEN = secrets.token_urlsafe(32)          # Run this in Python
```

**Optional: 25Live credentials** (skip if not using 25Live)
```bash
echo "your_username" > ~/.config/calpal/25live_credentials
echo "your_password" >> ~/.config/calpal/25live_credentials
chmod 600 ~/.config/calpal/25live_credentials
```

## Step 5: Grant Calendar Access (2 minutes)

Give your service account access to calendars:

1. Open Google Calendar
2. Settings → Calendar settings
3. Share with service account email (from JSON key file)
4. Grant "Make changes to events" permission

## Step 6: Test Configuration (1 minute)

```bash
# Test database
python3 -c "from src.db_manager import DatabaseManager; db = DatabaseManager(); print('✅ Database OK' if db.test_connection() else '❌ Database failed')"

# Test config
python3 -c "import config; print('✅ Config OK')"
```

## Step 7: Run CalPal (1 minute)

```bash
# Start unified service
python3 src/unified_db_calpal_service.py
```

You should see:
```
✅ Database manager initialized
✅ Unified CalPal Service initialized
🔄 Starting unified service loop...
```

Press `Ctrl+C` to stop.

## Verify It's Working

### Check database has events

```bash
docker exec -it calpal_db psql -U calpal -d calpal_db -c \
  "SELECT COUNT(*) as events FROM calendar_events WHERE deleted_at IS NULL;"
```

### Generate ICS file

```bash
python3 src/db_aware_wife_ics_generator.py
ls -lh private/*.ics
```

### Start web server

```bash
python3 src/calpal_flask_server.py
```

In another terminal:
```bash
# Test endpoint (replace with your tokens)
curl "http://localhost:5001/YOUR_SECURE_PATH/calendar.ics?token=YOUR_TOKEN"
```

## Common Issues

**Database connection failed**
```bash
docker compose logs calpal_db
docker compose restart calpal_db
```

**Config not found**
```bash
ls config.py  # Should exist
cp config.example.py config.py  # If missing
```

**Permission denied**
```bash
chmod 600 ~/.config/calpal/service-account-key.json
chmod 600 config.py
```

**No events in database**
```bash
# Run initial scan
python3 src/calendar_scanner.py
```

## Next Steps

### Run as a service

**Option 1: Systemd (Linux)**
```bash
sudo nano /etc/systemd/system/calpal.service
```

```ini
[Unit]
Description=CalPal Calendar Sync
After=network.target docker.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/CalPal
Environment="PATH=/home/youruser/CalPal/venv/bin:/usr/bin"
ExecStart=/home/youruser/CalPal/venv/bin/python3 src/unified_db_calpal_service.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable calpal
sudo systemctl start calpal
sudo systemctl status calpal
```

**Option 2: Cron (simpler)**
```bash
crontab -e
```

```cron
# Run every 15 minutes
*/15 * * * * cd /home/youruser/CalPal && venv/bin/python3 src/unified_db_calpal_service.py --once >> logs/cron.log 2>&1
```

### Customize event organization

Edit `src/work_event_organizer.py` to customize:
- Which events move to which subcalendars
- Event classification rules
- Mirror behavior

### Customize ICS output

Edit `src/db_aware_wife_ics_generator.py` to customize:
- Event filtering
- Event transformations
- Privacy settings

## Documentation

- **Full installation**: [docs/INSTALLATION.md](docs/INSTALLATION.md)
- **Configuration options**: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- **Service details**: [docs/SERVICES.md](docs/SERVICES.md)
- **Database guide**: [docs/DATABASE.md](docs/DATABASE.md)
- **Security practices**: [docs/SECURITY.md](docs/SECURITY.md)

## Getting Help

- **Documentation**: Check `docs/` folder
- **Issues**: [GitHub Issues](https://github.com/yourusername/CalPal/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/CalPal/discussions)

## Quick Command Reference

```bash
# Start database
docker compose up -d

# Stop database
docker compose down

# Run unified service
python3 src/unified_db_calpal_service.py

# Run specific service
python3 src/calendar_scanner.py
python3 src/db_aware_25live_sync.py
python3 src/db_aware_wife_ics_generator.py

# Generate ICS
python3 src/db_aware_wife_ics_generator.py

# Start web server
python3 src/calpal_flask_server.py

# Check database
docker exec -it calpal_db psql -U calpal -d calpal_db

# View logs
tail -f logs/calpal.log

# Backup database
docker exec calpal_db pg_dump -U calpal calpal_db > backup.sql
```

---

**That's it! CalPal is now running and syncing your calendars.** 🎉

For more detailed documentation, see the `docs/` folder.
