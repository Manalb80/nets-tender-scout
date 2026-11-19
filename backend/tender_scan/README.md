# tender_scan: the deterministic daily scan

One fixed program reads the three portals, applies the same rules every day, and writes one fixed
record layout. It replaces instructions that an AI agent re-interpreted each morning.

## Run it

| Where | Command | Writes to |
|---|---|---|
| Live (GitHub Actions, a server cron job) | `python scripts/run_scan.py` | Postgres, from `DATABASE_URL` |
| Check without writing | `python scripts/run_scan.py --dry-run` | nothing |
| Claude prototype, or any system reached through another tool | `python scripts/run_scan.py --store json --state <folder of stored tenders> --last-scan <file> --out scan_out` | `scan_out/batch_NNN.json` write plan and `scan_out/scan_record.json` |

Needs Python 3.10 or later, `requests`, `beautifulsoup4`, and for Postgres `sqlalchemy` with `psycopg2-binary`.
No browser, no AI model, no relay services.

## Rules (each has a test in `tests/test_tender_scan.py`)

1. **One tender, one id.** PPRA `PPRA-TS0000017741E` (never with the notice type), EPADS `EPADS-P188832`,
   Sindh Bank its SPPRA number. An existing suffixed PPRA record is updated in place, never duplicated.
2. **Every page is read.** A portal is `complete` only when its last page was reached and, for PPRA, the number
   of rows matches what the portal reports.
3. **Open needs a date.** A tender is open only if a closing date was read and has not passed. A tender with
   no date is never created and never open. Relative times ("4h 8m Left") are stored as a real date and time.
4. **Closing a missing tender needs proof.** Only when the portal was read completely and returned at least
   70% of the rows of the last complete scan.
5. **A tender left unchecked is named, not assumed.** When a portal is incomplete, its previously open
   tenders are neither closed nor quietly treated as confirmed: the scan record carries `unchecked_count`
   and `unchecked_ids` per portal, and the dashboard shows them as unchecked rather than confirmed open.
6. **Other people's fields are never written.** Only the fields in `engine.SCAN_FIELDS`.
7. **One scan record layout** (`engine.SCAN_KEYS`), and the plan is validated before anything is written.
8. **Postgres writes are one transaction.** A failed scan leaves the database exactly as it was.

## Re-checking one portal

When a scan leaves a portal incomplete, re-check that portal alone, without waiting for tomorrow's run:

```
python scripts/run_scan.py --portals ppra
```

The portals left out are reported as not scanned, so nothing of theirs is closed or changed.

## Tests

`python -m pytest tests -q`. They use saved copies of the real portal pages, so they need no network.
Set `TEST_DATABASE_URL` to a disposable Postgres database to include the store tests.

## Not covered

- A portal that blocks the machine running the scan. The scan then reports that portal as incomplete,
  closes nothing for it, and exits normally; it does not work around the block.
- A portal changing its page layout. The parser returns no rows, the portal is reported incomplete,
  and nothing is closed. The fixture tests then need new saved pages.
- Titles and scoring. Scoring is `backend/scorer.py`, unchanged; its fingerprint is stored as `scorer_version`.
