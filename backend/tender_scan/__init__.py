"""Deterministic daily tender scan.

One code path for every environment. The same engine runs in GitHub Actions against
Postgres (live) and from a JSON snapshot (the Claude artifact prototype). Nothing in
this package depends on a sandbox, a browser, or an AI model.

Layers, each testable on its own:
  dates      closing date text -> timezone-aware datetime (Pakistan time)
  normalize  one canonical id, title and closing string per tender
  parsers    portal HTML -> raw rows (pure functions, no network)
  portals    paged fetching with an explicit "complete" flag per portal
  engine     scoring, open/closed logic, safety guards, fixed output schema
  stores     Postgres (live) and JSON (snapshot in, write plan out)
"""
SCHEMA_VERSION = 1
SCORE_THRESHOLD = 70
