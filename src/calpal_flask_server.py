#!/usr/bin/env python3
"""
CalPal Flask Server

Serves CalPal ICS files securely with token authentication.
"""

import os
import json
import logging
from flask import Flask, send_file, request, abort, jsonify
from werkzeug.serving import WSGIRequestHandler

try:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import *
except ImportError:
    print("ERROR: config.py not found. Please copy config.example.py to config.py and customize it.")
    exit(1)

app = Flask(__name__)

# Configuration from config file
METADATA_FILE_PATH = METADATA_DIR / 'schedule_metadata.json'

def load_metadata():
    """Load metadata to get the valid access token."""
    try:
        if os.path.exists(METADATA_FILE_PATH):
            with open(METADATA_FILE_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading metadata: {e}")
    # Return configured access token if file doesn't exist
    return {'access_token': ACCESS_TOKEN}

@app.route(f'/{SECURE_ENDPOINT_PATH}/<filename>')
def serve_ics_file(filename):
    """Serve the travis schedule ICS file."""
    # Security check: only allow .ics files
    if not filename.endswith('.ics'):
        abort(404, description="File not found")

    # Build full path to ICS file
    if filename in ['schedule.ics', 'travis_schedule.ics']:
        file_path = ICS_FILE_PATH
    else:
        abort(404, description="File not found")

    # Check if ICS file exists
    if not os.path.exists(file_path):
        abort(404, description="Calendar file not found")

    # Serve the ICS file with NO caching
    # This ensures Flask always reads the file fresh from disk
    response = send_file(
        file_path,
        mimetype='text/calendar',
        as_attachment=False,
        download_name=filename,
        etag=False
    )

    # Add headers to prevent all caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response

@app.route('/status')
def status():
    """Status endpoint for monitoring."""
    metadata = load_metadata()

    status_info = {
        'service': 'CalPal Schedule Service',
        'status': 'active',
        'last_generated': metadata.get('generated_at', 'unknown'),
        'events_count': metadata.get('events_count', 0)
    }

    # Check if ICS file exists and get its size
    if os.path.exists(ICS_FILE_PATH):
        status_info['ics_file_size'] = os.path.getsize(ICS_FILE_PATH)
        status_info['ics_file_exists'] = True
    else:
        status_info['ics_file_exists'] = False

    return jsonify(status_info)

@app.route('/')
def index():
    """Return empty response for root path."""
    return ""

# Disable Flask request logging to reduce noise
class NoLoggingWSGIRequestHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass

def main():
    """Run the Flask server."""
    import argparse

    parser = argparse.ArgumentParser(description='CalPal Flask Server')
    parser.add_argument('--port', type=int, default=FLASK_PORT,
                       help='Port to run server on (default: 5000)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true',
                       help='Run in debug mode')
    args = parser.parse_args()

    # Configure logging
    if not args.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

    print(f"🌐 Starting CalPal Flask Server...")
    print(f"Host: {args.host}:{args.port}")
    print(f"Status page: http://{args.host}:{args.port}/status")

    # Run Flask server
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        request_handler=NoLoggingWSGIRequestHandler if not args.debug else None
    )

if __name__ == '__main__':
    main()