"""Daily tender scan. The only entry point: GitHub Actions, a server cron job and the Claude
prototype all run this same file.

    python scripts/run_scan.py                      # live: writes to Postgres (DATABASE_URL)
    python scripts/run_scan.py --dry-run            # scan and validate, write nothing
    python scripts/run_scan.py --store json --state tenders/ --out scan_out   # snapshot in, write plan out
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from tender_scan.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
