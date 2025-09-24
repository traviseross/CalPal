# CalPal - 25Live Calendar Sync System

A comprehensive calendar synchronization system that syncs events from CollegeNET 25Live to Google Calendar and generates clean ICS files for external calendar sharing.

## 🎯 Purpose

CalPal automates the complex process of:
- Syncing class schedules and university events from 25Live to Google Calendar
- Creating clean, filtered ICS files for calendar sharing
- Maintaining event tracking and duplicate prevention
- Providing a secure web interface for calendar access

## 🏗️ Architecture

```
CalPal/
├── src/                    # Core application modules
│   ├── twentyfive_live_sync.py      # 25Live API sync service
│   ├── wife_calendar_ics_service.py # ICS generation service
│   ├── calpal_flask_server.py       # Web server for ICS hosting
│   └── run_wife_calendar_service.py # Continuous sync daemon
├── docs/                   # Documentation
├── data/                   # System tracking files (git-ignored)
├── private/               # Sensitive data (git-ignored)
└── archives/              # Development files (git-ignored)
```

## ✨ Features

### 25Live Integration
- **Classes Sync**: Automatically syncs teaching schedules to a dedicated Google Calendar
- **University Events**: Syncs campus events from multiple 25Live queries
- **Duplicate Prevention**: Advanced signature-based duplicate detection
- **Date Range Management**: Respects 25Live's 20-week API limits with intelligent batching

### ICS Generation
- **Event Filtering**: Clean event categorization and filtering
- **Custom Formatting**:
  - Classes → "In class" (no location details)
  - University Events → "Fox Event" (with location)
  - Other Work Events → "In a meeting" (with location)
- **Privacy Protection**: Filters out personal calendar events completely

### Web Interface
- **Secure Access**: Token-based authentication for ICS file access
- **Auto-Generation**: Keeps ICS files updated automatically
- **Public URLs**: Provides shareable calendar URLs

## 📋 Event Processing Flow

```
25Live → Google Calendar → ICS Generation
   ↓            ↓               ↓
Classes      Classes         "In class"
GFU Events → GFU Events  →   "Fox Event"
              ↓               ↓
           Work Calendar → "In a meeting"
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Google Calendar API access
- 25Live API credentials
- George Fox University institutional access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/traviseross/CalPal.git
   cd CalPal
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**
   ```bash
   cp config.example.py config.py
   # Edit config.py with your settings
   ```

4. **Set up Google API credentials**
   - Place your service account key at `~/.config/calpal/service-account-key.json`
   - Add 25Live credentials to `~/.config/calpal/25live_credentials`

### Usage

#### One-time Sync
```bash
python3 src/twentyfive_live_sync.py
```

#### Generate ICS File
```bash
python3 src/wife_calendar_ics_service.py
```

#### Run Web Server
```bash
python3 src/calpal_flask_server.py
```

#### Continuous Sync Service
```bash
python3 src/run_wife_calendar_service.py --interval 15
```

## ⚙️ Configuration

### Required Settings

```python
# Google Calendar API
GOOGLE_CREDENTIALS_FILE = '~/.config/calpal/service-account-key.json'
WORK_CALENDAR_ID = 'your-work-calendar@example.edu'

# 25Live API
TWENTYFIVE_LIVE_CREDENTIALS_FILE = '~/.config/calpal/25live_credentials'
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'

# Calendar Mappings
CALENDAR_MAPPINGS = {
    'Classes': 'classes-calendar-id@group.calendar.google.com',
    'GFU Events': 'events-calendar-id@group.calendar.google.com'
}
```

### Security Configuration

```python
# Secure endpoint access
SECURE_ENDPOINT_PATH = 'your-secure-random-path'
ACCESS_TOKEN = 'your-secure-access-token'
```

## 🔒 Security Features

- **Credential Isolation**: All sensitive data stored outside repository
- **Token Authentication**: Secure access to calendar endpoints
- **Personal Data Filtering**: Removes personal calendar events from ICS output
- **Gitignore Protection**: Sensitive directories completely excluded from version control

## 📅 Event Categories

| Source | Google Calendar | ICS Output | Location | Details |
|--------|----------------|------------|----------|---------|
| Classes | Classes Calendar | "In class" | Hidden | None |
| 25Live Events | GFU Events Calendar | "Fox Event" | Shown | None |
| Work Events | Work Calendar | "In a meeting" | Shown | None |
| Personal Events | - | Filtered Out | - | - |

## 🔧 Advanced Features

### Deletion Detection
- Automatically detects when events are removed from source calendars
- Cleans up corresponding mirror events
- Maintains deletion history for learning

### Date Range Optimization
- Scans 12 months forward for comprehensive coverage
- Intelligently batches requests to respect API limits
- Automatically adjusts ranges based on actual event data

### Event Tracking
- JSON-based tracking system for event signatures
- Duplicate prevention across calendar rebuilds
- Comprehensive logging for debugging

## 🏫 George Fox University Integration

This system is specifically designed for George Fox University's:
- 25Live calendar system
- Institutional Google Workspace
- Academic calendar requirements
- Campus event management

## 📝 Development

### File Structure
- `src/twentyfive_live_sync.py` - Core sync engine with API integration
- `src/wife_calendar_ics_service.py` - ICS generation with filtering rules
- `src/calpal_flask_server.py` - Web server for secure calendar hosting
- `src/run_wife_calendar_service.py` - Daemon for continuous operation

### Testing
Run individual components for testing:
```bash
# Test 25Live connection
python3 src/twentyfive_live_sync.py --test

# Generate test ICS
python3 src/wife_calendar_ics_service.py --log-level DEBUG

# Test web server
python3 src/calpal_flask_server.py --debug
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is designed for George Fox University's internal calendar management needs.

## 📞 Support

For questions or issues:
- Check the documentation in `docs/`
- Review configuration examples
- Ensure all credentials are properly configured

---

*Built with Python, Google Calendar API, and Flask for reliable academic calendar management.*