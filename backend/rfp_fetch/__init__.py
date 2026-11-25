"""rfp_fetch: Agent 1b, the deterministic SharePoint RFP fetcher.

People download the RFPs they want from the tender portals and save them in the SharePoint folder
"NETS-Karachi Presales-Technical Proposals/RFP". This package lists that folder through Microsoft Graph,
matches each file to a live tender by the tender's portal number, downloads only new or changed files,
extracts their text and produces a write plan for the dashboard. No AI model is used anywhere here.
"""
LIVE_SCORE = 70
TEXT_CAP = 180_000          # characters of RFP text kept per tender (the workbench's WB_TEXT_CAP)
INLINE_BYTES = 120_000      # above this the text goes to rfp_text parts (the workbench's WB_INLINE_BYTES)
CHUNK_CHARS = 50_000        # characters per rfp_text part (the workbench's WB_CHUNK)
SCANNED_MIN_CHARS = 500     # fewer non-space characters than this: a scanned, image-only file
MAX_PAGES = 40              # pages read per PDF
SOURCE = "AGENT_1B_SHAREPOINT"
