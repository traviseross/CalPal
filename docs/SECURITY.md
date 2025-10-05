# CalPal Security Guide

Comprehensive security best practices and guidelines for deploying CalPal.

## Table of Contents

- [Security Overview](#security-overview)
- [Credential Management](#credential-management)
- [API Security](#api-security)
- [Database Security](#database-security)
- [Network Security](#network-security)
- [File Permissions](#file-permissions)
- [Web Server Security](#web-server-security)
- [Secrets Management](#secrets-management)
- [Audit Logging](#audit-logging)
- [Incident Response](#incident-response)
- [Security Checklist](#security-checklist)

## Security Overview

CalPal handles sensitive calendar data and API credentials. Follow these guidelines to ensure secure deployment.

### Security Principles

1. **Defense in Depth**: Multiple layers of security
2. **Least Privilege**: Minimum necessary permissions
3. **Secure by Default**: Safe defaults, explicit opt-in for risky features
4. **Separation of Concerns**: Credentials isolated from code
5. **Audit Trail**: Complete logging of all operations

### Threat Model

**Assets to Protect:**
- Google Calendar API credentials (service account key)
- 25Live API credentials (username/password)
- Database credentials
- Calendar event data
- Web server access tokens
- ICS files (may contain sensitive scheduling info)

**Threat Actors:**
- External attackers (network-based)
- Malicious insiders (with system access)
- Accidental exposure (git commits, logs, backups)

**Attack Vectors:**
- Credential theft
- Unauthorized API access
- Database compromise
- Man-in-the-middle attacks
- Social engineering

## Credential Management

### Service Account Key

**Never commit service account keys to git!**

```bash
# Correct: Store outside repository
~/.config/calpal/service-account-key.json

# Incorrect: In repository
/home/user/CalPal/service-account-key.json  # NEVER DO THIS
```

**Secure storage:**

```bash
# Create secure config directory
mkdir -p ~/.config/calpal
chmod 700 ~/.config/calpal

# Copy service account key
cp ~/Downloads/service-account-key.json ~/.config/calpal/
chmod 600 ~/.config/calpal/service-account-key.json

# Verify permissions
ls -la ~/.config/calpal/
# Should show: drwx------ (directory)
#              -rw------- (file)
```

**Key rotation:**

```bash
# Rotate service account key every 90 days
# 1. Create new key in Google Cloud Console
# 2. Download new key
# 3. Update CalPal configuration
# 4. Test with new key
# 5. Delete old key from Google Cloud Console
# 6. Securely delete old key file
shred -vfz -n 10 ~/.config/calpal/service-account-key.json.old
```

### 25Live Credentials

**Never log credentials!**

```bash
# Correct: Secure credentials file
~/.config/calpal/25live_credentials
chmod 600 ~/.config/calpal/25live_credentials

# Verify no credentials in logs
grep -r "password" logs/
# Should return nothing
```

**Credential format:**

```bash
# Two lines: username, password
username
password

# NOT:
username:password  # Incorrect format
```

**Access control:**

```bash
# Only user should access
chmod 600 ~/.config/calpal/25live_credentials
chown youruser:youruser ~/.config/calpal/25live_credentials
```

### Configuration File Security

**config.py contains sensitive settings:**

```python
# Generate strong random tokens
import secrets

# Generate 32-byte (256-bit) tokens
SECURE_ENDPOINT_PATH = secrets.token_urlsafe(32)
ACCESS_TOKEN = secrets.token_urlsafe(32)

# Example output:
# SECURE_ENDPOINT_PATH = 'Xj8kZ3pQ9mR2vL5nB7yH4wT6cF1dK0sA2eG9uN3xM8'
# ACCESS_TOKEN = 'P4qW7eR9tY2uI5oP8aS1dF6gH3jK0lZ9xC7vB5nM4'
```

**Protect config.py:**

```bash
chmod 600 config.py

# Verify git ignores it
git status config.py
# Should show: "not tracked" or "ignored"

# If accidentally tracked:
git rm --cached config.py
echo "config.py" >> .gitignore
git add .gitignore
git commit -m "Remove config.py from git tracking"
```

## API Security

### Google Calendar API

**Service account best practices:**

1. **Use separate service accounts for dev/prod**
```bash
# Development
~/.config/calpal-dev/service-account-key.json

# Production
~/.config/calpal-prod/service-account-key.json
```

2. **Limit service account permissions**
   - Only grant access to calendars that need sync
   - Use "Make changes to events" not "Make changes and manage sharing"

3. **Monitor service account usage**
   - Review Google Cloud Console > IAM & Admin > Service Accounts
   - Check for unexpected activity

4. **Implement rate limiting**
```python
# In code, add delays between API calls
import time
time.sleep(0.1)  # 100ms delay

# Handle rate limit errors
from googleapiclient.errors import HttpError
try:
    # API call
except HttpError as e:
    if e.resp.status == 429:  # Rate limit
        time.sleep(60)  # Wait 1 minute
        # Retry
```

### 25Live API

**Protect 25Live credentials:**

1. **Use read-only account if possible**
   - Request API user with minimal permissions
   - Only "read" access to calendars/events

2. **Rotate credentials regularly**
   ```bash
   # Every 90 days, update password
   nano ~/.config/calpal/25live_credentials
   # Update password line
   ```

3. **Monitor for unauthorized access**
   - Check 25Live audit logs for API user
   - Alert on unexpected queries

4. **Use HTTPS only**
   ```python
   # Always use https://
   TWENTYFIVE_LIVE_BASE_URL = 'https://25live.collegenet.com'
   # NEVER: http://25live.collegenet.com
   ```

## Database Security

### PostgreSQL Security

**Production database security:**

```yaml
# docker-compose.yml (production)
version: '3.8'
services:
  calpal_db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: calpal
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      POSTGRES_DB: calpal_db
    secrets:
      - db_password
    ports:
      - "127.0.0.1:5433:5432"  # Localhost only!
    volumes:
      - calpal_db_data:/var/lib/postgresql/data
    restart: unless-stopped

secrets:
  db_password:
    file: ~/.config/calpal/db_password.txt
```

**Database password security:**

```bash
# Generate strong password
openssl rand -base64 32 > ~/.config/calpal/db_password.txt
chmod 600 ~/.config/calpal/db_password.txt

# Use in DATABASE_URL
DATABASE_URL="postgresql://calpal:$(cat ~/.config/calpal/db_password.txt)@localhost:5433/calpal_db"
```

**Network security:**

```yaml
# Only bind to localhost (NOT 0.0.0.0)
ports:
  - "127.0.0.1:5433:5432"  # ✓ Correct
  # NOT:
  # - "0.0.0.0:5433:5432"  # ✗ Exposes to network
  # - "5433:5432"          # ✗ Exposes to network
```

**Connection encryption:**

```python
# For remote databases, use SSL
DATABASE_URL = 'postgresql://user:pass@host:5432/db?sslmode=require'

# Verify SSL
import psycopg2
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
```

**User permissions:**

```sql
-- Limit calpal user to calpal_db only
REVOKE ALL ON DATABASE postgres FROM calpal;
REVOKE ALL ON DATABASE template1 FROM calpal;
GRANT ALL PRIVILEGES ON DATABASE calpal_db TO calpal;

-- Within calpal_db, limit to tables only
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO calpal;
REVOKE CREATE ON SCHEMA public FROM calpal;
```

### Backup Security

**Encrypt backups:**

```bash
# Encrypted backup
docker exec calpal_db pg_dump -U calpal calpal_db | \
  openssl enc -aes-256-cbc -salt -pbkdf2 -out \
  backups/calpal_db_$(date +%Y%m%d).sql.enc

# Enter encryption password when prompted

# Decrypt for restore
openssl enc -aes-256-cbc -d -pbkdf2 -in backups/calpal_db_20251004.sql.enc | \
  docker exec -i calpal_db psql -U calpal -d calpal_db
```

**Secure backup storage:**

```bash
# Set restrictive permissions
chmod 600 backups/*.sql
chmod 600 backups/*.sql.enc

# Store offsite (encrypted)
# Upload to S3, Google Cloud Storage, etc. with encryption
```

## Network Security

### Firewall Configuration

**Production firewall rules:**

```bash
# Allow only necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH (if remote)
sudo ufw allow 22/tcp

# HTTP/HTTPS (for Flask server)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Database (localhost only, no firewall rule needed)
# Port 5433 should NOT be accessible from network

sudo ufw enable
sudo ufw status
```

### HTTPS/TLS

**Use reverse proxy with TLS:**

```nginx
# /etc/nginx/sites-available/calpal
server {
    listen 443 ssl http2;
    server_name calendar.example.edu;

    ssl_certificate /etc/letsencrypt/live/calendar.example.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/calendar.example.edu/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name calendar.example.edu;
    return 301 https://$server_name$request_uri;
}
```

**Obtain TLS certificate:**

```bash
# Using Let's Encrypt
sudo certbot --nginx -d calendar.example.edu
```

### IP Whitelisting

**Restrict access by IP:**

```nginx
# In nginx config
location / {
    allow 192.168.1.0/24;  # Your network
    allow 10.0.0.0/8;       # VPN range
    deny all;

    proxy_pass http://127.0.0.1:5001;
}
```

## File Permissions

### Recommended Permissions

```bash
# Directories
chmod 700 ~/.config/calpal          # Config directory
chmod 755 /home/user/CalPal         # Project directory
chmod 700 /home/user/CalPal/private # Private files
chmod 755 /home/user/CalPal/logs    # Logs (readable by group)
chmod 700 /home/user/CalPal/db      # Database files

# Files
chmod 600 ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/25live_credentials
chmod 600 ~/.config/calpal/db_password.txt
chmod 600 config.py
chmod 600 private/*.ics
chmod 644 requirements.txt
chmod 755 src/*.py  # Executable scripts
```

### Verify Permissions Script

```bash
#!/bin/bash
# scripts/check_permissions.sh

echo "Checking CalPal file permissions..."

ERRORS=0

check_perms() {
    file="$1"
    expected="$2"
    if [ -e "$file" ]; then
        actual=$(stat -c %a "$file")
        if [ "$actual" != "$expected" ]; then
            echo "❌ $file has permissions $actual, expected $expected"
            ERRORS=$((ERRORS + 1))
        else
            echo "✅ $file has correct permissions ($expected)"
        fi
    else
        echo "⚠️  $file does not exist"
    fi
}

check_perms ~/.config/calpal/service-account-key.json 600
check_perms ~/.config/calpal/25live_credentials 600
check_perms config.py 600
check_perms ~/.config/calpal 700

if [ $ERRORS -eq 0 ]; then
    echo "✅ All permissions correct"
else
    echo "❌ Found $ERRORS permission issues"
    exit 1
fi
```

## Web Server Security

### Flask Security

**Production deployment:**

```python
# Use production WSGI server (NOT Flask development server)
# Install: pip install gunicorn

# Run with gunicorn
# gunicorn -w 4 -b 127.0.0.1:5001 src.calpal_flask_server:app
```

**Rate limiting:**

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"]
)

@app.route('/<path>/calendar.ics')
@limiter.limit("10 per hour")
def serve_ics(path):
    # ...
```

**Request validation:**

```python
from werkzeug.exceptions import BadRequest

@app.route('/<path>/calendar.ics')
def serve_ics(path):
    # Validate path
    if path != SECURE_ENDPOINT_PATH:
        abort(404)

    # Validate token
    token = request.args.get('token')
    if not token or not secrets.compare_digest(token, ACCESS_TOKEN):
        abort(403)

    # Rate limit per IP
    # (see rate limiting above)

    return send_file(ICS_FILE_PATH)
```

**Security headers:**

```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

## Secrets Management

### Using Environment Variables

```bash
# .env file (never commit!)
DATABASE_URL=postgresql://...
GOOGLE_CREDENTIALS_FILE=/path/to/key.json
SECURE_ENDPOINT_PATH=random-path
ACCESS_TOKEN=random-token
```

```python
# Load from .env
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
```

### Using Docker Secrets

```yaml
# docker-compose.yml
services:
  calpal_service:
    secrets:
      - db_password
      - access_token
    environment:
      - DATABASE_URL=postgresql://calpal@calpal_db:5432/calpal_db
      - ACCESS_TOKEN_FILE=/run/secrets/access_token

secrets:
  db_password:
    file: ~/.config/calpal/db_password.txt
  access_token:
    file: ~/.config/calpal/access_token.txt
```

### Using HashiCorp Vault

```python
import hvac

# Connect to Vault
client = hvac.Client(url='https://vault.example.com')
client.token = os.getenv('VAULT_TOKEN')

# Read secrets
db_password = client.secrets.kv.v2.read_secret_version(
    path='calpal/database'
)['data']['data']['password']

access_token = client.secrets.kv.v2.read_secret_version(
    path='calpal/web'
)['data']['data']['access_token']
```

## Audit Logging

### Enable Comprehensive Logging

```python
import logging

# Configure audit logger
audit_logger = logging.getLogger('calpal.audit')
audit_logger.setLevel(logging.INFO)

audit_handler = logging.FileHandler('logs/audit.log')
audit_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(message)s')
)
audit_logger.addHandler(audit_handler)

# Log all sensitive operations
def record_event(event_data):
    audit_logger.info(f"Event created: {event_data['event_id']} by {get_current_user()}")
    # ... database operation

def delete_event(event_id):
    audit_logger.warning(f"Event deleted: {event_id} by {get_current_user()}")
    # ... database operation
```

### What to Log

**Security events:**
- Authentication attempts (success/failure)
- API key usage
- Database connections
- Configuration changes
- File access

**Operational events:**
- Event creation/modification/deletion
- Sync operations (start/end/errors)
- Database queries
- API calls to external services

**Don't log:**
- Passwords or tokens
- Full calendar event contents
- Personal identifiable information (unless necessary)
- Full API responses (may contain sensitive data)

## Incident Response

### Compromised Credentials

**If service account key compromised:**

1. **Immediately disable key** in Google Cloud Console
2. **Create new service account** with new key
3. **Update CalPal configuration** with new key
4. **Audit calendar access** for unauthorized changes
5. **Review logs** for suspicious activity
6. **Notify security team**

```bash
# Secure old key
shred -vfz -n 10 ~/.config/calpal/service-account-key.json

# Update with new key
cp ~/Downloads/new-key.json ~/.config/calpal/service-account-key.json
chmod 600 ~/.config/calpal/service-account-key.json

# Restart services
systemctl restart calpal
```

**If database compromised:**

1. **Change database password** immediately
2. **Audit database for unauthorized changes**
3. **Review connection logs**
4. **Restore from clean backup** if necessary
5. **Enable additional monitoring**

```bash
# Change password
docker exec -it calpal_db psql -U postgres -c \
  "ALTER USER calpal WITH PASSWORD 'new_secure_password';"

# Update config
sed -i 's/old_password/new_password/g' config.py

# Restart
docker compose restart calpal_db
systemctl restart calpal
```

### Suspicious Activity

**Indicators of compromise:**
- Unexpected API calls in logs
- Database queries at unusual times
- Failed authentication attempts
- Unusual event modifications
- Unexpected file access

**Response procedure:**
1. **Isolate system** (disable network if severe)
2. **Collect logs** before they rotate
3. **Review recent changes** in database and calendars
4. **Identify attack vector**
5. **Remediate vulnerabilities**
6. **Restore from backup** if compromised
7. **Monitor for recurrence**

## Security Checklist

### Pre-Deployment Checklist

- [ ] Service account key stored securely outside repository
- [ ] File permissions set correctly (600 for credentials, 700 for directories)
- [ ] config.py NOT committed to git
- [ ] Strong random tokens generated for web access
- [ ] Database password changed from default
- [ ] Database only accessible from localhost
- [ ] TLS/HTTPS configured for web server
- [ ] Firewall rules restrict access
- [ ] Logging enabled for security events
- [ ] Backup encryption configured
- [ ] Secrets rotation schedule established

### Monthly Security Review

- [ ] Review audit logs for suspicious activity
- [ ] Check for unauthorized calendar access
- [ ] Verify file permissions unchanged
- [ ] Review database user privileges
- [ ] Check for software updates
- [ ] Test backup restoration
- [ ] Review API usage patterns
- [ ] Audit service account permissions

### Quarterly Security Tasks

- [ ] Rotate database password
- [ ] Rotate service account key (Google)
- [ ] Rotate 25Live password
- [ ] Rotate web access tokens
- [ ] Review and update firewall rules
- [ ] Update dependencies (pip install -U -r requirements.txt)
- [ ] Security audit of logs
- [ ] Penetration testing (if applicable)

## Resources

- [Google Cloud Security Best Practices](https://cloud.google.com/security/best-practices)
- [PostgreSQL Security Documentation](https://www.postgresql.org/docs/current/security.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Guide](https://flask.palletsprojects.com/en/latest/security/)

## Reporting Security Issues

If you discover a security vulnerability in CalPal:

1. **Do NOT open a public GitHub issue**
2. **Email security contact**: security@example.com
3. **Include**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work to address critical issues immediately.
