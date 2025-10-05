# CalPal - 25Live Calendar Sync System

A comprehensive, database-backed calendar synchronization system that syncs events from CollegeNET 25Live to Google Calendar and generates clean ICS files for external calendar sharing.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Configuration](#configuration)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Overview

CalPal automates complex calendar management workflows for academic institutions using CollegeNET 25Live. It provides intelligent event synchronization, duplicate prevention, database-backed event tracking, and flexible ICS generation for calendar sharing.

**Perfect for:**
- Academic institutions using 25Live for course scheduling
- Faculty/staff managing multiple calendar sources
- Organizations needing automated calendar aggregation
- Anyone requiring filtered calendar views for external sharing

## Key Features

### Database-Backed Event Tracking
- **PostgreSQL Database**: Single source of truth for all calendar events
- **Intelligent Sync**: Tracks event lifecycle (created, moved, deleted, updated)
- **Bidirectional Detection**: Identifies changes in both Google Calendar and 25Live
- **Audit Trail**: Complete history of all event operations

### 25Live Integration
- **Automated Class Sync**: Pull teaching schedules into Google Calendar
- **Event Synchronization**: Sync campus/university events from 25Live queries
- **Smart Duplicate Prevention**: Signature-based detection using 25Live reservation IDs
- **API Limit Management**: Intelligent batching respects 25Live's date range constraints

### Calendar Organization
- **Automatic Event Sorting**: Routes events to appropriate subcalendars
- **Booking Management**: Identifies and organizes appointment-type events
- **Mirror Subcalendars**: Creates organized views across multiple calendars
- **Attendee Event Handling**: Intelligently manages meeting invitations

### ICS Generation
- **Filtered Calendar Views**: Generate clean ICS files for external sharing
- **Custom Event Formatting**: Transform event details for privacy/clarity
- **Privacy Protection**: Exclude personal events from shared calendars
- **Flexible Rules**: Configurable filtering and transformation logic

### Web Interface
- **Secure ICS Hosting**: Token-based authentication for calendar URLs
- **Continuous Updates**: Auto-refreshes ICS files on schedule
- **Flask Server**: Lightweight web server for calendar distribution

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    CalPal Architecture                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   25Live     │      │    Google    │                     │
│  │   Calendar   │◄────►│   Calendar   │                     │
│  │     API      │      │     API      │                     │
│  └──────────────┘      └──────────────┘                     │
│         │                      │                             │
│         └──────────┬───────────┘                            │
│                    ▼                                         │
│         ┌────────────────────┐                              │
│         │  PostgreSQL DB     │◄─── Single Source of Truth   │
│         │  Event Tracking    │                              │
│         └────────────────────┘                              │
│                    │                                         │
│         ┌──────────┴──────────┐                             │
│         ▼                     ▼                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ Event        │      │ ICS          │                     │
│  │ Organizer    │      │ Generator    │                     │
│  └──────────────┘      └──────────────┘                     │
│         │                      │                             │
│         └──────────┬───────────┘                            │
│                    ▼                                         │
│         ┌────────────────────┐                              │
│         │  Flask Web Server  │                              │
│         │  (ICS Hosting)     │                              │
│         └────────────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
CalPal/
├── src/                           # Core application modules
│   ├── unified_db_calpal_service.py    # Main coordinating service
│   ├── db_aware_25live_sync.py         # 25Live to database sync
│   ├── calendar_scanner.py             # Google Calendar scanner
│   ├── work_event_organizer.py         # Event organization logic
│   ├── db_aware_wife_ics_generator.py  # Database-backed ICS generation
│   ├── db_manager.py                   # Database operations
│   └── calpal_flask_server.py          # Web server for ICS hosting
├── docs/                          # Documentation
│   ├── DATABASE.md                     # Database schema & operations
│   ├── INSTALLATION.md                 # Setup instructions
│   ├── CONFIGURATION.md                # Configuration guide
│   └── SERVICES.md                     # Service documentation
├── db/                            # Database files
│   ├── init/                           # Schema initialization
│   └── migrations/                     # Database migrations
├── config.example.py              # Configuration template
├── requirements.txt               # Python dependencies
└── docker-compose.yml             # Database container setup
```

## Quick Start

### Prerequisites

- **Python 3.8+**
- **PostgreSQL 15+** (or use included Docker setup)
- **Google Cloud Project** with Calendar API enabled
- **25Live Account** with API access
- **Docker & Docker Compose** (optional, for database)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/CalPal.git
   cd CalPal
   ```

2. **Set up Python environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure CalPal**
   ```bash
   cp config.example.py config.py
   # Edit config.py with your institution's settings
   ```

4. **Start the database**
   ```bash
   docker compose up -d
   # Database will be available on localhost:5433
   ```

5. **Set up credentials**
   ```bash
   mkdir -p ~/.config/calpal
   # Place service-account-key.json in ~/.config/calpal/
   # Create 25live_credentials file with username and password
   ```

6. **Run the unified service**
   ```bash
   python3 src/unified_db_calpal_service.py
   ```

For detailed installation instructions, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Documentation

- **[Installation Guide](docs/INSTALLATION.md)** - Complete setup instructions
- **[Configuration Guide](docs/CONFIGURATION.md)** - All configuration options
- **[Database Documentation](docs/DATABASE.md)** - Database schema and operations
- **[Services Documentation](docs/SERVICES.md)** - Service components and APIs
- **[Security Guide](docs/SECURITY.md)** - Security best practices
- **[Contributing Guidelines](docs/CONTRIBUTING.md)** - How to contribute

## Configuration

CalPal uses a centralized `config.py` file for all settings. Key configuration areas:

```python
# Google Calendar API
GOOGLE_CREDENTIALS_FILE = '~/.config/calpal/service-account-key.json'
WORK_CALENDAR_ID = 'your-work-calendar@example.edu'

# 25Live API
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'
TWENTYFIVE_LIVE_CREDENTIALS_FILE = '~/.config/calpal/25live_credentials'

# Database
DATABASE_URL = 'postgresql://user:password@localhost:5433/calpal_db'

# Calendar Mappings
CALENDAR_MAPPINGS = {
    'Classes': 'classes-calendar-id@group.calendar.google.com',
    'Events': 'events-calendar-id@group.calendar.google.com'
}
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for complete configuration reference.

## Security

CalPal implements multiple security layers:

- **Credential Isolation**: All sensitive data stored outside repository
- **Token Authentication**: Secure access to web endpoints
- **Database Security**: Encrypted connections and credential management
- **API Key Protection**: Service account keys never committed to git
- **Environment Separation**: Development vs production configurations

For detailed security information, see [docs/SECURITY.md](docs/SECURITY.md).

## Use Cases

### Academic Institutions
- Sync course schedules from 25Live to faculty Google Calendars
- Aggregate campus events for administrative staff
- Generate filtered calendar feeds for students and parents

### Individual Faculty/Staff
- Consolidate multiple calendar sources into one view
- Automatically organize booking/appointment events
- Share availability without exposing sensitive details

### Departments
- Track course offerings across departments
- Monitor room bookings and space utilization
- Coordinate campus events and activities

## Service Components

CalPal operates as a unified service with multiple coordinated components:

### Core Services

| Service | Purpose | Run Frequency |
|---------|---------|---------------|
| **25Live Sync** | Pull events from 25Live API into database | Every 30 minutes |
| **Calendar Scanner** | Scan Google Calendars for changes/deletions | Every 15 minutes |
| **Personal/Family Mirror** | Mirror personal/family events to subcalendars | Every 10 minutes |
| **Work Event Organizer** | Sort and organize work calendar events | Every 5 minutes |
| **Subcalendar Sync** | Ensure subcalendars mirrored to work calendar | Every 10 minutes |
| **ICS Generator** | Generate filtered ICS files from database | Every 5 minutes |

All services use the PostgreSQL database as the single source of truth.

## Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
# Check database is running
docker compose ps
docker compose logs calpal_db

# Restart database
docker compose down && docker compose up -d
```

**Google Calendar API Errors**
```bash
# Verify service account key exists
ls -la ~/.config/calpal/service-account-key.json

# Check calendar permissions in Google Admin Console
```

**25Live Authentication Errors**
```bash
# Verify credentials file format (two lines: username, password)
cat ~/.config/calpal/25live_credentials
```

For more troubleshooting, see [docs/SERVICES.md](docs/SERVICES.md).

## Contributing

We welcome contributions! Please see [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

**Quick Contribution Guide:**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with clear commit messages
4. Add tests for new functionality
5. Update documentation as needed
6. Submit a pull request

## FAQ

**Q: Can I use this without 25Live?**
A: The 25Live integration is optional. You can use CalPal just for Google Calendar organization and ICS generation.

**Q: What happens if I manually delete a synced event?**
A: CalPal's database tracking detects deletions. The event will be marked as deleted and won't be re-created unless it appears again in the source.

**Q: Can I customize the ICS output format?**
A: Yes! Edit the filtering rules in `src/db_aware_wife_ics_generator.py` to customize event transformations.

**Q: How do I back up my CalPal database?**
A: See [docs/DATABASE.md](docs/DATABASE.md#backup-and-restore) for backup procedures.

**Q: Is this suitable for production use?**
A: CalPal is production-ready. Ensure you follow the security guidelines in [docs/SECURITY.md](docs/SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

- Built with [Google Calendar API](https://developers.google.com/calendar)
- Integrated with [CollegeNET 25Live](https://www.collegenet.com/products/series25/)
- Database: [PostgreSQL](https://www.postgresql.org/)
- Web framework: [Flask](https://flask.palletsprojects.com/)
- Calendar generation: [iCalendar](https://github.com/collective/icalendar)

## Support

- **Documentation**: Full documentation in [`docs/`](docs/)
- **Issues**: Report bugs via [GitHub Issues](https://github.com/yourusername/CalPal/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/yourusername/CalPal/discussions)

---

**Built with Python, PostgreSQL, and Google Calendar API for reliable academic calendar management.**