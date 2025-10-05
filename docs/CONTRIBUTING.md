# Contributing to CalPal

Thank you for your interest in contributing to CalPal! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contribution Workflow](#contribution-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of:
- Experience level
- Gender identity and expression
- Sexual orientation
- Disability
- Personal appearance
- Body size
- Race or ethnicity
- Age
- Religion
- Nationality

### Expected Behavior

- Be respectful and considerate
- Welcome newcomers and help them get started
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment, trolling, or discriminatory language
- Personal attacks or insults
- Publishing others' private information
- Other conduct which could reasonably be considered inappropriate

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- PostgreSQL 15+ (or Docker)
- Google Cloud account
- 25Live account (optional, for full functionality)

### First-Time Contributors

1. **Read the documentation** - Familiarize yourself with CalPal's architecture and features
2. **Set up development environment** - Follow [Development Setup](#development-setup)
3. **Find an issue** - Look for issues labeled `good first issue` or `help wanted`
4. **Ask questions** - Don't hesitate to ask in discussions or issue comments

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/CalPal.git
cd CalPal

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/CalPal.git
```

### 2. Create Development Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
# Or manually:
pip install pytest pytest-cov black flake8 mypy
```

### 3. Set Up Database

```bash
# Start PostgreSQL via Docker
docker compose up -d

# Verify database is running
docker compose ps
```

### 4. Configure CalPal

```bash
# Copy example config
cp config.example.py config.py

# Edit config.py with your development settings
# Use test calendars, not production ones!
nano config.py
```

### 5. Verify Setup

```bash
# Test database connection
python3 -c "from src.db_manager import DatabaseManager; db = DatabaseManager(); print(db.test_connection())"

# Run tests (if available)
pytest

# Check code style
black --check src/
flake8 src/
```

## Contribution Workflow

### 1. Create a Feature Branch

```bash
# Update your fork
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature-name
# Or for bug fixes:
git checkout -b fix/bug-description
```

### Branch Naming Conventions

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Adding or updating tests

### 2. Make Changes

```bash
# Make your changes
# Test thoroughly
# Commit with clear messages

git add .
git commit -m "Add feature: description of feature"
```

### 3. Keep Your Branch Updated

```bash
# Regularly sync with upstream
git fetch upstream
git rebase upstream/main

# Or merge if you prefer
git merge upstream/main
```

### 4. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create pull request on GitHub
# Include description of changes, link to issue if applicable
```

## Coding Standards

### Python Style Guide

CalPal follows [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

#### Code Formatting

```bash
# Use Black for consistent formatting
black src/

# Check formatting
black --check src/

# Or configure your editor to format on save
```

#### Linting

```bash
# Use flake8 for linting
flake8 src/

# Common issues to avoid:
# - Unused imports
# - Undefined variables
# - Lines longer than 100 characters (when reasonable)
```

#### Type Hints

Use type hints for function signatures:

```python
from typing import Dict, List, Optional
from datetime import datetime

def process_event(
    event_data: Dict,
    calendar_id: str,
    created_at: Optional[datetime] = None
) -> bool:
    """
    Process a calendar event.

    Args:
        event_data: Dictionary containing event information
        calendar_id: Target calendar ID
        created_at: Optional creation timestamp

    Returns:
        True if successful, False otherwise
    """
    # Implementation
    return True
```

### Docstring Conventions

Use Google-style docstrings:

```python
def sync_calendar(calendar_id: str, start_date: str, end_date: str) -> Dict:
    """
    Synchronize events from 25Live for a specific calendar.

    This function fetches events from the 25Live API within the specified
    date range and stores them in the database. It handles duplicate
    detection and event updates.

    Args:
        calendar_id: Google Calendar ID to sync to
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)

    Returns:
        Dictionary containing sync results:
        {
            'events_created': int,
            'events_updated': int,
            'errors': List[str]
        }

    Raises:
        ValueError: If date format is invalid
        APIError: If 25Live API request fails

    Example:
        >>> result = sync_calendar('cal123@group.calendar.google.com',
        ...                        '2025-01-01', '2025-12-31')
        >>> print(result['events_created'])
        42
    """
    # Implementation
```

### File Organization

```python
# Order of imports:
# 1. Standard library
# 2. Third-party packages
# 3. Local application imports

import os
import sys
from datetime import datetime
from typing import Dict, List

import requests
from googleapiclient.discovery import build

from config import DATABASE_URL, WORK_CALENDAR_ID
from src.db_manager import DatabaseManager
```

### Naming Conventions

```python
# Classes: PascalCase
class CalendarScanner:
    pass

# Functions and variables: snake_case
def get_calendar_events():
    event_count = 0

# Constants: UPPER_SNAKE_CASE
MAX_BATCH_SIZE = 100
DEFAULT_TIMEOUT = 30

# Private methods: _leading_underscore
def _internal_helper():
    pass
```

## Testing Guidelines

### Writing Tests

Create tests in `tests/` directory:

```python
# tests/test_db_manager.py
import pytest
from datetime import datetime
from src.db_manager import DatabaseManager

@pytest.fixture
def db():
    """Fixture providing database connection."""
    return DatabaseManager('postgresql://test:test@localhost:5433/test_db')

def test_record_event(db):
    """Test event recording."""
    event_data = {
        'event_id': 'test123',
        'current_calendar': 'test@example.com',
        'summary': 'Test Event',
        'start_time': datetime.now(),
        'end_time': datetime.now(),
        'event_type': 'manual',
        'status': 'active'
    }

    db.record_event(event_data)

    # Verify event was recorded
    retrieved = db.get_event_by_id('test123', 'test@example.com')
    assert retrieved is not None
    assert retrieved['summary'] == 'Test Event'

def test_mark_deleted(db):
    """Test soft delete functionality."""
    # Setup: create event
    event_data = {...}
    db.record_event(event_data)

    # Action: mark deleted
    db.mark_as_deleted('test123', 'test@example.com')

    # Verify: event marked deleted
    event = db.get_event_by_id('test123', 'test@example.com')
    assert event is None  # Should not return deleted events
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_db_manager.py

# Run with coverage
pytest --cov=src tests/

# Run with verbose output
pytest -v

# Run only tests matching pattern
pytest -k "test_record"
```

### Test Coverage

Aim for:
- **80%+ coverage** for new code
- **100% coverage** for critical paths (database operations, API calls)

```bash
# Generate coverage report
pytest --cov=src --cov-report=html tests/

# View in browser
open htmlcov/index.html
```

## Documentation

### Code Documentation

- **Docstrings**: All public functions, classes, and modules
- **Comments**: Explain "why", not "what"
- **Type hints**: All function signatures

### User Documentation

When adding features, update:

- **README.md**: If it affects quick start or main features
- **docs/INSTALLATION.md**: If it changes installation process
- **docs/CONFIGURATION.md**: If it adds config options
- **docs/SERVICES.md**: If it adds/modifies services
- **docs/DATABASE.md**: If it changes database schema

### Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Longer explanation if needed. Wrap at 72 characters.
Include motivation for change and contrast with previous behavior.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code restructuring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**

```bash
# Good commit messages
git commit -m "feat(scanner): add support for recurring events"
git commit -m "fix(db): prevent duplicate mirror events"
git commit -m "docs(readme): update installation instructions"

# Multi-line commit
git commit -m "feat(25live): add custom query support

Allows users to specify custom 25Live query IDs in configuration.
This enables syncing from organization-specific saved queries.

Closes #42"
```

## Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines (black, flake8)
- [ ] All tests pass (`pytest`)
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] Commit messages are clear and follow conventions
- [ ] Branch is up to date with upstream main

### PR Description Template

```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Changes Made
- Change 1
- Change 2
- Change 3

## Testing
How was this tested?

## Screenshots (if applicable)
Add screenshots for UI changes

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
- [ ] Code follows style guide
- [ ] Commits are clean and descriptive

## Related Issues
Fixes #123
Related to #456
```

### Review Process

1. **Automated checks**: CI/CD runs tests and linting
2. **Code review**: Maintainer reviews code
3. **Feedback**: Address review comments
4. **Approval**: Maintainer approves PR
5. **Merge**: PR merged into main branch

### After Merge

- Your contribution will be included in the next release
- You'll be credited in CHANGELOG.md
- Thank you for contributing!

## Issue Guidelines

### Reporting Bugs

Use the bug report template:

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce:
1. Run '...'
2. Configure '...'
3. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Environment:**
- OS: [e.g., Ubuntu 22.04]
- Python version: [e.g., 3.10.5]
- CalPal version: [e.g., 1.0.0]
- Database: [e.g., PostgreSQL 15]

**Logs**
```
Paste relevant logs here
```

**Additional context**
Any other relevant information.
```

### Requesting Features

Use the feature request template:

```markdown
**Is your feature request related to a problem?**
Clear description of the problem. Ex. "I'm frustrated when..."

**Describe the solution you'd like**
Clear description of what you want to happen.

**Describe alternatives you've considered**
Other solutions or features you've considered.

**Additional context**
Any other context or screenshots.

**Would you be willing to implement this?**
Yes/No/Maybe
```

### Issue Labels

- `bug`: Something isn't working
- `enhancement`: New feature or improvement
- `documentation`: Documentation improvements
- `good first issue`: Good for newcomers
- `help wanted`: Extra attention needed
- `question`: Further information requested
- `duplicate`: Duplicate of another issue
- `wontfix`: This will not be worked on

## Development Best Practices

### Database Migrations

When modifying database schema:

1. **Create migration file**:
```bash
# Sequential number, descriptive name
touch db/migrations/003_add_new_field.sql
```

2. **Write idempotent SQL**:
```sql
-- Migration 003: Add timezone field
-- Rollback: ALTER TABLE calendar_events DROP COLUMN IF EXISTS timezone;

ALTER TABLE calendar_events
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Los_Angeles';

COMMENT ON COLUMN calendar_events.timezone IS 'IANA timezone identifier';
```

3. **Update docs/DATABASE.md** with new schema

4. **Test migration** on clean database

### Configuration Changes

When adding configuration options:

1. **Add to config.example.py** with comments
2. **Document in docs/CONFIGURATION.md**
3. **Provide sensible defaults**
4. **Add validation** in code

### Error Handling

```python
# Good error handling
try:
    result = api_call()
except APIError as e:
    logger.error(f"API call failed: {e}")
    # Handle gracefully
    return None
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
    raise

# Bad error handling
try:
    result = api_call()
except:  # Too broad
    pass  # Silent failure
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Detailed diagnostic info")
logger.info("Normal operation")
logger.warning("Something unexpected")
logger.error("Error occurred")
logger.critical("Critical failure")

# Include context
logger.info(f"Synced {count} events from {calendar_id}")
logger.error(f"Failed to connect to database: {error}")
```

## Getting Help

- **Documentation**: Check [docs/](../docs/) folder
- **Discussions**: Use GitHub Discussions for questions
- **Issues**: Search existing issues before creating new ones
- **Email**: Contact maintainers at dev@example.com

## Recognition

Contributors will be recognized in:
- CHANGELOG.md for each release
- README.md contributors section
- GitHub contributors page

Thank you for contributing to CalPal!
