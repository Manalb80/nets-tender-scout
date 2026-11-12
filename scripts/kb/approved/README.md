Approved workbench proposals go here as Markdown (Export Markdown from Step 4), with this header added:

---
tender_id: PPRA-TS0000017824E
client: State Bank of Pakistan
verticals: networking, sec_network
approved_by: Manal Butt
approved_at: 2026-11-12
status: approved
---

Then run: python -I scripts/kb/agent6_rebuild_kb.py --pdf-dir <seed PDFs> --approved-dir scripts/kb/approved --scorer-dir backend --out scripts/kb/out
