"""
Agent 6: rebuild the proposal knowledge base, per vertical, from
  (a) the seed PDFs (past NETS technical proposals), and
  (b) proposals written in the Tender Scout workbench and APPROVED by a person,
      exported as Markdown with a small header block.

For a layman: the dashboard writer learns from past proposals. This script is how
the pile of past proposals grows. Every time the team approves a new proposal, it
is cut into paragraphs, labelled with the solution areas it covers (networking,
security, data centre, and so on), and added to the pile. The writer only reuses
paragraphs from the same solution area.

For a developer: this is the offline twin of wbKbAdd() in frontend/index.html.
The dashboard already does this live (collection kb_live). Run this script when you
want a single, versioned kb_chunks.json for the asset store or for the later server
deployment (Render + ChromaDB). It never deletes anything; it rebuilds from inputs.

Usage:
  python -I scripts/kb/agent6_rebuild_kb.py \
      --pdf-dir  "D:/NETS/DIGITISATION/Manal Skills/Technical proposals/NETS-Karachi Presales-Technical Proposals" \
      --approved-dir scripts/kb/approved \
      --scorer-dir backend \
      --out scripts/kb/out

Approved proposal file format (Markdown, exported from the workbench "Export Markdown"
button, then saved under --approved-dir with this header added at the top):

  ---
  tender_id: PPRA-TS0000017824E
  client: State Bank of Pakistan
  verticals: networking, sec_network
  approved_by: Manal Butt
  approved_at: 2026-11-12
  status: approved
  ---
  # Technical Proposal: ...
  ## 1. Executive Summary
  ...

Only files with status: approved are included. Verticals must be scorer ids
(see backend/scorer.py SOLUTIONS[*].id); if the header omits them, they are
inferred from the text with the same keyword-density rule used for the seed PDFs.
"""
import argparse, os, re, sys, json, hashlib, collections, datetime

# ---------------------------------------------------------------- shared helpers
STOP = set("""a an the and or of to in for on with by from as at is are was were be been this that these those it its into over under
than then also any all per each our we us you your their they them he she his her will shall may can must should would could
not no nor but if so such via etc which who whom whose where when while within without between among about above below
nets international proposal technical section page table figure""".split())

def clean(s):
    s = s.replace('\u00a0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()

def terms_of(text, k=12):
    ws = re.findall(r'[a-z][a-z0-9\-\+\.]{2,}', text.lower())
    ws = [w.strip('.') for w in ws if w not in STOP and not w.isdigit()]
    return [w for w, _ in collections.Counter(ws).most_common(k)]

def windows(paragraphs, max_words=260):
    """Group consecutive paragraphs into ~260-word windows."""
    cur, cw, out = [], 0, []
    for p in paragraphs:
        w = len(p.split())
        if cw + w > max_words and cur:
            out.append('\n\n'.join(cur)); cur, cw = [], 0
        cur.append(p); cw += w
    if cur: out.append('\n\n'.join(cur))
    return out

def chunk_id(*parts):
    return hashlib.md5('|'.join(parts).encode()).hexdigest()[:12]

def load_scorer(scorer_dir):
    sys.path.insert(0, scorer_dir)
    from scorer import SOLUTIONS  # noqa
    return SOLUTIONS

def infer_verticals(text, solutions, min_hits=6, top=3):
    """Keyword-density rule: a vertical counts when its keywords occur >= min_hits times."""
    low = text.lower()
    counts = {}
    for sol in solutions:
        n = 0
        for k in sol["keywords"]:
            if len(k) < 4: continue
            n += len(re.findall(r'(?<![a-z0-9])' + re.escape(k.lower()) + r'(?![a-z0-9])', low))
        counts[sol["id"]] = n
    return [k for k, v in sorted(counts.items(), key=lambda x: -x[1]) if v >= min_hits][:top]

# ---------------------------------------------------------------- (a) seed PDFs
def chunk_pdfs(pdf_dir, solutions):
    import fitz  # PyMuPDF
    HEAD_RE = re.compile(r'^\s*((\d+(\.\d+)*)[\.\)]?\s+)?([A-Z][A-Za-z0-9 &/,\-\(\)]{3,80})\s*$')
    NOISE = re.compile(r'(?i)contact person|^contents$|table of contents|^urdu$|^modes of communication')

    def client_of(name):
        n = name.replace('.pdf', '')
        m = re.match(r'(?i)^technical proposal \(([^)]*)\) for\s*(.+)$', n)
        if m: return (m.group(2).replace('Statelife', 'State Life') + ' (' + m.group(1) + ')').strip()
        n = re.sub(r'(?i)nets[-_ ]*', '', n)
        n = re.sub(r'(?i)[-_ ]*(technical|tech)[-_ ]*(proposal|prposal).*$', '', n)
        n = re.sub(r'\(\d\)', '', n).replace('-', ' ').replace('_', ' ')
        return re.sub(r'\s+', ' ', n).strip() or name

    def is_heading(line):
        if len(line) > 90 or len(line) < 4: return False
        if line.endswith(('.', ',', ';', ':')) and not re.match(r'^\d', line): return False
        if not HEAD_RE.match(line): return False
        words = line.split()
        return sum(1 for w in words if w[:1].isupper() or w.isdigit()) / len(words) >= 0.6

    chunks, files = [], []
    for fn in sorted(os.listdir(pdf_dir)):
        if not fn.lower().endswith('.pdf'): continue
        doc = fitz.open(os.path.join(pdf_dir, fn))
        client = client_of(fn)
        section, buf, file_chunks = "Introduction", [], []

        def flush():
            nonlocal buf
            txt = clean('\n'.join(buf)); buf = []
            if len(txt.split()) < 25 or NOISE.search(section): return
            paras = [p for p in re.split(r'\n\s*\n', txt) if p.strip()]
            for t in windows(paras):
                t = clean(t)
                if len(t.split()) < 25: continue
                file_chunks.append({"id": chunk_id(fn, section, t[:80]), "source": fn, "client": client,
                                    "section": section[:80], "text": t[:2400], "words": len(t.split()),
                                    "terms": terms_of(t)})
        for page in doc:
            for line in page.get_text("text").split('\n'):
                l = line.strip()
                if not l: buf.append(''); continue
                if is_heading(l) and len(buf) > 3:
                    flush(); section = re.sub(r'^\d+(\.\d+)*[\.\)]?\s+', '', l)
                else:
                    buf.append(l)
        flush()
        verticals = infer_verticals(client + " . " + " ".join(c["text"] for c in file_chunks), solutions)
        for c in file_chunks: c["verticals"] = verticals; c["origin"] = "seed"
        chunks += file_chunks
        files.append({"file": fn, "client": client, "pages": doc.page_count, "chunks": len(file_chunks), "verticals": verticals, "origin": "seed"})
    return chunks, files

# ---------------------------------------------------------------- (b) approved workbench proposals
def parse_front_matter(text):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.S)
    if not m: return {}, text
    meta = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
            k, v = line.split(':', 1); meta[k.strip()] = v.strip()
    return meta, m.group(2)

def chunk_approved(approved_dir, solutions):
    chunks, files = [], []
    if not approved_dir or not os.path.isdir(approved_dir): return chunks, files
    valid_ids = {s["id"] for s in solutions}
    for fn in sorted(os.listdir(approved_dir)):
        if not fn.lower().endswith('.md'): continue
        meta, body = parse_front_matter(open(os.path.join(approved_dir, fn), encoding='utf-8').read())
        if meta.get('status', '').lower() != 'approved':
            print(f"skip {fn}: status is not approved"); continue
        tender = meta.get('tender_id', fn[:-3]); client = meta.get('client', 'Unknown client')
        verticals = [v.strip() for v in meta.get('verticals', '').split(',') if v.strip() in valid_ids]
        if not verticals: verticals = infer_verticals(body, solutions)
        source = f"NETS proposal {tender} ({client})"
        # split on the 13 section headings the workbench writes: "## n. Title"
        parts = re.split(r'^## \d+\.\s+', body, flags=re.M)
        file_chunks = []
        for part in parts[1:]:
            title, _, sec_body = part.partition('\n')
            paras = [p for p in re.split(r'\n\s*\n', sec_body) if p.strip()]
            for i, t in enumerate(windows(paras)):
                t = clean(t)
                if len(t.split()) < 25: continue
                file_chunks.append({"id": "live_" + chunk_id(tender, title, str(i), t[:80]), "source": source, "client": client,
                                    "section": title.strip()[:80], "text": t[:2400], "words": len(t.split()),
                                    "terms": terms_of(t), "verticals": verticals, "origin": "approved",
                                    "tender_id": tender, "added_by": meta.get('approved_by', ''), "added_at": meta.get('approved_at', '')})
        chunks += file_chunks
        files.append({"file": fn, "client": client, "tender_id": tender, "chunks": len(file_chunks), "verticals": verticals, "origin": "approved"})
    return chunks, files

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Agent 6: rebuild the proposal knowledge base per vertical")
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--approved-dir', default=None)
    ap.add_argument('--scorer-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--only-vertical', default=None, help="rebuild only chunks tagged with this scorer id (others are kept from the previous kb_chunks.json)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    solutions = load_scorer(a.scorer_dir)

    seed_chunks, seed_files = chunk_pdfs(a.pdf_dir, solutions)
    live_chunks, live_files = chunk_approved(a.approved_dir, solutions)
    chunks = seed_chunks + live_chunks
    files = seed_files + live_files

    if a.only_vertical:
        prev_path = os.path.join(a.out, 'kb_chunks.json')
        prev = json.load(open(prev_path, encoding='utf-8')) if os.path.exists(prev_path) else []
        keep = [c for c in prev if a.only_vertical not in (c.get("verticals") or [])]
        fresh = [c for c in chunks if a.only_vertical in (c.get("verticals") or [])]
        chunks = keep + fresh
        print(f"vertical {a.only_vertical}: kept {len(keep)} chunks from other verticals, rebuilt {len(fresh)}")

    # de-duplicate identical paragraphs (two copies of the same PDF, re-approved proposals)
    seen, dedup = set(), []
    for c in chunks:
        key = re.sub(r'\W+', '', c["text"].lower())[:400]
        if key in seen: continue
        seen.add(key); dedup.append(c)

    coverage = collections.Counter(v for f in files for v in f["verticals"])
    name_of = {s["id"]: s["name"] for s in solutions}
    report = {
        "built_at": datetime.datetime.utcnow().isoformat() + "Z",
        "files": len(files), "seed_files": len(seed_files), "approved_files": len(live_files),
        "chunks": len(dedup), "words": sum(c["words"] for c in dedup),
        "coverage": {name_of.get(k, k): v for k, v in coverage.most_common()},
        "not_covered": [s["name"] for s in solutions if s["id"] not in coverage],
    }
    json.dump(dedup, open(os.path.join(a.out, 'kb_chunks.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(files, open(os.path.join(a.out, 'kb_files.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(report, open(os.path.join(a.out, 'kb_report.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print("\nNext: upload out/kb_chunks.json as the dashboard asset and update KB_ASSET in frontend/index.html,")
    print("or point the Render deployment's ChromaDB loader at it when the server path goes live.")

if __name__ == '__main__':
    main()
