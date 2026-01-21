# AI Scraper Agent Setup Guide

## What This Does

The `scraper_agent.py` replaces `main.py` as your Task Scheduler entry point. It:

1. **Runs your scraper** - Executes main.py as a subprocess
2. **Monitors for errors** - Parses logs in real-time
3. **Auto-fixes common issues**:
   - Missing imports (adds them automatically)
   - Missing packages (pip installs them)
   - Browser crashes (retries)
   - Timeouts (retries)
4. **Uses Claude AI for complex fixes** - Analyzes unfamiliar errors and generates code patches
5. **Auto-deploys fixes** - Applies patches with automatic backups
6. **Sends reports** - Emails you when fixes are applied or issues need attention

---

## Quick Setup (5 minutes)

### Step 1: Get Claude API Key

1. Go to https://console.anthropic.com/
2. Create an account or sign in
3. Go to "API Keys" and create a new key
4. Copy the key (starts with `sk-ant-`)

### Step 2: Add API Key to .env

Open `.env` and add your key:

```
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
```

### Step 3: Test the Agent

```bash
cd C:\Users\levi\RhizeHQ\menu_scraping_api15122025
python test_agent.py
```

You should see all tests pass.

### Step 4: Update Task Scheduler

1. Open **Task Scheduler** (search in Windows)
2. Find your existing scraper task
3. Click **Properties** > **Actions** > **Edit**
4. Change the **Program/script** argument from:
   ```
   main.py
   ```
   To:
   ```
   scraper_agent.py
   ```
5. Click OK to save

---

## How It Works

```
Task Scheduler triggers daily
         |
         v
   scraper_agent.py
         |
         v
   Runs main.py -----> Success? -----> Done
         |                  |
         v                  v
      Failed            Send normal
         |              email reports
         v
   Parse error logs
         |
         v
   Known pattern? -----> Yes -----> Apply fix
         |                              |
         No                             v
         |                          Retry
         v
   Call Claude API
         |
         v
   Apply AI fix
         |
         v
   Retry (up to 3x)
         |
         v
   Send agent report
```

---

## Error Patterns Auto-Fixed

| Error Type | Auto-Fix |
|------------|----------|
| `name 'X' is not defined` | Adds missing import |
| `No module named 'X'` | Runs pip install |
| `TimeoutException` | Retries |
| `no such window` (browser crash) | Retries |
| `age verification` failures | Retries |
| `SyntaxError` | Claude analyzes and patches |
| `IndentationError` | Claude analyzes and patches |
| Unknown errors | Claude analyzes and patches |

---

## Files Created

| File | Purpose |
|------|---------|
| `scraper_agent.py` | Main agent - run this |
| `test_agent.py` | Test script to verify setup |
| `backups/` | Automatic backups before any code changes |
| `agent_logs/` | Agent execution logs |
| `fix_history.json` | History of all fixes applied |

---

## Configuration Options

Edit these in `scraper_agent.py`:

```python
# Maximum retry attempts after fixing
MAX_RETRIES = 3

# Maximum auto-fixes per run (safety limit)
MAX_AUTO_FIXES_PER_RUN = 5

# Send email reports about agent actions
SEND_AGENT_NOTIFICATIONS = True

# Claude model to use
CLAUDE_MODEL = "claude-sonnet-4-20250514"
```

---

## Monitoring

### Agent Logs
Check `agent_logs/` for detailed execution logs:
```bash
type agent_logs\agent_YYYYMMDD_HHMMSS.log
```

### Fix History
See all fixes applied:
```bash
type fix_history.json
```

### Backups
All modified files are backed up to `backups/`:
```
backups/
  dutchie_scraper_20250111_143052.py
  gramcentral_scraper_20250111_143055.py
```

---

## Rollback

If a fix causes issues, restore from backup:

```python
# Find the backup
dir backups\

# Restore it
copy backups\dutchie_scraper_20250111_143052.py scrapers\dutchie_scraper.py
```

---

## Cost Estimate

Claude API costs ~$3-15 per 1M tokens. Typical usage:
- Each error analysis: ~2K tokens (~$0.006)
- Average run with 2-3 fixes: ~$0.02
- Monthly (30 days): ~$0.60

Very cost-effective compared to paying someone hourly.

---

## FAQ

**Q: What if Claude suggests a bad fix?**
A: The agent validates Python syntax before applying. If invalid, the fix is rejected. Backups are always created.

**Q: What if the API key expires?**
A: The agent will still work - it just won't be able to use Claude for complex fixes. Simple patterns (missing imports, retries) will still work.

**Q: Can I run both main.py and scraper_agent.py?**
A: Don't run them simultaneously. scraper_agent.py runs main.py internally.

**Q: How do I disable the agent temporarily?**
A: Just change Task Scheduler back to run `main.py` directly.

---

## Support

If you need help:
1. Check `agent_logs/` for error details
2. Check `fix_history.json` for what was changed
3. Restore from `backups/` if needed
