# Rhize Menu Scraper

Automated system for tracking Rhize products across 28 Vermont dispensaries.

## Overview

- **Scrapes 28 dispensary websites** across 6 different platforms
- **Tracks inventory changes** daily (added, removed, updated)
- **Generates Excel reports** with comparison data
- **Sends email notifications** with changes
- **Uploads to Google Drive** and MySQL database

## Quick Start

### Prerequisites

```bash
pip install selenium webdriver-manager requests openpyxl pandas mysql-connector-python
```

Chrome browser required for Selenium scrapers.

### Run

```bash
# Full daily scrape (all stores)
python main.py

# Priority stores only (faster)
python run_priority.py

# Single store test
python test.py
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point - runs all stores |
| `scraper_agent.py` | AI-powered self-healing scraper |
| `test_agent.py` | Test the AI agent |
| `mail_cfg.py` | Email configuration |
| `scrapers/` | Platform-specific scraper modules |
| `utils/` | Common utilities (data processing, Excel) |
| `config/website_list.json` | Store configurations (28 stores) |

## Platforms Supported

| Platform | Stores | Method |
|----------|--------|--------|
| Dutchie | 12 | API |
| Leafly | 5 | API |
| iHeartJane | 4 | API |
| Gram Central | 3 | API |
| Dispenseapp | 2 | Web scrape |
| dispensary.shop | 2 | API |

## Output Files

| File | Content |
|------|---------|
| `current_inventory_{store}.xlsx` | Latest scraped inventory |
| `data_base_{store}.xlsx` | Historical inventory database |
| `notification_excel_{date}.xlsx` | Daily changes summary |

## AI Agent (Self-Healing)

The scraper agent uses Claude API to automatically fix scraping errors:

```bash
python scraper_agent.py
```

See [AGENT_SETUP.md](AGENT_SETUP.md) for full setup instructions.

## Windows Task Scheduler

Daily scrape configured to run at 6:00 AM:
- Task: `Menu Scraper - Daily`

## Related Documentation

- [AGENT_SETUP.md](AGENT_SETUP.md) - AI agent setup guide
- [Documentation/SCRAPER_GUIDE.md](../Documentation/SCRAPER_GUIDE.md) - Platform details
- [Documentation/STORES.md](../Documentation/STORES.md) - Complete store list
- [Documentation/TROUBLESHOOTING.md](../Documentation/TROUBLESHOOTING.md) - Common issues
