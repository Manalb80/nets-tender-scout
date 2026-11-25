# rfp_fetch: Agent 1b, the SharePoint RFP fetcher

People pick the tenders they want, download the RFP from the portal themselves and save it in the
SharePoint folder **NETS-Karachi Presales-Technical Proposals/RFP**. This program does the rest, with no AI
model anywhere in it:

1. Lists the folder through Microsoft Graph (optionally recursive).
2. Matches each file to a **live** tender (open, score 70 or more, not NOGO) by the tender's portal number
   in the file name (`match.py` has the exact rules). Unmatched or ambiguous files are reported, never guessed.
3. Downloads only new or changed files. The dashboard is the sync state: each file sent is recorded in
   `rfp_analysis/<id>.docs[]` with its SharePoint item id and cTag, so nothing is downloaded twice.
4. Extracts text (PDF up to 40 pages, DOCX, XLSX, CSV, TXT). A PDF with no text layer is flagged as scanned.
5. Produces a validated write plan that touches only the fields listed below.

The language models start only after this, in the workbench: once `rfpText` and `rfp_stamp` arrive, the
Manager starts the four analyses (summary, grading, compliance, BOQ).

## Where it sits

| Agent | Job | Program |
|---|---|---|
| Agent 1, Scout | Read the portals, score, qualify, log the scan | `scripts/run_scan.py` |
| Agent 1b, Acquisition | SharePoint RFP folder to tender text | `scripts/run_rfp_fetch.py` |
| Workbench agents | Summary, grading, compliance, BOQ, proposal | the dashboard page (Claude) |

Agent 1 never touches SharePoint; Agent 1b never touches the portals.

## Fields written, and nothing else

| Record | Fields |
|---|---|
| `rfp_analysis/<id>` | `tender_id, rfpText, rfp_chars, rfp_stamp, rfp_received_at, rfpSource ("AGENT_1B_SHAREPOINT"), docs` |
| `rfp_text/<id>__<n>` | `tender_id, part, parts, stamp, text`: only when the text is over 120 KB, exactly as the workbench splits it |
| `tenders/<id>` | `acquisition_status, acqStatus` (`SHAREPOINT`, or `SHAREPOINT_SCANNED` when only scanned files exist), `doc_accessible` |
| `sp_index/<item id>` | the folder index the workbench's file picker reads |
| `config/sharepoint` | `indexed_at, count, indexed_by ("agent_1b"), error`, plus `folder_uri, folder_name` when missing |

`summary, grading, compliance, boq, decision` and every other analysis or human field are never written;
`engine.validate` refuses any plan that would.

## Setup

```
pip install requests msal pypdf
```

| Variable | Meaning |
|---|---|
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` | App-only login (recommended for a schedule) |
| `GRAPH_ACCESS_TOKEN` | Alternative for a quick test: a delegated token, valid about an hour |
| `SHAREPOINT_DRIVE_ID` + `SHAREPOINT_RFP_ITEM_ID` | The folder, by id (most reliable) |
| `SHAREPOINT_RFP_SHARE_URL` | Or: the folder's sharing link |
| `SHAREPOINT_DRIVE_ID` + `SHAREPOINT_RFP_ROOT` | Or: a path from the drive root |
| `SHAREPOINT_RFP_RECURSIVE` | `true` to include subfolders |
| `RFP_DOWNLOAD_DIR` | Optional: keep a copy of each downloaded file in `<dir>/<tender id>/` |

Find both ids with Graph Explorer (`GET /me/drive/root:/NETS-Karachi Presales-Technical Proposals/RFP`):
```
SHAREPOINT_DRIVE_ID=your-drive-id
SHAREPOINT_RFP_ITEM_ID=your-rfp-folder-item-id
```

**App-only access needs your IT admin.** Register an app in Microsoft Entra ID (Azure AD), add the Microsoft
Graph *application* permission `Files.Read.All` (or `Sites.Read.All`), and have a tenant admin click "Grant
admin consent". Then create a client secret. The folder lives in a personal OneDrive, which app-only access
can read once consent is granted; a sharing link alone is not always resolvable with app-only tokens, so
prefer the drive id and item id above.

## Run

```
# 1. Export the dashboard (Claude prototype): ArtifactData list of tenders, rfp_analysis, rfp_text and
#    sp_index with out_dir=snapshot, and get config/sharepoint into snapshot/config/sharepoint.json
# 2. Read, match and report without planning any writes:
python scripts/run_rfp_fetch.py --state snapshot --dry-run
# 3. Build the plan:
python scripts/run_rfp_fetch.py --state snapshot --out rfp_out
# 4. Apply rfp_out/batch_NNN.json in order, unchanged (add if_version for updates). rfp_out/report.json
#    lists what was sent, unchanged, unmatched, ambiguous, scanned and failed.
```

Exit codes: 0 ok (also when there is nothing to do), 2 Graph or configuration error (nothing planned).

## Test without SharePoint

```
python -m pytest tests/test_rfp_fetch.py -q
python scripts/run_rfp_fetch.py --state snapshot --listing files.json --files-dir ./files --dry-run
```
`files.json` is a list of `{item_id, drive_id, name, size, ctag, modified}`; the files themselves sit in `--files-dir`.

## Not covered

- OCR. Scanned PDFs are flagged (`SHAREPOINT_SCANNED`, `docs[].read = "scanned"`) for a person to replace
  with a text PDF; `backend/rfp_sync_engine.py` has a Tesseract path if OCR is wanted later.
- Legacy `.doc` and `.xls` files are reported as unsupported.
- A Postgres store. The plan format is ready for one; today it is applied through the artifact database.
