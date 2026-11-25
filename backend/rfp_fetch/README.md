# rfp_fetch: Agent 1b, RFP intake

People pick the tenders they want, download the RFP from the portal themselves and save it in the
SharePoint folder **NETS-Karachi Presales-Technical Proposals/RFP**. This program does the rest, with no AI
model anywhere in it, and **without an Azure app registration**: it reads the OneDrive-synced copy of that
folder on a PC (or any staging folder people save downloads into).

1. Scans the folder (subfolders too). Skips partial downloads and lock files (`.crdownload`, `.part`, `~$...`,
   `desktop.ini`) and OneDrive online-only placeholders.
2. Waits for files to settle: a file is read only after it has been unchanged for `RFP_STABLE_SECONDS`, kept
   the same size and modified time across a second check, and can be opened (Windows refuses files still held
   by a browser or Word). Anything else is reported as `waiting` and picked up on the next run.
3. Deduplicates by SHA-256. A size and modified-time memo (`RFP_CACHE_FILE`) avoids re-hashing files that
   have not changed. The dashboard is the record of what was sent: each file is stored in
   `rfp_analysis/<id>.docs[]` with its `file_sha256`, so the same content is never sent twice, even when
   renamed or copied. A new version of the same file replaces only its own text section.
4. Matches each file to a **live** tender (open, score 70 or more, not NOGO) by the tender's portal number in
   the file name, or in its subfolder name (`EPADS-P194040/bidding document.pdf`). `match.py` has the exact
   rules. Unmatched or ambiguous files are reported, never guessed.
5. Extracts text (PDF up to 40 pages, DOCX, XLSX, CSV, TXT). A PDF with no text layer is flagged as scanned.
6. Produces a validated write plan that touches only the fields listed below.
7. Archives files the dashboard already holds into `RFP_ARCHIVE_DIR/<tender id>/`. A file sent in this run is
   archived on the next run, after its batch has been applied, so nothing is lost if a batch is never applied.

The language models start only after this, in the workbench: once `rfpText` and `rfp_stamp` arrive, the
Manager starts the four analyses (summary, grading, compliance, BOQ).

## Where it sits

| Agent | Job | Program |
|---|---|---|
| Agent 1, Scout | Read the portals, score, qualify, log the scan | `scripts/run_scan.py` |
| Agent 1b, Acquisition | RFP folder to tender text | `scripts/run_rfp_fetch.py` |
| Workbench agents | Summary, grading, compliance, BOQ, proposal | the dashboard page (Claude) |

Agent 1 never touches the RFP folder; Agent 1b never touches the portals.

## Sources

`sources.py` defines one interface (`list_files()`, `read(file)`, `archive(file, tender, mode)`), with:

| `--source` | Reads | Needs |
|---|---|---|
| `local` (default) | a local or OneDrive-synced folder | the folder on disk |
| `graph` | the SharePoint folder through Microsoft Graph | an app registration with admin consent (later) |

The engine is the same for both, so switching to Graph later is one setting.

## Fields written, and nothing else

| Record | Fields |
|---|---|
| `rfp_analysis/<id>` | `tender_id, rfpText, rfp_chars, rfp_stamp, rfp_received_at, rfpSource, docs` |
| `rfp_text/<id>__<n>` | `tender_id, part, parts, stamp, text`: only when the text is over 120 KB, exactly as the workbench splits it |
| `tenders/<id>` | `acquisition_status, acqStatus` (`SHAREPOINT`, or `AUTO_DOWNLOADED` with `RFP_ACQ_STATUS`; `..._SCANNED` when only scanned files exist), `doc_accessible` |
| `sp_index/<item id>`, `config/sharepoint` | Graph source only: the folder index the workbench's file picker reads |

Human and analysis work is never overwritten:
- `summary, grading, compliance, boq, decision` and every other field are never written; `engine.validate`
  refuses any plan that would.
- Other files' text sections (for example a manual upload) are kept when one file changes.
- A status a person set (for example `MANUAL_UPLOADED`) is left alone and reported as `kept_status`.
- `rfpSource` is set only when empty or already an agent value (`AGENT_1B_LOCAL`, `AGENT_1B_SHAREPOINT`).

## Configuration

`pip install pypdf` is all the local source needs (`requests` and `msal` only for Graph).

| Variable | Default | Meaning |
|---|---|---|
| `RFP_SOURCE` | `local` | `local` or `graph` |
| `RFP_WATCH_DIR` | (required) | The folder to scan, e.g. `C:\Users\<you>\OneDrive - NETS International\NETS-Karachi Presales-Technical Proposals\RFP` |
| `RFP_ARCHIVE_DIR` | (none: no archive) | Where processed files are archived, by tender id. Keep it outside the shared folder |
| `RFP_ARCHIVE_MODE` | `copy` | `copy` keeps the original; `move` empties a staging folder; `off` |
| `RFP_STABLE_SECONDS` | `30` | How long a file must be unchanged before it is read |
| `RFP_RECHECK_SECONDS` | `2` | Pause between the two size checks |
| `RFP_CACHE_FILE` | `rfp_state/agent1b_hashes.json` | SHA-256 memo |
| `RFP_RECURSIVE` | `true` | Include subfolders |
| `RFP_HYDRATE` | `false` | `true` reads OneDrive online-only files too (OneDrive downloads them) |
| `RFP_ACQ_STATUS` | `SHAREPOINT` | Or `AUTO_DOWNLOADED` |
| `RFP_OUT_DIR` | `rfp_out` | Where the plan goes |

**Do not use `move` on the synced SharePoint folder itself**: OneDrive would remove the files from SharePoint
for everyone. Use `move` only on a private staging folder.

For the synced folder: in SharePoint open the RFP folder, choose "Add shortcut to My files" (or "Sync"), then
in File Explorer right-click it and choose "Always keep on this device" so the files are real, not placeholders.

### Graph, for later

Set `RFP_SOURCE=graph` plus the variables in `graph.py`: `GRAPH_TENANT_ID, GRAPH_CLIENT_ID,
GRAPH_CLIENT_SECRET` (or `GRAPH_ACCESS_TOKEN` for a one-hour test) and `SHAREPOINT_DRIVE_ID` +
`SHAREPOINT_RFP_ITEM_ID` (or `SHAREPOINT_RFP_SHARE_URL`). App-only access needs an app registration in
Microsoft Entra ID with the Graph application permission `Files.Read.All` (or `Sites.Read.All`) and a tenant
admin's consent.

## Run

```
# 1. Export the dashboard (Claude prototype): ArtifactData list of tenders, rfp_analysis and rfp_text with
#    out_dir=snapshot.
# 2. See what would happen, writing nothing (no plan, no archive, no cache):
python scripts/run_rfp_fetch.py --state snapshot --watch-dir "<RFP folder>" --dry-run
# 3. Build the plan:
python scripts/run_rfp_fetch.py --state snapshot --watch-dir "<RFP folder>" --archive-dir "<archive>" --out rfp_out
# 4. Apply rfp_out/batch_NNN.json in order, unchanged (add if_version for updates). rfp_out/report.json
#    lists what was sent, unchanged, duplicate, unmatched, ambiguous, scanned, waiting, archived and failed.
```

Exit codes: 0 ok (also when there is nothing to do), 2 folder or Graph configuration error (nothing planned).

## Test standalone, without the dashboard

```
python -m pytest tests/test_rfp_fetch.py tests/test_rfp_intake_local.py -q
# Rehearse two runs against a copy of the snapshot: run 1 plans and applies to the copy, run 2 archives.
cp -r snapshot rehearsal
python scripts/run_rfp_fetch.py --state rehearsal --watch-dir ./test_in --archive-dir ./test_archive --stable-seconds 0 --apply-to-snapshot
python scripts/run_rfp_fetch.py --state rehearsal --watch-dir ./test_in --archive-dir ./test_archive --stable-seconds 0
```
`--apply-to-snapshot` only changes the local snapshot files, never the dashboard.

## Not covered

- OCR. Scanned PDFs are flagged (`..._SCANNED`, `docs[].read = "scanned"`) for a person to replace with a text
  PDF; `backend/rfp_sync_engine.py` has a Tesseract path if OCR is wanted later.
- Legacy `.doc` and `.xls` files are reported as unsupported.
- A continuous watcher. Each run is one scan; run it on a schedule (Task Scheduler or cron, every few minutes).
- A Postgres store. The plan format is ready for one; today it is applied through the artifact database.
