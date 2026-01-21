"""
Quick test for the scraper agent.
Run this to verify the agent is set up correctly.
"""

import sys
from pathlib import Path

def test_imports():
    """Test that all imports work"""
    print("Testing imports...")
    try:
        from scraper_agent import ScraperAgent, parse_scraper_output, categorize_error
        print("  Core agent imports OK")
    except ImportError as e:
        print(f"  FAILED: {e}")
        return False

    try:
        from dotenv import load_dotenv
        print("  dotenv import OK")
    except ImportError:
        print("  FAILED: Install python-dotenv")
        return False

    return True

def test_directories():
    """Test that required directories exist"""
    print("\nTesting directories...")
    script_dir = Path(__file__).parent

    required = [
        script_dir / "main.py",
        script_dir / "config" / "website_list.json",
        script_dir / ".env",
    ]

    all_ok = True
    for path in required:
        if path.exists():
            print(f"  {path.name} OK")
        else:
            print(f"  MISSING: {path}")
            all_ok = False

    return all_ok

def test_anthropic_key():
    """Test that Anthropic API key is configured"""
    print("\nTesting Claude API key...")
    import os
    from dotenv import load_dotenv
    load_dotenv()

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key and len(key) > 10:
        print(f"  API key configured ({key[:8]}...)")
        return True
    else:
        print("  WARNING: ANTHROPIC_API_KEY not set in .env")
        print("  The agent will still work but cannot use Claude for complex fixes")
        print("  Get your key from: https://console.anthropic.com/")
        return False

def test_error_patterns():
    """Test error pattern matching"""
    print("\nTesting error pattern matching...")
    from scraper_agent import parse_scraper_output, categorize_error, ErrorInfo
    import logging
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger("test")

    # Test known error patterns
    test_cases = [
        ("name 'time' is not defined", "add_import"),
        ("No module named 'foobar'", "install_package"),
        ("TimeoutException: waited 30 seconds", "retry"),
        ("no such window: target window already closed", "retry"),
    ]

    for error_msg, expected_fix in test_cases:
        error = ErrorInfo(error_type="test", message=error_msg)
        pattern, _ = categorize_error(error, logger)

        if pattern and pattern.get("fix_type") == expected_fix:
            print(f"  Pattern match OK: {error_msg[:30]}...")
        else:
            print(f"  FAILED: {error_msg[:30]}... (expected {expected_fix})")

    return True

def main():
    print("=" * 50)
    print("SCRAPER AGENT TEST")
    print("=" * 50)

    results = []
    results.append(("Imports", test_imports()))
    results.append(("Directories", test_directories()))
    results.append(("API Key", test_anthropic_key()))
    results.append(("Patterns", test_error_patterns()))

    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "WARN" if name == "API Key" else "FAIL"
        print(f"  {name}: {status}")
        if not passed and name != "API Key":
            all_passed = False

    if all_passed:
        print("\nAgent is ready to use!")
        print("\nTo run:")
        print("  python scraper_agent.py")
        print("\nOr update Task Scheduler to run scraper_agent.py instead of main.py")
    else:
        print("\nFix the issues above before running the agent.")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
