"""Agent 1b: SharePoint RFP fetcher. Deterministic, no AI. See backend/rfp_fetch/README.md.

    python scripts/run_rfp_fetch.py --state snapshot/ --out rfp_out            # live: Graph in, write plan out
    python scripts/run_rfp_fetch.py --state snapshot/ --dry-run                # read and report, plan nothing
    python scripts/run_rfp_fetch.py --state snapshot/ --listing files.json     # offline, no Graph
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from rfp_fetch.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
