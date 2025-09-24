# CalPal Setup Guide

This guide will help you set up your own instance of the CalPal 25Live sync system.

## Prerequisites

- Python 3.8+
- Google Calendar API access
- 25Live API access (institutional account)
- A web server for hosting ICS files (optional)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd CalPal
   ```

2. **Create a Python virtual environment**
   ```bash
   python3 -m venv .
   source bin/activate  # On Windows: bin\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Create your configuration file**
   ```bash
   cp config.example.py config.py
   ```

2. **Edit config.py with your settings:**
   - **TWENTYFIVE_LIVE_INSTITUTION**: Your institution's identifier in 25Live
   - **CALENDAR_MAPPINGS**: Your Google Calendar IDs
   - **WORK_CALENDAR_ID**: The calendar to pull events from for ICS generation
   - **SECURE_ENDPOINT_PATH**: A random string for securing your ICS endpoints
   - **ACCESS_TOKEN**: A random token for API access

3. **Set up Google Calendar API credentials**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or use an existing one
   - Enable the Google Calendar API
   - Create a service account
   - Download the service account key as JSON
   - Save it as `~/.config/calpal/service-account-key.json`

4. **Set up 25Live credentials**
   - Create the file `~/.config/calpal/25live_credentials`
   - Add two lines:
     ```
     your_username
     your_password
     ```

## Usage

### Running the sync service
```bash
python3 twentyfive_live_sync.py
```

### Running the Flask server
```bash
python3 calpal_flask_server.py --port 5001 --host 0.0.0.0
```

### Generating ICS files
```bash
python3 wife_calendar_ics_service.py
```

## Security Notes

- Never commit `config.py` to version control
- Keep your credentials files secure and outside the project directory
- Use strong random tokens for `ACCESS_TOKEN` and `SECURE_ENDPOINT_PATH`
- The generated ICS files may contain sensitive calendar information

## File Structure

- `config.py` - Your configuration (not in git)
- `config.example.py` - Example configuration template
- `twentyfive_live_sync.py` - Main sync service
- `calpal_flask_server.py` - Web server for serving ICS files
- `wife_calendar_ics_service.py` - ICS file generation
- `docs/25Live_Classes_Sync.md` - Detailed documentation for Classes-only usage

## Troubleshooting

1. **"config.py not found" error**
   - Make sure you copied `config.example.py` to `config.py` and customized it

2. **Authentication errors**
   - Verify your Google service account key is in the correct location
   - Check that your 25Live credentials are correct

3. **Calendar not found errors**
   - Ensure your calendar IDs in `config.py` are correct
   - Verify the service account has access to the calendars

For more detailed usage and programming interface documentation, see `docs/25Live_Classes_Sync.md`.