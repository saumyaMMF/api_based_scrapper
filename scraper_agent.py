"""
AI-Powered Scraper Agent
Automatically monitors, diagnoses, fixes, and redeploys the scraper.

Run this instead of main.py via Task Scheduler.
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
import traceback
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

# Claude API settings (add ANTHROPIC_API_KEY to .env)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Agent settings
MAX_RETRIES = 3
MAX_AUTO_FIXES_PER_RUN = 5
BACKUP_DIR = Path(__file__).parent / "backups"
AGENT_LOG_DIR = Path(__file__).parent / "agent_logs"
FIX_HISTORY_FILE = Path(__file__).parent / "fix_history.json"

# Notification settings
SEND_AGENT_NOTIFICATIONS = True

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ErrorInfo:
    """Represents a detected error"""
    error_type: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    store_name: Optional[str] = None
    full_traceback: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class FixAction:
    """Represents a fix that was applied"""
    error: ErrorInfo
    fix_type: str  # "pattern", "claude", "retry"
    description: str
    file_modified: Optional[str] = None
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    success: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

# ============================================================================
# KNOWN ERROR PATTERNS AND FIXES
# ============================================================================

# Patterns that can be auto-fixed without AI
KNOWN_FIXES = [
    {
        "pattern": r"name '(\w+)' is not defined",
        "description": "Missing import",
        "fix_type": "add_import",
        "common_imports": {
            "time": "import time",
            "json": "import json",
            "os": "import os",
            "sys": "import sys",
            "re": "import re",
            "logging": "import logging",
            "requests": "import requests",
            "datetime": "from datetime import datetime",
            "Path": "from pathlib import Path",
            "Dict": "from typing import Dict",
            "List": "from typing import List",
            "Any": "from typing import Any",
            "Optional": "from typing import Optional",
        }
    },
    {
        "pattern": r"No module named '(\w+)'",
        "description": "Missing package",
        "fix_type": "install_package",
    },
    {
        "pattern": r"(TimeoutException|timeout|timed out)",
        "description": "Timeout error - increase wait time",
        "fix_type": "retry_with_config",
        "retry": True,
    },
    {
        "pattern": r"(no such window|browser.*crash|session.*deleted)",
        "description": "Browser crashed",
        "fix_type": "retry",
        "retry": True,
    },
    {
        "pattern": r"(age.?verification|verify.?age|are you 21)",
        "description": "Age verification issue",
        "fix_type": "retry",
        "retry": True,
    },
    {
        "pattern": r"(Connection refused|ConnectionError|MaxRetryError)",
        "description": "Network connectivity issue",
        "fix_type": "retry",
        "retry": True,
    },
    {
        "pattern": r"(cookie|Cookie).*expired",
        "description": "Cookie expired",
        "fix_type": "notify",  # Needs manual cookie refresh
    },
    {
        "pattern": r"IndentationError: (.*)",
        "description": "Indentation error",
        "fix_type": "claude_fix",  # Let Claude fix it
    },
    {
        "pattern": r"SyntaxError: (.*)",
        "description": "Syntax error",
        "fix_type": "claude_fix",
    },
]

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_agent_logging() -> logging.Logger:
    """Setup logging for the agent"""
    AGENT_LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = AGENT_LOG_DIR / f"agent_{timestamp}.log"

    logger = logging.getLogger("scraper_agent")
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger

# ============================================================================
# BACKUP AND RESTORE
# ============================================================================

def create_backup(file_path: Path, logger: logging.Logger) -> Path:
    """Create a backup of a file before modifying it"""
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = BACKUP_DIR / backup_name

    shutil.copy2(file_path, backup_path)
    logger.info(f"Created backup: {backup_path}")

    return backup_path

def restore_from_backup(backup_path: Path, original_path: Path, logger: logging.Logger):
    """Restore a file from backup"""
    shutil.copy2(backup_path, original_path)
    logger.info(f"Restored {original_path} from {backup_path}")

# ============================================================================
# ERROR DETECTION
# ============================================================================

def parse_scraper_output(output: str, logger: logging.Logger) -> List[ErrorInfo]:
    """Parse scraper output to detect errors"""
    errors = []

    # Look for ERROR and CRITICAL log lines
    error_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?(ERROR|CRITICAL).*?(?:\[.*?\])?\s*(.+?):\s*(.+)',
        re.IGNORECASE
    )

    # Look for Python tracebacks
    traceback_pattern = re.compile(
        r'Traceback \(most recent call last\):(.+?)(?=\n\d{4}|\n\[|\Z)',
        re.DOTALL
    )

    # Look for specific error messages
    exception_pattern = re.compile(
        r'((?:Error|Exception|Failed).*?)(?:\n|$)',
        re.IGNORECASE
    )

    # Extract store-level errors
    store_error_pattern = re.compile(
        r'\[(\d+)/\d+\]\s*Processing:\s*(.+?)(?:\n|$).*?(?:ERROR|Error|Failed).*?:\s*(.+?)(?:\n|$)',
        re.DOTALL
    )

    lines = output.split('\n')
    current_store = None

    for i, line in enumerate(lines):
        # Track current store being processed
        store_match = re.search(r'\[\d+/\d+\]\s*Processing:\s*(.+)', line)
        if store_match:
            current_store = store_match.group(1).strip()

        # Check for error lines
        if 'ERROR' in line.upper() or 'CRITICAL' in line.upper():
            error_match = error_pattern.search(line)
            if error_match:
                timestamp, level, context, message = error_match.groups()

                # Extract file and line number if present
                file_path = None
                line_number = None
                file_match = re.search(r'File "([^"]+)", line (\d+)', output[max(0, i-10):])
                if file_match:
                    file_path = file_match.group(1)
                    line_number = int(file_match.group(2))

                errors.append(ErrorInfo(
                    error_type="log_error",
                    message=message.strip(),
                    file_path=file_path,
                    line_number=line_number,
                    store_name=current_store,
                    timestamp=timestamp
                ))

    # Extract tracebacks
    for tb_match in traceback_pattern.finditer(output):
        traceback_text = tb_match.group(0)

        # Get the actual exception at the end
        exception_lines = traceback_text.strip().split('\n')
        if exception_lines:
            last_line = exception_lines[-1].strip()

            # Extract file and line
            file_match = re.search(r'File "([^"]+)", line (\d+)', traceback_text)
            file_path = file_match.group(1) if file_match else None
            line_number = int(file_match.group(2)) if file_match else None

            errors.append(ErrorInfo(
                error_type="exception",
                message=last_line,
                file_path=file_path,
                line_number=line_number,
                store_name=current_store,
                full_traceback=traceback_text
            ))

    logger.info(f"Detected {len(errors)} errors in output")
    return errors

def categorize_error(error: ErrorInfo, logger: logging.Logger) -> Tuple[Optional[Dict], bool]:
    """
    Categorize an error and return the matching pattern and whether to retry.

    Returns:
        (matching_pattern, should_retry)
    """
    message = error.message.lower()
    full_text = f"{error.message} {error.full_traceback or ''}"

    for pattern_info in KNOWN_FIXES:
        pattern = pattern_info["pattern"]
        if re.search(pattern, full_text, re.IGNORECASE):
            logger.info(f"Error matched pattern: {pattern_info['description']}")
            should_retry = pattern_info.get("retry", False)
            return pattern_info, should_retry

    return None, False

# ============================================================================
# AUTO-FIX IMPLEMENTATIONS
# ============================================================================

def fix_missing_import(error: ErrorInfo, pattern_info: Dict, logger: logging.Logger) -> Optional[FixAction]:
    """Fix a missing import error"""
    match = re.search(r"name '(\w+)' is not defined", error.message)
    if not match:
        return None

    missing_name = match.group(1)
    common_imports = pattern_info.get("common_imports", {})

    if missing_name not in common_imports:
        logger.warning(f"Unknown import: {missing_name}, will need Claude to fix")
        return None

    import_statement = common_imports[missing_name]

    # Find the file to modify
    if error.file_path and Path(error.file_path).exists():
        file_path = Path(error.file_path)
    else:
        # Try to find it from traceback
        logger.warning("Could not determine file to fix")
        return None

    # Read the file
    original_content = file_path.read_text(encoding='utf-8')

    # Check if import already exists
    if import_statement in original_content:
        logger.info(f"Import already exists: {import_statement}")
        return None

    # Find the best place to add the import (after other imports)
    lines = original_content.split('\n')
    insert_index = 0

    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_index = i + 1
        elif line.strip() and not line.startswith('#') and not line.startswith('"""') and insert_index > 0:
            break

    # Insert the import
    lines.insert(insert_index, import_statement)
    new_content = '\n'.join(lines)

    # Create backup and apply fix
    backup_path = create_backup(file_path, logger)
    file_path.write_text(new_content, encoding='utf-8')

    logger.info(f"Added import '{import_statement}' to {file_path}")

    return FixAction(
        error=error,
        fix_type="add_import",
        description=f"Added missing import: {import_statement}",
        file_modified=str(file_path),
        original_content=original_content,
        new_content=new_content,
        success=True
    )

def fix_missing_package(error: ErrorInfo, pattern_info: Dict, logger: logging.Logger) -> Optional[FixAction]:
    """Install a missing package"""
    match = re.search(r"No module named '(\w+)'", error.message)
    if not match:
        return None

    package_name = match.group(1)

    # Map some module names to package names
    package_map = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "yaml": "pyyaml",
    }

    install_name = package_map.get(package_name, package_name)

    logger.info(f"Installing missing package: {install_name}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", install_name],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info(f"Successfully installed {install_name}")
            return FixAction(
                error=error,
                fix_type="install_package",
                description=f"Installed missing package: {install_name}",
                success=True
            )
        else:
            logger.error(f"Failed to install {install_name}: {result.stderr}")
            return None

    except Exception as e:
        logger.error(f"Error installing package: {e}")
        return None

# ============================================================================
# CLAUDE API INTEGRATION
# ============================================================================

def call_claude_for_fix(error: ErrorInfo, file_content: str, logger: logging.Logger) -> Optional[str]:
    """Call Claude API to get a fix for an error"""
    if not CLAUDE_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY configured, cannot use Claude for fixes")
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed, installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "anthropic"],
                      capture_output=True, timeout=60)
        import anthropic

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    prompt = f"""You are fixing a Python scraper error. Analyze this error and provide the EXACT fix.

ERROR:
{error.message}

{f"TRACEBACK:{chr(10)}{error.full_traceback}" if error.full_traceback else ""}

{f"FILE: {error.file_path}" if error.file_path else ""}
{f"LINE: {error.line_number}" if error.line_number else ""}

CURRENT FILE CONTENT:
```python
{file_content}
```

Respond with ONLY a JSON object in this exact format:
{{
    "fix_description": "Brief description of what you're fixing",
    "search_text": "The exact text to find in the file (include enough context to be unique)",
    "replace_text": "The exact replacement text"
}}

Important:
- search_text must be an EXACT match of text currently in the file
- Include enough context in search_text to make it unique
- Keep the fix minimal and focused
- Do not add unnecessary changes
"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            fix_data = json.loads(json_match.group())
            return fix_data
        else:
            logger.error(f"Could not parse Claude response as JSON: {response_text[:500]}")
            return None

    except Exception as e:
        logger.error(f"Error calling Claude API: {e}")
        return None

def apply_claude_fix(error: ErrorInfo, logger: logging.Logger) -> Optional[FixAction]:
    """Get a fix from Claude and apply it"""
    if not error.file_path or not Path(error.file_path).exists():
        logger.warning("Cannot apply Claude fix: file path unknown or doesn't exist")
        return None

    file_path = Path(error.file_path)
    original_content = file_path.read_text(encoding='utf-8')

    fix_data = call_claude_for_fix(error, original_content, logger)
    if not fix_data:
        return None

    search_text = fix_data.get("search_text", "")
    replace_text = fix_data.get("replace_text", "")
    description = fix_data.get("fix_description", "Claude-suggested fix")

    if not search_text or search_text not in original_content:
        logger.error(f"Search text not found in file: {search_text[:100]}...")
        return None

    # Apply the fix
    new_content = original_content.replace(search_text, replace_text, 1)

    if new_content == original_content:
        logger.warning("Fix would not change the file")
        return None

    # Validate syntax before applying
    try:
        compile(new_content, str(file_path), 'exec')
    except SyntaxError as e:
        logger.error(f"Claude's fix has syntax error: {e}")
        return None

    # Create backup and apply
    backup_path = create_backup(file_path, logger)
    file_path.write_text(new_content, encoding='utf-8')

    logger.info(f"Applied Claude fix: {description}")

    return FixAction(
        error=error,
        fix_type="claude_fix",
        description=description,
        file_modified=str(file_path),
        original_content=original_content,
        new_content=new_content,
        success=True
    )

# ============================================================================
# FIX HISTORY
# ============================================================================

def load_fix_history() -> List[Dict]:
    """Load fix history from file"""
    if FIX_HISTORY_FILE.exists():
        try:
            return json.loads(FIX_HISTORY_FILE.read_text())
        except:
            return []
    return []

def save_fix_to_history(fix: FixAction):
    """Save a fix to history"""
    history = load_fix_history()

    history.append({
        "timestamp": fix.timestamp,
        "error_type": fix.error.error_type,
        "error_message": fix.error.message,
        "store_name": fix.error.store_name,
        "fix_type": fix.fix_type,
        "description": fix.description,
        "file_modified": fix.file_modified,
        "success": fix.success
    })

    # Keep last 100 fixes
    history = history[-100:]

    FIX_HISTORY_FILE.write_text(json.dumps(history, indent=2))

# ============================================================================
# NOTIFICATION
# ============================================================================

def send_agent_notification(subject: str, body: str, logger: logging.Logger):
    """Send notification about agent actions"""
    if not SEND_AGENT_NOTIFICATIONS:
        return

    try:
        from utils.data_processing import DataProcessor
        processor = DataProcessor()

        html_body = f"""
        <html>
        <body>
        <h2>Scraper Agent Report</h2>
        <p>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <hr>
        {body}
        </body>
        </html>
        """

        # Use existing email infrastructure
        processor.send_notification(html_body, mail_to_prod=True)
        logger.info(f"Sent agent notification: {subject}")

    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

# ============================================================================
# MAIN AGENT
# ============================================================================

class ScraperAgent:
    """Main agent class that monitors and fixes the scraper"""

    def __init__(self):
        self.logger = setup_agent_logging()
        self.script_dir = Path(__file__).parent
        self.main_script = self.script_dir / "main.py"
        self.fixes_applied: List[FixAction] = []
        self.retry_count = 0

    def run_scraper(self) -> Tuple[int, str, str]:
        """Run the main scraper and capture output"""
        self.logger.info("Starting scraper execution...")

        try:
            result = subprocess.run(
                [sys.executable, str(self.main_script)],
                capture_output=True,
                text=True,
                timeout=7200,  # 2 hour timeout
                cwd=str(self.script_dir)
            )

            self.logger.info(f"Scraper finished with exit code: {result.returncode}")
            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            self.logger.error("Scraper timed out after 2 hours")
            return -1, "", "Scraper execution timed out"
        except Exception as e:
            self.logger.error(f"Error running scraper: {e}")
            return -1, "", str(e)

    def analyze_and_fix(self, stdout: str, stderr: str) -> bool:
        """
        Analyze output for errors and attempt fixes.

        Returns:
            True if fixes were applied and retry is recommended
        """
        combined_output = f"{stdout}\n{stderr}"
        errors = parse_scraper_output(combined_output, self.logger)

        if not errors:
            self.logger.info("No errors detected")
            return False

        fixes_this_round = 0
        should_retry = False

        for error in errors:
            if fixes_this_round >= MAX_AUTO_FIXES_PER_RUN:
                self.logger.warning("Max auto-fixes reached for this run")
                break

            self.logger.info(f"Analyzing error: {error.message[:100]}...")

            # Try to categorize and fix
            pattern_info, retry_needed = categorize_error(error, self.logger)

            if pattern_info:
                fix_type = pattern_info.get("fix_type")

                if fix_type == "add_import":
                    fix = fix_missing_import(error, pattern_info, self.logger)
                    if fix:
                        self.fixes_applied.append(fix)
                        save_fix_to_history(fix)
                        fixes_this_round += 1
                        should_retry = True

                elif fix_type == "install_package":
                    fix = fix_missing_package(error, pattern_info, self.logger)
                    if fix:
                        self.fixes_applied.append(fix)
                        save_fix_to_history(fix)
                        fixes_this_round += 1
                        should_retry = True

                elif fix_type == "retry":
                    should_retry = True
                    self.logger.info(f"Error type suggests retry: {pattern_info['description']}")

                elif fix_type == "claude_fix":
                    fix = apply_claude_fix(error, self.logger)
                    if fix:
                        self.fixes_applied.append(fix)
                        save_fix_to_history(fix)
                        fixes_this_round += 1
                        should_retry = True

                elif fix_type == "notify":
                    self.logger.info(f"Manual intervention needed: {pattern_info['description']}")

            else:
                # Unknown error - try Claude
                self.logger.info("Unknown error pattern, attempting Claude fix...")
                fix = apply_claude_fix(error, self.logger)
                if fix:
                    self.fixes_applied.append(fix)
                    save_fix_to_history(fix)
                    fixes_this_round += 1
                    should_retry = True

        return should_retry and fixes_this_round > 0

    def generate_report(self, final_exit_code: int, total_runs: int) -> str:
        """Generate HTML report of agent actions"""
        report = f"""
        <h3>Execution Summary</h3>
        <ul>
            <li><strong>Final Exit Code:</strong> {final_exit_code}</li>
            <li><strong>Total Runs:</strong> {total_runs}</li>
            <li><strong>Fixes Applied:</strong> {len(self.fixes_applied)}</li>
        </ul>
        """

        if self.fixes_applied:
            report += "<h3>Fixes Applied</h3><table border='1' style='border-collapse: collapse;'>"
            report += "<tr><th style='padding: 8px;'>Time</th><th style='padding: 8px;'>Type</th><th style='padding: 8px;'>Description</th><th style='padding: 8px;'>File</th></tr>"

            for fix in self.fixes_applied:
                report += f"""
                <tr>
                    <td style='padding: 8px;'>{fix.timestamp}</td>
                    <td style='padding: 8px;'>{fix.fix_type}</td>
                    <td style='padding: 8px;'>{fix.description}</td>
                    <td style='padding: 8px;'>{fix.file_modified or 'N/A'}</td>
                </tr>
                """

            report += "</table>"

        return report

    def run(self) -> int:
        """Main agent execution loop"""
        self.logger.info("=" * 60)
        self.logger.info("SCRAPER AGENT STARTED")
        self.logger.info("=" * 60)

        start_time = time.time()
        total_runs = 0
        final_exit_code = 0

        while self.retry_count <= MAX_RETRIES:
            total_runs += 1
            self.logger.info(f"Run #{total_runs} (retry {self.retry_count}/{MAX_RETRIES})")

            # Run the scraper
            exit_code, stdout, stderr = self.run_scraper()
            final_exit_code = exit_code

            if exit_code == 0:
                self.logger.info("Scraper completed successfully!")
                break

            self.logger.warning(f"Scraper failed with exit code {exit_code}")

            # Analyze and attempt fixes
            should_retry = self.analyze_and_fix(stdout, stderr)

            if should_retry and self.retry_count < MAX_RETRIES:
                self.retry_count += 1
                self.logger.info(f"Retrying after fixes (attempt {self.retry_count}/{MAX_RETRIES})...")
                time.sleep(10)  # Brief pause before retry
            else:
                if self.retry_count >= MAX_RETRIES:
                    self.logger.error("Max retries exceeded")
                break

        # Generate and send report
        duration = time.time() - start_time
        self.logger.info(f"Agent completed in {duration:.2f}s")

        if self.fixes_applied or final_exit_code != 0:
            report = self.generate_report(final_exit_code, total_runs)
            send_agent_notification(
                f"Scraper Agent Report - {'SUCCESS' if final_exit_code == 0 else 'FAILED'}",
                report,
                self.logger
            )

        self.logger.info("=" * 60)
        self.logger.info("SCRAPER AGENT FINISHED")
        self.logger.info("=" * 60)

        return final_exit_code


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Entry point"""
    agent = ScraperAgent()
    exit_code = agent.run()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
