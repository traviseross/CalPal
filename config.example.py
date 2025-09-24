"""
Example configuration for CalPal 25Live Sync System.
Copy this file to config.py and customize with your own settings.
"""

import os
from pathlib import Path

# Base configuration directory - where credentials will be stored
CONFIG_DIR = os.path.expanduser('~/.config/calpal')

# Google Calendar API Settings
GOOGLE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'service-account-key.json')
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']

# 25Live API Settings
TWENTYFIVE_LIVE_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, '25live_credentials')
TWENTYFIVE_LIVE_BASE_URL = 'https://25live.collegenet.com'
TWENTYFIVE_LIVE_INSTITUTION = 'your-institution'  # e.g., 'georgefox', 'stanford', etc.

# Calendar Settings - Replace with your actual Google Calendar IDs
CALENDAR_MAPPINGS = {
    'Classes': 'your-classes-calendar-id@group.calendar.google.com',
    'GFU Events': 'your-events-calendar-id@group.calendar.google.com'
}

# Work Calendar (the calendar to pull events from for ICS generation)
WORK_CALENDAR_ID = 'your-work-email@your-domain.com'

# Flask Server Settings
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5001
ICS_FILE_PATH = os.path.expanduser('~/your_schedule.ics')

# Security Settings - CHANGE THESE TO SECURE RANDOM VALUES
SECURE_ENDPOINT_PATH = 'generate-a-random-string-here'  # e.g., 'zj9ETjqLo2EFWwwUtMORWgnI94ji_4Obbsanw5ld8EM'
ACCESS_TOKEN = 'generate-another-random-token'  # e.g., 'd3ef69c2d848e8db'

# File Paths
PROJECT_ROOT = Path(__file__).parent
METADATA_DIR = PROJECT_ROOT / 'metadata'
LOGS_DIR = PROJECT_ROOT / 'logs'

# Ensure directories exist
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Event Processing Settings
EVENT_FILTER_KEYWORDS = [
    'committee', 'governance', 'council', 'board', 'senate', 'faculty'
]

# Sync Settings
SYNC_LOOKBACK_DAYS = 30
SYNC_LOOKAHEAD_DAYS = 365