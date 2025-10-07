# Security Guide

Security best practices for deploying and operating CalPal.

## Credential Management

### Never Commit Secrets to Git

**Protected files (in `.gitignore`):**
- `config.py`
- `.env`
- `~/.config/calpal/*` (credentials directory)
- `data/` (contains calendar IDs)
- `private/` (contains sensitive configuration)

**Always use templates:**
- Commit: `config.example.py`, `.env.example`
- Use locally: `config.py`, `.env`

### Secure Credential Storage

```bash
# Create secure credentials directory
mkdir -p ~/.config/calpal
chmod 700 ~/.config/calpal

# Store service account key
mv service-account-key.json ~/.config/calpal/
chmod 600 ~/.config/calpal/service-account-key.json

# Store 25Live credentials (username and password, one per line)
cat > ~/.config/calpal/25live_credentials << 'EOF'
your-username
your-password
EOF
chmod 600 ~/.config/calpal/25live_credentials
```

### Environment Variable Security

```bash
# Never commit .env file
echo ".env" >> .gitignore

# Use strong passwords
DATABASE_PASSWORD=$(openssl rand -base64 32)

# Generate secure tokens
SECURE_ENDPOINT_PATH=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
ACCESS_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
```

## Database Security

### Connection Security

```python
# Use SSL for database connections
DATABASE_URL = 'postgresql://user:pass@host:5432/db?sslmode=require'

# For cloud databases, use certificate authentication
DATABASE_URL = 'postgresql://user:pass@host:5432/db?sslmode=verify-full&sslrootcert=/path/to/ca.crt'
```

### User Permissions

```sql
-- Create limited-privilege user
CREATE USER calpal WITH PASSWORD 'strong_password';

-- Grant only necessary permissions
GRANT CONNECT ON DATABASE calpal_db TO calpal;
GRANT SELECT, INSERT, UPDATE ON calendar_events TO calpal;
GRANT SELECT, INSERT ON event_blacklist TO calpal;

-- Do NOT grant DROP, TRUNCATE, or superuser
```

### Data Encryption

```sql
-- Enable encryption at rest (PostgreSQL 14+)
ALTER DATABASE calpal_db SET default_transaction_read_only = off;

-- Encrypt sensitive JSONB fields
-- Example: Encrypt event metadata
UPDATE calendar_events
SET metadata = pgp_sym_encrypt(metadata::text, 'encryption_key')::jsonb;
```

## API Security

### Google Calendar API

**Service Account Best Practices:**
- Use domain-wide delegation sparingly
- Limit scope to `https://www.googleapis.com/auth/calendar` only
- Rotate service account keys annually
- Monitor service account usage in Google Admin Console

**Key Rotation:**
```bash
# Generate new key in Google Cloud Console
# Download new key
mv new-key.json ~/.config/calpal/service-account-key.json

# Restart CalPal services
sudo systemctl restart calpal
```

### 25Live API

**Credential Security:**
- Use read-only API credentials where possible
- Never log passwords
- Rotate credentials every 90 days
- Monitor API access logs

**Session Management:**
```python
# Sessions should expire after inactivity
session_timeout = 3600  # 1 hour

# Re-authenticate on session expiry
if time.time() - last_auth > session_timeout:
    authenticate()
```

## Web Server Security

### ICS Server (Flask)

**Token-Based Authentication:**
```python
# Require token for all requests
@app.route(f'/{SECURE_ENDPOINT_PATH}/schedule.ics')
def serve_ics():
    token = request.args.get('token')
    if not secrets.compare_digest(token, ACCESS_TOKEN):
        abort(403)
    return send_file('private/schedule.ics')
```

**Security Headers:**
```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response
```

**Rate Limiting:**
```python
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.route('/schedule.ics')
@limiter.limit("10 per minute")
def serve_ics():
    # ...
```

### HTTPS Configuration

**Use Let's Encrypt with Nginx:**
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d calendar.example.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

**Nginx SSL Configuration:**
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

## Access Control

### File Permissions

```bash
# CalPal directory
chmod 755 /opt/calpal
chown calpal:calpal /opt/calpal

# Configuration files
chmod 600 /opt/calpal/.env
chmod 600 /opt/calpal/config.py

# Logs (readable by admins)
chmod 640 /opt/calpal/logs/*.log

# Data directories
chmod 700 /opt/calpal/private/
chmod 700 /opt/calpal/data/
```

### User Isolation

```bash
# Create dedicated user
sudo useradd -r -s /bin/false -d /opt/calpal calpal

# Run services as calpal user
sudo systemctl edit calpal.service
# Add: User=calpal
```

## Data Privacy

### Personal Information

**Minimize data collection:**
- Store only necessary event fields
- Avoid logging full event details
- Sanitize logs before sharing

**Privacy-preserving transformations:**
```python
# ICS generation - remove personal details
def sanitize_event(event):
    if event.is_personal:
        return {
            'summary': 'Busy',
            'description': '',
            'attendees': [],
            'start': event.start,
            'end': event.end
        }
    return event
```

### Data Retention

```sql
-- Automatically purge old deleted events
DELETE FROM calendar_events
WHERE deleted_at < NOW() - INTERVAL '90 days';

-- Archive old blacklist entries
CREATE TABLE event_blacklist_archive AS
SELECT * FROM event_blacklist
WHERE blacklisted_at < NOW() - INTERVAL '1 year';

DELETE FROM event_blacklist
WHERE blacklisted_at < NOW() - INTERVAL '1 year';
```

## Logging & Monitoring

### Secure Logging

**Don't log sensitive data:**
```python
# BAD
logger.info(f"Event: {event}")  # May contain private info

# GOOD
logger.info(f"Processing event {event.id} in calendar {event.calendar[:8]}...")
```

**Sanitize before logging:**
```python
def sanitize_for_log(data):
    sensitive_fields = ['password', 'token', 'api_key', 'email']
    return {k: '***' if k in sensitive_fields else v
            for k, v in data.items()}
```

### Monitoring

**Security metrics to track:**
- Failed authentication attempts
- Unusual API usage patterns
- Database connection errors
- ICS endpoint access patterns

**Alerting:**
```python
# Alert on suspicious activity
if failed_auth_count > 5:
    alert("Multiple authentication failures detected")

if api_rate > threshold:
    alert("Unusual API usage pattern detected")
```

## Incident Response

### Suspected Breach

1. **Immediately revoke credentials:**
   ```bash
   # Rotate all tokens
   python3 -c "import secrets; print(secrets.token_urlsafe(32))" > new_token.txt

   # Update .env with new token
   # Restart services
   ```

2. **Audit logs:**
   ```bash
   # Check access logs
   grep "schedule.ics" /var/log/nginx/access.log | grep -v "200"

   # Check authentication logs
   grep "Failed" logs/calpal.log
   ```

3. **Revoke Google service account:**
   - Go to Google Cloud Console
   - Delete compromised key
   - Generate new key
   - Update CalPal configuration

4. **Reset 25Live credentials:**
   - Change password in 25Live
   - Update `~/.config/calpal/25live_credentials`

### Regular Security Audits

**Monthly:**
- Review user access logs
- Check for unauthorized database connections
- Verify credential file permissions
- Update dependencies (`pip list --outdated`)

**Quarterly:**
- Rotate API tokens and passwords
- Review and update security policies
- Audit event data for PII leakage
- Test backup and recovery procedures

**Annually:**
- Rotate Google service account keys
- Comprehensive security assessment
- Update SSL/TLS certificates
- Review and update access control lists

## Compliance

### GDPR Considerations

If processing EU personal data:
- **Data Minimization:** Only store necessary event data
- **Right to Erasure:** Implement event deletion workflows
- **Data Portability:** Provide ICS export functionality
- **Consent:** Ensure users consent to calendar sync

### FERPA (Educational Records)

For academic institutions:
- **Access Controls:** Limit who can view student schedules
- **Audit Logging:** Log all access to educational records
- **Data Security:** Encrypt sensitive educational data
- **Disclosure Policies:** Document what data is shared via ICS

## Security Checklist

**Before Deployment:**
- [ ] All credentials in `.gitignore`
- [ ] Strong database password set
- [ ] Secure tokens generated for ICS endpoints
- [ ] HTTPS enabled with valid certificate
- [ ] File permissions set correctly (600 for secrets)
- [ ] Service running as non-root user
- [ ] Database user has minimal permissions
- [ ] Logs don't contain sensitive data
- [ ] Rate limiting enabled on web endpoints
- [ ] Security headers configured

**Ongoing:**
- [ ] Regular dependency updates
- [ ] Credential rotation schedule
- [ ] Log monitoring and alerting
- [ ] Backup verification
- [ ] Access audit reviews
- [ ] Security patch application

## Resources

- [Google Cloud Security Best Practices](https://cloud.google.com/security/best-practices)
- [OWASP Top Ten](https://owasp.org/www-project-top-ten/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)
- [Flask Security Checklist](https://flask.palletsprojects.com/en/latest/security/)
