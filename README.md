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
- **Deletion Detection & Removal**: Automatically detects and removes deleted events from both database and Google Calendar
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
├── calpal/                        # Main package
│   ├── core/                          # Core database and infrastructure
│   │   └── db_manager.py                  # Database operations
│   ├── sync/                          # Synchronization services
│   │   ├── twentyfive_live_sync.py        # 25Live API integration
│   │   ├── calendar_scanner.py            # Google Calendar scanning
│   │   ├── calendar_writer.py             # Calendar write operations
│   │   └── unified_sync_service.py        # Main coordinating service
│   ├── organizers/                    # Event organization logic
│   │   ├── event_organizer.py             # Event sorting and routing
│   │   ├── mirror_manager.py              # Calendar mirroring
│   │   ├── subcalendar_sync.py            # Subcalendar synchronization
│   │   └── reconciler.py                  # Calendar reconciliation
│   └── generators/                    # ICS file generation
│       ├── ics_generator.py               # Database-backed ICS generation
│       └── ics_server.py                  # Flask web server for ICS hosting
├── tools/                         # Utility scripts
│   └── manage_blacklist.py            # Event blacklist management
├── config/                        # Configuration templates
│   ├── calendars.example.json         # Calendar ID template
│   └── 25live_queries.example.json    # 25Live query template
├── docs/                          # Documentation (to be created)
│   ├── architecture.md                # System architecture
│   ├── getting-started.md             # Quick start guide
│   └── api-reference.md               # API documentation
├── db/                            # Database setup
│   ├── init/                          # Schema initialization
│   └── migrations/                    # Database migrations
├── config.example.py              # Configuration template
├── .env.example                   # Environment variables template
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
   # Copy configuration templates
   cp config.example.py config.py
   cp .env.example .env
   cp config/calendars.example.json data/work_subcalendars.json

   # Edit config files with your institution's settings
   nano config.py
   nano .env
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
   # Create 25live_credentials file with username and password (one per line)
   echo "your-username" > ~/.config/calpal/25live_credentials
   echo "your-password" >> ~/.config/calpal/25live_credentials
   ```

6. **Run the unified service**
   ```bash
   # Using the main entry point (recommended)
   python3 -m calpal.sync.unified_sync_service

   # Or run individual components
   python3 -m calpal.sync.twentyfive_live_sync  # 25Live sync only
   python3 -m calpal.sync.calendar_scanner      # Calendar scanning only
   ```

For detailed installation instructions, see [docs/getting-started.md](docs/getting-started.md).

## Documentation

- **[Getting Started](docs/getting-started.md)** - Quick start guide and basic setup
- **[Architecture Guide](docs/architecture.md)** - System design and components
- **[API Reference](docs/api-reference.md)** - Developer API documentation
- **[Configuration Guide](docs/configuration.md)** - All configuration options
- **[Security Guide](docs/security.md)** - Security best practices

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

See [docs/configuration.md](docs/configuration.md) for complete configuration reference.

## Security

CalPal implements multiple security layers:

- **Credential Isolation**: All sensitive data stored outside repository
- **Token Authentication**: Secure access to web endpoints
- **Database Security**: Encrypted connections and credential management
- **API Key Protection**: Service account keys never committed to git
- **Environment Separation**: Development vs production configurations

For detailed security information, see [docs/security.md](docs/security.md).

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
| **Calendar Scanner** | Scan Google Calendars for changes/deletions, remove deleted events | Every 15 minutes |
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

For more troubleshooting, see [docs/architecture.md](docs/architecture.md).

## Contributing

We welcome contributions! CalPal is an open-source project that benefits from community involvement.

**Quick Contribution Guide:**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with clear commit messages
4. Ensure all imports use the `calpal.` package structure
5. Update documentation as needed
6. Submit a pull request with a clear description

## FAQ

**Q: Can I use this without 25Live?**
A: The 25Live integration is optional. You can use CalPal just for Google Calendar organization and ICS generation.

**Q: What happens if I manually delete a synced event?**
A: CalPal's Calendar Scanner automatically detects when events are deleted from Google Calendar and marks them as deleted in the database. This prevents them from being re-created and ensures bidirectional sync stays consistent.

**Q: Can I customize the ICS output format?**
A: Yes! Edit the filtering rules in `calpal/generators/ics_generator.py` to customize event transformations.

**Q: How do I back up my CalPal database?**
A: See [docs/architecture.md](docs/architecture.md) for database backup procedures.

**Q: Is this suitable for production use?**
A: CalPal is production-ready. Ensure you follow the security guidelines in [docs/security.md](docs/security.md).

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